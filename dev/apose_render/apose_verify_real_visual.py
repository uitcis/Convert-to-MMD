"""渲染真实工程 TESTMIKU.blend 的 A-Pose 烘顶点前后对照图。

运行：
    blender --background --factory-startup TESTMIKU.blend \
        --python tools/apose_verify_real_visual.py

左：烘前 T-Pose（原样）
右：烘后 A-Pose（上臂下垂 36°，evaluated mesh 烘进 Basis + armature_apply）
两列并排，正面 + 45° 俯视角。
"""
import bpy
import os
from math import radians
from mathutils import Vector, Matrix

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "apose_verify_real_visual.png")

arm = bpy.data.objects["Armature"]


def find_bones(arm):
    names = set(arm.data.bones.keys())
    if "左腕" in names:
        return "左腕", "右腕"
    return "UpperArm_L", "UpperArm_R"


L_ARM, R_ARM = find_bones(arm)
meshes = [o for o in bpy.data.objects
          if o.type == 'MESH'
          and any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]
if not meshes:
    raise RuntimeError("没有绑定骨架的网格")
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()


def snapshot():
    out = {}
    for o in meshes:
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        out[o.name] = [tuple(v.co) for v in m.vertices]
        ev.to_mesh_clear()
    return out


before = snapshot()

# 摆 A-Pose（T-Pose 工程：上臂绕世界 Y ±36° 下垂）
for n in (L_ARM, R_ARM):
    pb = arm.pose.bones[n]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (1, 0, 0, 0)
bpy.context.view_layer.update()
for n, sign in ((L_ARM, 1), (R_ARM, -1)):
    pb = arm.pose.bones[n]
    pb.matrix = Matrix.Rotation(radians(36) * sign, 4, 'Y') @ pb.bone.matrix_local
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
posed = snapshot()

# 烘顶点（同新方案）
for o in meshes:
    saved = {}
    if o.data.shape_keys:
        for kb in o.data.shape_keys.key_blocks:
            saved[kb.name] = kb.value
            kb.value = 0.0
    saved_mods = {}
    for m in o.modifiers:
        if m.type != 'ARMATURE':
            saved_mods[m.name] = m.show_viewport
            m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    em = ev.to_mesh()
    baked = [tuple(v.co) for v in em.vertices]
    ev.to_mesh_clear()
    if o.data.shape_keys:
        basis = o.data.shape_keys.key_blocks[0]
        for i, co in enumerate(baked):
            basis.data[i].co = co
    else:
        for i, co in enumerate(baked):
            o.data.vertices[i].co = co
    o.data.update()
    for kb in o.data.shape_keys.key_blocks if o.data.shape_keys else []:
        kb.value = saved[kb.name]
    for m in o.modifiers:
        if m.name in saved_mods:
            m.show_viewport = saved_mods[m.name]

if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
after = snapshot()

# ---------------------------------------------------------------- 重建对照场景
def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def emit(name, rgba):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    return mat


# 取采样点：为减负，每个网格抽样顶点，合并成一个点云对象显示
def build_cloud(name, coords_map, color, x_off):
    """把抽样顶点画成小四面体，Workbench 下可见。"""
    verts, faces = [], []
    r = 0.006
    step = 30
    for oname, coords in coords_map.items():
        for i in range(0, len(coords), step):
            x, y, z = coords[i]
            b = len(verts)
            verts.extend([
                (x + x_off + r, y, z), (x + x_off - r, y, z),
                (x + x_off, y + r, z), (x + x_off, y, z + r),
            ])
            faces.extend([(b, b+1, b+2), (b, b+1, b+3),
                          (b, b+2, b+3), (b+1, b+2, b+3)])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(emit(name + "_m", color))
    return o


# 用曲线画骨架（烘前 T-Pose / 烘后 A-Pose）
def bone_lines(name, coords_list, color, x_off, radius=0.006):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.resolution_u = 1

    def add_seg(a, b):
        sp = cu.splines.new('POLY')
        sp.points.add(1)
        sp.points[0].co = (a[0] + x_off, a[1], a[2], 1)
        sp.points[1].co = (b[0] + x_off, b[1], b[2], 1)

    for seg in coords_list:
        add_seg(*seg)
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(emit(name + "_m", color))
    return o


# 骨架线段（烘前从原始 pose 推算，烘后从 rest 直接读）
def skeleton_segments(pose_mode):
    segs = []
    chain = [("Hips", "Spine"), ("Spine", "Chest"), ("Chest", "UpperChest"),
             ("UpperChest", "Neck"), ("Neck", "Head"),
             ("Hips", "UpperLeg_L"), ("UpperLeg_L", "LowerLeg_L"),
             ("Hips", "UpperLeg_R"), ("UpperLeg_R", "LowerLeg_R"),
             ("UpperChest", L_ARM), (L_ARM, "LowerArm_L" if "UpperArm_L" == L_ARM else "左ひじ"),
             ("UpperChest", R_ARM), (R_ARM, "LowerArm_R" if "UpperArm_R" == R_ARM else "右ひじ")]
    for a, b in chain:
        ba, bb = arm.data.bones.get(a), arm.data.bones.get(b)
        if not ba or not bb:
            continue
        if pose_mode:
            pa, pb = arm.pose.bones.get(a), arm.pose.bones.get(b)
            if not pa or not pb:
                continue
            ha = pa.head
            ta = pb.head
        else:
            ha = ba.head_local
            ta = bb.head_local
        segs.append((tuple(ha), tuple(ta)))
    return segs


# 烘前的骨架线段：需要在烘前 pose 状态抓，这里用重算（T-Pose 时全部 rest 即可）
pre_segs = []
for a, b in [("Hips", "Spine"), ("Spine", "Chest"), ("Chest", "UpperChest"),
             ("UpperChest", "Neck"), ("Neck", "Head"),
             ("Hips", "UpperLeg_L"), ("UpperLeg_L", "LowerLeg_L"),
             ("Hips", "UpperLeg_R"), ("UpperLeg_R", "LowerLeg_R"),
             ("UpperChest", L_ARM), (L_ARM, "LowerArm_L" if L_ARM == "UpperArm_L" else "左ひじ"),
             ("UpperChest", R_ARM), (R_ARM, "LowerArm_R" if R_ARM == "UpperArm_R" else "右ひじ")]:
    ba, bb = arm.data.bones.get(a), arm.data.bones.get(b)
    if ba and bb:
        pre_segs.append((tuple(ba.head_local), tuple(bb.head_local)))

post_segs = skeleton_segments(False)   # 必须在 clear 之前读取骨架数据
clear()
X_L, X_R = -2.2, 2.2
# 烘前：T-Pose 骨架线段（rest）+ 网格点云（未变形的原始顶点，用烘前坐标的逆推近似 rest）
bone_lines("skel_T", pre_segs, (0.8, 0.82, 0.86, 1), X_L, 0.008)
# 烘后：A-Pose 骨架线段（新 rest）
bone_lines("skel_A", post_segs, (1.0, 0.72, 0.2, 1), X_R, 0.008)

# 网格点云：烘后直接用 after 坐标；烘前用 before（原始 T-Pose）
build_cloud("mesh_T", before, (0.3, 0.62, 1.0, 1), X_L)
build_cloud("mesh_A", after, (1.0, 0.32, 0.36, 1), X_R)

# 标签
def label(text, x, z):
    cu = bpy.data.curves.new("t_" + text, 'FONT')
    cu.body = text
    cu.size = 0.16
    cu.align_x = 'CENTER'
    o = bpy.data.objects.new("t_" + text, cu)
    bpy.context.collection.objects.link(o)
    o.location = (x, 0, z)
    o.rotation_euler = (radians(90), 0, 0)
    o.data.materials.append(emit("tm_" + text, (0.95, 0.95, 0.98, 1)))

label("BEFORE  T-Pose", X_L, 1.75)
label("AFTER  A-Pose", X_R, 1.75)

# 相机 / 渲染
scn = bpy.context.scene
scn.render.engine = 'BLENDER_WORKBENCH'
scn.display.shading.light = 'FLAT'
scn.display.shading.color_type = 'MATERIAL'
scn.display.shading.show_shadows = False
scn.display.shading.show_cavity = False
scn.world.color = (0.06, 0.07, 0.09)
cam_data = bpy.data.cameras.new("Cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 6.6
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0, -9, 2.2)
cam.rotation_euler = (Vector((0, 0, 1.0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
scn.camera = cam
scn.render.resolution_x = 1400
scn.render.resolution_y = 700
scn.render.resolution_percentage = 100
scn.render.image_settings.file_format = 'PNG'
scn.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("saved:", OUT)
