"""最小 demo：验证「用 evaluated mesh 把骨骼姿态烘进网格顶点」方案。

运行（后台模式，无需界面）：
    blender --background --factory-startup --python tools/apose_bake_demo.py

验证链路：
    A. 摆姿态后 evaluated 顶点确实偏离 Basis（蒙皮生效）
    B. 形态键 value 归零后读 evaluated 顶点，写回 Basis 成功
    C. armature_apply 之后 evaluated 顶点 == Basis（视觉形状不跳变）
    D. 修改器栈保持不变（原始 Armature 修改器还在）
    E. 形态键 value 正确恢复
    F. 反例：形态键 value 非 0 时直接烘会污染 Basis
"""
import bpy
from math import radians
from mathutils import Vector

TOL = 1e-4
_results = []


def check(cond, label):
    ok = bool(cond)
    _results.append(ok)
    print("[%s] %s" % ("PASS" if ok else "FAIL", label))
    return ok


def maxdiff(a, b):
    return max((Vector(a[i]) - Vector(b[i])).length for i in range(len(a)))


def basis_coords():
    kb = ob.data.shape_keys.key_blocks
    return [tuple(kb[0].data[i].co) for i in range(len(kb[0].data))]


def key_coords(name):
    kb = ob.data.shape_keys.key_blocks[name]
    return [tuple(v.co) for v in kb.data]


# ---------------------------------------------------------------- 建场景
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

arm_data = bpy.data.armatures.new("DemoArm")
arm = bpy.data.objects.new("DemoArm", arm_data)
bpy.context.collection.objects.link(arm)
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')

root = arm_data.edit_bones.new("root")
root.head = (0, 0, 0)
root.tail = (0, 0, 1)
ua = arm_data.edit_bones.new("upper_arm")
ua.head = (0, 0, 1)
ua.tail = (1, 0, 1)          # T-Pose：沿 +X 水平
ua.parent = root
la = arm_data.edit_bones.new("lower_arm")
la.head = (1, 0, 1)
la.tail = (2, 0, 1)
la.parent = ua
bpy.ops.object.mode_set(mode='OBJECT')

# 网格：沿手臂的一段带子，全部绑 upper_arm
coords = [(-0.05, -0.15, 1.0), (-0.05, 0.15, 1.0),
          (0.80, -0.15, 1.0), (0.80, 0.15, 1.0),
          (1.60, -0.15, 1.0), (1.60, 0.15, 1.0)]
faces = [(0, 1, 3, 2), (2, 3, 5, 4)]
mesh = bpy.data.meshes.new("DemoMesh")
mesh.from_pydata(coords, [], faces)
mesh.update()
ob = bpy.data.objects.new("DemoMesh", mesh)
bpy.context.collection.objects.link(ob)

vg = ob.vertex_groups.new(name="upper_arm")
vg.add(list(range(len(coords))), 1.0, 'REPLACE')
mod = ob.modifiers.new("Armature", 'ARMATURE')
mod.object = arm

# 形态键：Key1 把末两个顶点抬高 0.4，模拟表情形变
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.shape_key_add(from_mix=False)
ob.data.shape_keys.key_blocks[0].name = "Basis"
bpy.ops.object.shape_key_add(from_mix=False)
k1 = ob.data.shape_keys.key_blocks[1]
k1.name = "Key1"
for i in (4, 5):
    k1.data[i].co.z += 0.4
k1.value = 0.0

# ---------------------------------------------------------------- 摆 A-Pose
arm.pose.bones["upper_arm"].rotation_mode = 'XYZ'
# 骨骼局部 Y 沿骨长方向，绕 Y 是扭转；绕局部 X 才是手臂在 XZ 平面下垂
arm.pose.bones["upper_arm"].rotation_euler.x = -radians(36)   # 下垂 36°
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()


def eval_coords():
    ev = ob.evaluated_get(depsgraph)
    m = ev.to_mesh()
    out = [tuple(v.co) for v in m.vertices]
    ev.to_mesh_clear()
    return out


base_before = basis_coords()
key1_before = key_coords("Key1")
delta = [Vector(key1_before[i]) - Vector(base_before[i])
         for i in range(len(base_before))]

# 反例基准：value=1 时 evaluated 包含形态键形变
k1.value = 1.0
bpy.context.view_layer.update()
ev_with_key = eval_coords()
k1.value = 0.0
bpy.context.view_layer.update()
ev_basis = eval_coords()

check(maxdiff(base_before, ev_basis) > 0.05,
      "A. 蒙皮生效：evaluated 偏离 Basis %.4f" % maxdiff(base_before, ev_basis))
check(maxdiff(ev_basis, ev_with_key) > 0.1,
      "F. 反例成立：形态键 value=1 与 value=0 的 evaluated 相差 %.4f" %
      maxdiff(ev_basis, ev_with_key))

# ---------------------------------------------------------------- 烘进
# 关键：value 归零状态下读 evaluated（此时只有骨骼变形），写回 Basis
bpy.context.view_layer.objects.active = ob
basis = ob.data.shape_keys.key_blocks[0]
for i, co in enumerate(ev_basis):
    basis.data[i].co = co

# 形态键绝对坐标 = 新 Basis + 原 delta（形变模式保持不变）
k1_new = ob.data.shape_keys.key_blocks["Key1"]
for i, d in enumerate(delta):
    k1_new.data[i].co = Vector(basis.data[i].co) + d

saved_values = {kb.name: kb.value for kb in ob.data.shape_keys.key_blocks}
for kb in ob.data.shape_keys.key_blocks:
    kb.value = 0.0
check(maxdiff(basis_coords(), ev_basis) < TOL,
      "B. Basis 已写为 evaluated 顶点（差 %.6f）" %
      maxdiff(basis_coords(), ev_basis))

# ---------------------------------------------------------------- armature_apply
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()   # apply 后依赖图需刷新

ev_after = eval_coords()
check(maxdiff(ev_after, basis_coords()) < TOL,
      "C. armature_apply 后形状不跳变：evaluated == Basis（差 %.6f）" %
      maxdiff(ev_after, basis_coords()))

mods = [m for m in ob.modifiers if m.type == 'ARMATURE' and m.object == arm]
check(len(mods) == 1,
      "D. 修改器栈不变：原始 Armature 修改器仍在（数量 %d）" % len(mods))

for kb in ob.data.shape_keys.key_blocks:
    kb.value = saved_values[kb.name]
check(all(kb.value == saved_values[kb.name]
          for kb in ob.data.shape_keys.key_blocks),
      "E. 形态键 value 已恢复")

k1_after = key_coords("Key1")
delta_after = [Vector(k1_after[i]) - Vector(basis_coords()[i])
               for i in range(len(k1_after))]
check(max([(delta_after[i] - delta[i]).length for i in range(len(delta))]) < TOL,
      "G. 形态键 delta 保持不变")

# ---------------------------------------------------------------- 汇总
print("\n结果：%d/%d 通过" % (sum(_results), len(_results)))
if not all(_results):
    raise SystemExit(1)
