"""渲染真实工程 TESTMIKU.blend 的模型截图：烘前 T-Pose / 烘后 A-Pose 并排。

运行：
    blender --background --factory-startup TESTMIKU.blend \
        --python tools/apose_real_render.py

输出：
    tools/apose_real_before.png
    tools/apose_real_after.png
    tools/apose_real_compare.png   (PIL 拼接, 在 Blender 外单独执行)
"""
import bpy
import os
from math import radians
from mathutils import Vector, Matrix

BASE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(BASE, "apose_real_before.png")
AFTER = os.path.join(BASE, "apose_real_after.png")

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
print("骨架 %s, 网格 %d 个" % (arm.name, len(meshes)))

# ---------------------------------------------------------------- 渲染设置
scn = bpy.context.scene
scn.render.engine = 'BLENDER_WORKBENCH'
scn.display.shading.light = 'STUDIO'
scn.display.shading.studio_light = 'paint.sl'
scn.display.shading.color_type = 'MATERIAL'
scn.display.shading.show_shadows = False
scn.display.shading.show_cavity = True
scn.display.shading.cavity_type = 'BOTH'
scn.display.shading.curvature_ridge_factor = 1.0
scn.display.shading.curvature_valley_factor = 1.0
scn.render.film_transparent = False
scn.world.color = (0.10, 0.11, 0.14)

# 隐藏非绑定网格（刚体显示盒等）
hidden = []
for o in bpy.data.objects:
    if o.type == 'MESH' and o not in meshes:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    if o.type == 'CURVE' or o.type == 'FONT':
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)

# 统一材质颜色（Workbench 用 diffuse_color）
for o in meshes:
    for slot in o.material_slots:
        if slot.material:
            slot.material.diffuse_color = (0.72, 0.78, 0.86, 1)

# 相机：正面稍偏上
cam_data = bpy.data.cameras.new("RenderCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.2
cam = bpy.data.objects.new("RenderCam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0, -5, 1.15)
cam.rotation_euler = (Vector((0, 0, 0.92)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
scn.camera = cam
scn.render.resolution_x = 900
scn.render.resolution_y = 900
scn.render.resolution_percentage = 100
scn.render.image_settings.file_format = 'PNG'

# ---------------------------------------------------------------- 烘前
scn.render.filepath = BEFORE
bpy.ops.render.render(write_still=True)
print("saved:", BEFORE)

# ---------------------------------------------------------------- 摆 A-Pose
for n in (L_ARM, R_ARM):
    pb = arm.pose.bones[n]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (1, 0, 0, 0)
bpy.context.view_layer.update()
for n, sign in ((L_ARM, 1), (R_ARM, -1)):
    pb = arm.pose.bones[n]
    pb.matrix = Matrix.Rotation(radians(36) * sign, 4, 'Y') @ pb.bone.matrix_local
bpy.context.view_layer.update()

# ---------------------------------------------------------------- 烘顶点
dg = bpy.context.evaluated_depsgraph_get()
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

# 应用姿态为静置
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()

# 隐藏非绑定网格（apply 后可能恢复显示，再隐藏一次）
for o in bpy.data.objects:
    if o.type == 'MESH' and o not in meshes:
        o.hide_render = True

# ---------------------------------------------------------------- 烘后
scn.render.filepath = AFTER
bpy.ops.render.render(write_still=True)
print("saved:", AFTER)
