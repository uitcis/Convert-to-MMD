"""端到端验证：直接调用插件的真实 operator（object.convert_to_apose）。

运行：
    blender --background --factory-startup TESTMIKU.blend \
        --python tools/apose_operator_verify.py

验证点：
  1. operator 正常返回 FINISHED
  2. 网格顶点确实被烘入（Basis 变化明显）
  3. armature_apply 后上臂姿态归零
  4. 修改器栈完整保留（不再有临时 _copy 修改器）
  5. 形态键数量与 value 保留
  6. 烘后不跳变（evaluated 与写入的 Basis 一致）
"""
import bpy
import importlib.util
import os
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "ctm_addon_verify"

_results = []


def check(cond, label):
    ok = bool(cond)
    _results.append(ok)
    print("[%s] %s" % ("PASS" if ok else "FAIL", label))
    return ok


def maxdiff(a, b):
    return max((Vector(a[i]) - Vector(b[i])).length for i in range(len(a)))


def eval_coords(ob, dg):
    ev = ob.evaluated_get(dg)
    m = ev.to_mesh()
    try:
        return [tuple(v.co) for v in m.vertices]
    finally:
        ev.to_mesh_clear()


def basis_coords(ob):
    sk = ob.data.shape_keys
    src = sk.key_blocks[0].data if sk else ob.data.vertices
    return [tuple(v.co) for v in src]


# ---------------------------------------------------------------- 加载插件
if PKG not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PKG, os.path.join(ROOT, "__init__.py"), submodule_search_locations=[ROOT])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    mod.register()
print("插件加载完成:", PKG)

def _bound_mesh_count(o):
    return sum(1 for x in bpy.data.objects if x.type == 'MESH'
               and any(m.type == 'ARMATURE' and m.object == o for m in x.modifiers))


# 工程里可能有多套骨架（含隐藏备份），选绑定网格最多的那套
candidates = [o for o in bpy.data.objects if o.type == 'ARMATURE']
arm = max(candidates, key=_bound_mesh_count)
names = set(arm.data.bones.keys())
JP = "左腕" in names
FIELDS = {
    "upper_body_bone": "上半身" if JP else "Spine",
    "neck_bone": "首" if JP else "Neck",
    "left_upper_arm_bone": "左腕" if JP else "UpperArm_L",
    "right_upper_arm_bone": "右腕" if JP else "UpperArm_R",
    "left_lower_arm_bone": "左ひじ" if JP else "LowerArm_L",
    "right_lower_arm_bone": "右ひじ" if JP else "LowerArm_R",
}
missing = [k for k, v in FIELDS.items() if v not in names]
if missing:
    raise RuntimeError("骨骼缺失: %s" % ", ".join(missing))
sc = bpy.context.scene
for k, v in FIELDS.items():
    setattr(sc, k, v)
print("骨架 %s (%d 骨), 字段 %s" % (arm.name, len(arm.data.bones), FIELDS))

meshes = [o for o in bpy.data.objects
          if o.type == 'MESH'
          and any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]
meshes = [o for o in meshes if len(o.data.vertices) > 100]
print("绑定网格 %d 个, 顶点合计 %d" %
      (len(meshes), sum(len(o.data.vertices) for o in meshes)))

# 烘前上臂仰角：日文工程本身就是 A-Pose，此时 Basis 不变是正确行为
from math import atan2, degrees, hypot
pre_elev = []
for n in (FIELDS["left_upper_arm_bone"], FIELDS["right_upper_arm_bone"]):
    pb = arm.pose.bones[n]
    mw = arm.matrix_world
    d = (mw @ pb.tail - mw @ pb.head).normalized()
    pre_elev.append(degrees(atan2(d.z, hypot(d.x, d.y))))
already_apose = all(abs(e + 36.0) < 1.0 for e in pre_elev)
print("烘前上臂仰角:", [round(e, 2) for e in pre_elev],
      "| 已是 A-Pose:", already_apose)

# 烘前快照
before_basis = {o.name: basis_coords(o) for o in meshes}
before_mods = {o.name: [(m.name, m.type) for m in o.modifiers] for o in meshes}
before_keys = {o.name: ([(kb.name, kb.value) for kb in o.data.shape_keys.key_blocks]
                        if o.data.shape_keys else []) for o in meshes}

# ---------------------------------------------------------------- 调用 operator
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
ret = bpy.ops.object.convert_to_apose()
print("operator 返回:", ret)
check('FINISHED' in ret, "operator 返回 FINISHED")

# ---------------------------------------------------------------- 验证
changed = 0
for o in meshes:
    if maxdiff(before_basis[o.name], basis_coords(o)) > 0.01:
        changed += 1
check(changed >= 1 or already_apose,
      "网格顶点已烘入（%d/%d 个网格 Basis 改变；已是 A-Pose 则无需改变）"
      % (changed, len(meshes)))

for n in (FIELDS["left_upper_arm_bone"], FIELDS["right_upper_arm_bone"]):
    pb = arm.pose.bones[n]
    rot = max(abs(pb.matrix_basis[i][j] - (1.0 if i == j else 0.0))
              for i in range(4) for j in range(4))
    check(rot < 1e-3, "上臂姿态已归零（%s，matrix_basis 偏差 %.6f）" % (n, rot))

mods_ok = True
for o in meshes:
    cur = [(m.name, m.type) for m in o.modifiers]
    if cur != before_mods[o.name]:
        print("  修改器变化:", o.name, before_mods[o.name], "->", cur)
        mods_ok = False
check(mods_ok, "修改器栈完整保留（无 _copy 残留）")

keys_ok = True
for o in meshes:
    cur = ([(kb.name, kb.value) for kb in o.data.shape_keys.key_blocks]
           if o.data.shape_keys else [])
    if cur != before_keys[o.name]:
        old = before_keys[o.name]
        print("  形态键变化:", o.name, len(old), "->", len(cur))
        if len(old) == len(cur):
            diffs = [(b[0], round(b[1], 6), round(c[1], 6))
                     for b, c in zip(old, cur)
                     if b[0] != c[0] or abs(b[1] - c[1]) > 1e-6]
            print("    value 差异:", diffs[:8], "共", len(diffs))
        keys_ok = False
check(keys_ok, "形态键数量与 value 保留")

# 烘后不跳变：evaluated 与写入的 Basis 一致（仅当上臂外骨骼姿态为 rest）
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
max_jump = 0.0
for o in meshes:
    if o.data.shape_keys and any(abs(kb.value) > 1e-6
                                 for kb in o.data.shape_keys.key_blocks[1:]):
        continue
    max_jump = max(max_jump, maxdiff(eval_coords(o, dg), basis_coords(o)))
check(max_jump < 1e-3, "烘后不跳变（最大差 %.6f）" % max_jump)

print("\n结果：%d/%d 通过" % (sum(_results), len(_results)))
if not all(_results):
    raise SystemExit(1)
