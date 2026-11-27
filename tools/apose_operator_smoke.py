"""最小场景端到端 smoke test：构造骨架+带形态键网格，直接调用插件 operator。

用于在没有 .blend 工程文件的 Blender 版本（4.0/4.2）上验证兼容性。

运行：
    blender --background --factory-startup --python tools/apose_operator_smoke.py
"""
import bpy
import importlib.util
import os
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "ctm_addon_smoke"
_results = []


def check(cond, label):
    ok = bool(cond)
    _results.append(ok)
    print("[%s] %s" % ("PASS" if ok else "FAIL", label))


def maxdiff(a, b):
    return max((Vector(a[i]) - Vector(b[i])).length for i in range(len(a)))


def coords(ob):
    src = ob.data.shape_keys.key_blocks[0].data if ob.data.shape_keys else ob.data.vertices
    return [tuple(v.co) for v in src]


# ---------------------------------------------------------------- 最小场景
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

ad = bpy.data.armatures.new("SmokeArm")
arm = bpy.data.objects.new("SmokeArm", ad)
bpy.context.collection.objects.link(arm)
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
spec = [
    ("Root", None, (0, 0, 0), (0, 0, 0.6)),
    ("Spine", "Root", (0, 0, 0.6), (0, 0, 1.2)),
    ("Neck", "Spine", (0, 0, 1.2), (0, 0, 1.5)),
    ("UpperArm_L", "Spine", (0.1, 0, 1.15), (1.0, 0, 1.15)),
    ("LowerArm_L", "UpperArm_L", (1.0, 0, 1.15), (1.8, 0, 1.15)),
    ("UpperArm_R", "Spine", (-0.1, 0, 1.15), (-1.0, 0, 1.15)),
    ("LowerArm_R", "UpperArm_R", (-1.0, 0, 1.15), (-1.8, 0, 1.15)),
]
for name, parent, head, tail in spec:
    b = ad.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = ad.edit_bones[parent]
bpy.ops.object.mode_set(mode='OBJECT')

verts, faces = [], []
for i in range(9):
    x = -1.8 + 0.45 * i
    verts.extend([(x, -0.12, 1.15), (x, 0.12, 1.15)])
for i in range(8):
    faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
me = bpy.data.meshes.new("SmokeMesh")
me.from_pydata(verts, [], faces)
me.update()
mesh = bpy.data.objects.new("SmokeMesh", me)
bpy.context.collection.objects.link(mesh)
gL = mesh.vertex_groups.new(name="UpperArm_L")
gR = mesh.vertex_groups.new(name="UpperArm_R")
for i, v in enumerate(me.vertices):
    (gL if v.co.x > 0 else gR).add([i], 1.0, 'REPLACE')
mod = mesh.modifiers.new("Armature", 'ARMATURE')
mod.object = arm
mesh.parent = arm

bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.shape_key_add(from_mix=False)
bpy.ops.object.shape_key_add(from_mix=False)
k1 = mesh.data.shape_keys.key_blocks[-1]
k1.name = "Smile"
for i, v in enumerate(k1.data):
    if v.co.x > 0:
        v.co.y += 0.05
print("VER", bpy.app.version_string, "| 骨架", len(arm.data.bones), "骨, 网格", len(verts), "顶点")

# ---------------------------------------------------------------- 加载插件
spec_mod = importlib.util.spec_from_file_location(
    PKG, os.path.join(ROOT, "__init__.py"), submodule_search_locations=[ROOT])
mod_plugin = importlib.util.module_from_spec(spec_mod)
sys.modules[PKG] = mod_plugin
spec_mod.loader.exec_module(mod_plugin)
mod_plugin.register()

sc = bpy.context.scene
for k, v in {
    "upper_body_bone": "Spine", "neck_bone": "Neck",
    "left_upper_arm_bone": "UpperArm_L", "right_upper_arm_bone": "UpperArm_R",
    "left_lower_arm_bone": "LowerArm_L", "right_lower_arm_bone": "LowerArm_R",
}.items():
    setattr(sc, k, v)

before = coords(mesh)
before_mods = [(m.name, m.type) for m in mesh.modifiers]
before_keys = [(kb.name, kb.value) for kb in mesh.data.shape_keys.key_blocks]

bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
ret = bpy.ops.object.convert_to_apose()
print("operator", ret)
check('FINISHED' in ret, "operator 返回 FINISHED")
check(maxdiff(before, coords(mesh)) > 0.01,
      "网格顶点已烘入（最大差 %.4f）" % maxdiff(before, coords(mesh)))
check([(m.name, m.type) for m in mesh.modifiers] == before_mods,
      "修改器栈保留")
check([(kb.name, kb.value) for kb in mesh.data.shape_keys.key_blocks] == before_keys,
      "形态键数量与 value 保留")
for n in ("UpperArm_L", "UpperArm_R"):
    m2 = arm.pose.bones[n].matrix_basis
    dev = max(abs(m2[i][j] - (1.0 if i == j else 0.0)) for i in range(4) for j in range(4))
    check(dev < 1e-3, "上臂姿态归零 %s" % n)

print("结果：%d/%d 通过" % (sum(_results), len(_results)))
if not all(_results):
    raise SystemExit(1)
