"""渲染 A-Pose 烘顶点 demo 的对照图（后台模式，无需界面）。

运行：
    blender --background --factory-startup --python tools/apose_bake_demo_visual.py

左：烘进前 T-Pose（骨架 T-Pose，网格 Basis 为原始顶点）
右：烘进后 A-Pose（骨架 A-Pose，网格 Basis 已写为 evaluated 顶点）
两列摆在同一场景，用正交相机从正面拍一张对比图。
"""
import bpy
from math import radians
from mathutils import Vector

import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "apose_bake_demo_visual.png")

# ---------------------------------------------------------------- 工具


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def emission(name, rgba):
    mat = bpy.data.materials.new(name)
    # Workbench 引擎按 diffuse_color 上色，emission 节点在这里无效
    mat.diffuse_color = rgba
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    em = nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = rgba
    mat.node_tree.links.new(em.outputs[0], out.inputs['Surface'])
    return mat


def curve_lines(name, segments, color, radius=0.02):
    """segments: [( (x,y,z), (x,y,z) ), ...]"""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.resolution_u = 1
    for a, b in segments:
        sp = cu.splines.new('POLY')
        sp.points.add(1)
        sp.points[0].co = (a[0], a[1], a[2], 1)
        sp.points[1].co = (b[0], b[1], b[2], 1)
    obj = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(emission(name + "_mat", color))
    return obj


def make_panel(name, coords, x_off, color, half_h=0.11):
    """把沿手臂的采样点扩成正对相机的带状面（相机从 -Y 看 XZ 平面）。"""
    # coords 每两个一组代表同一截面（y=±0.15），取平均 x/z
    pairs = []
    for i in range(0, len(coords), 2):
        a, b = coords[i], coords[i + 1]
        pairs.append(((a[0] + b[0]) / 2, (a[2] + b[2]) / 2))
    verts = []
    faces = []
    for x, z in pairs:
        verts.append((x + x_off, 0, z + half_h))
        verts.append((x + x_off, 0, z - half_h))
    for i in range(len(pairs) - 1):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(emission(name + "_mat", color))
    return obj


# ---------------------------------------------------------------- 真实烘一遍
clear_scene()
arm_data = bpy.data.armatures.new("Arm")
arm = bpy.data.objects.new("Arm", arm_data)
bpy.context.collection.objects.link(arm)
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
root = arm_data.edit_bones.new("root")
root.head = (0, 0, 0); root.tail = (0, 0, 1)
ua = arm_data.edit_bones.new("upper_arm")
ua.head = (0, 0, 1); ua.tail = (1, 0, 1); ua.parent = root
la = arm_data.edit_bones.new("lower_arm")
la.head = (1, 0, 1); la.tail = (2, 0, 1); la.parent = ua
bpy.ops.object.mode_set(mode='OBJECT')

coords = [(-0.05, -0.15, 1.0), (-0.05, 0.15, 1.0),
          (0.80, -0.15, 1.0), (0.80, 0.15, 1.0),
          (1.60, -0.15, 1.0), (1.60, 0.15, 1.0)]
faces = [(0, 1, 3, 2), (2, 3, 5, 4)]
me = bpy.data.meshes.new("Mesh")
me.from_pydata(coords, [], faces)
me.update()
ob = bpy.data.objects.new("Mesh", me)
bpy.context.collection.objects.link(ob)
vg = ob.vertex_groups.new(name="upper_arm")
vg.add(list(range(len(coords))), 1.0, 'REPLACE')
mod = ob.modifiers.new("Armature", 'ARMATURE')
mod.object = arm

bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.shape_key_add(from_mix=False)
ob.data.shape_keys.key_blocks[0].name = "Basis"

arm.pose.bones["upper_arm"].rotation_mode = 'XYZ'
arm.pose.bones["upper_arm"].rotation_euler.x = -radians(36)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
ev = ob.evaluated_get(dg)
mesh_eval = ev.to_mesh()
baked = [tuple(v.co) for v in mesh_eval.vertices]
ev.to_mesh_clear()

bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply()
bpy.ops.object.mode_set(mode='OBJECT')

# 烘进后的骨架 A-Pose 静置位置（世界=骨架局部，变换已应用）
rest_after = {
    "root": (tuple(arm.data.bones["root"].head_local),
             tuple(arm.data.bones["root"].tail_local)),
    "upper_arm": (tuple(arm.data.bones["upper_arm"].head_local),
                  tuple(arm.data.bones["upper_arm"].tail_local)),
    "lower_arm": (tuple(arm.data.bones["lower_arm"].head_local),
                  tuple(arm.data.bones["lower_arm"].tail_local)),
}

# ---------------------------------------------------------------- 重建展示场景
clear_scene()
X_L, X_R = -2.5, 2.5

# T-Pose 骨架（原始坐标）
t_segments = [((0, 0, 0), (0, 0, 1)),
              ((0, 0, 1), (1, 0, 1)),
              ((1, 0, 1), (2, 0, 1))]
curve_lines("arm_T", [((a[0] + X_L, a[1], a[2]), (b[0] + X_L, b[1], b[2]))
                      for a, b in t_segments], (0.65, 0.68, 0.72, 1), 0.025)
make_panel("mesh_T", coords, X_L, (0.30, 0.62, 1.00, 1))

# A-Pose 骨架（烘进后的 rest）
a_segments = list(rest_after.values())
curve_lines("arm_A", [((a[0] + X_R, a[1], a[2]), (b[0] + X_R, b[1], b[2]))
                      for a, b in a_segments], (1.00, 0.72, 0.20, 1), 0.025)
make_panel("mesh_A", baked, X_R, (1.00, 0.32, 0.36, 1))

# 地面参考线
curve_lines("floor", [((X_L - 1.2, -0.02, 0), (X_L + 2.6, -0.02, 0)),
                      ((X_R - 1.2, -0.02, 0), (X_R + 2.6, -0.02, 0))],
            (0.18, 0.20, 0.24, 1), 0.008)

# 标签（用曲线拼简单字符太麻烦，改用文本对象，Workbench 渲染会显示）
def label(text, x, y, z, size=0.14):
    cu = bpy.data.curves.new("txt_" + text, 'FONT')
    cu.body = text
    cu.size = size
    cu.align_x = 'CENTER'
    obj = bpy.data.objects.new("txt_" + text, cu)
    bpy.context.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.rotation_euler = (radians(90), 0, 0)   # 面向 -Y 相机
    obj.data.materials.append(emission("txt_mat_" + text, (0.92, 0.94, 0.98, 1)))
    return obj

label("BEFORE  T-Pose", X_L + 0.5, -0.02, 1.75, 0.16)
label("AFTER  A-Pose", X_R + 0.5, -0.02, 1.75, 0.16)

# ---------------------------------------------------------------- 相机 / 渲染
scn = bpy.context.scene
scn.render.engine = 'BLENDER_WORKBENCH'
scn.display.shading.light = 'FLAT'
scn.display.shading.color_type = 'MATERIAL'
scn.display.shading.show_shadows = False
scn.display.shading.show_cavity = False
scn.render.film_transparent = False
scn.world.color = (0.06, 0.07, 0.09)

cam_data = bpy.data.cameras.new("Cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 8.6
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0, -10, 0.85)
target = Vector((0, 0, 0.85))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scn.camera = cam

scn.render.resolution_x = 1200
scn.render.resolution_y = 620
scn.render.resolution_percentage = 100
scn.render.image_settings.file_format = 'PNG'
scn.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("saved:", OUT)
