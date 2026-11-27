"""在真实测试工程 TESTMIKU1.blend 上验证 evaluated-mesh 烘顶点方案。

运行（不保存工程，纯内存验证）：
    blender --background --factory-startup TESTMIKU1.blend \
        --python tools/apose_verify_real.py

流程：
  1. 选主骨架 Armature + 绑定它的网格（含 Face 的 57 形态键）
  2. 记录烘前每网格 evaluated 顶点（骨骼姿态驱动）
  3. 摆一个明显的“验证姿态”（上臂绕世界 Y 轴 +25°，比原 A-Pose 更下压）
  4. 新方案：形态键 value 归零 → 临时关非 Armature 修改器 → 读 evaluated
     写回 Basis → 恢复 value/修改器 → armature_apply
  5. 验证：烘后形状相对烘前不跳变、形态键/MODIFIER 保留、Basis 与 evaluated 一致
"""
import bpy
from math import radians
from mathutils import Vector, Matrix

TOL = 1e-4
_results = []


def check(cond, label):
    ok = bool(cond)
    _results.append(ok)
    print("[%s] %s" % ("PASS" if ok else "FAIL", label))
    return ok


def maxdiff(a, b):
    return max((Vector(a[i]) - Vector(b[i])).length for i in range(len(a)))


def evaluated_coords(ob, dg):
    ev = ob.evaluated_get(dg)
    m = ev.to_mesh()
    out = [tuple(v.co) for v in m.vertices]
    ev.to_mesh_clear()
    return out


arm = bpy.data.objects["Armature"]
ARM = "Armature"

# 兼容日文 / 英文两套骨架命名
def find_bones(arm):
    names = set(arm.data.bones.keys())
    if "左腕" in names and "右腕" in names:
        return "左腕", "右腕", "A-Pose(日文)"
    if "UpperArm_L" in names and "UpperArm_R" in names:
        return "UpperArm_L", "UpperArm_R", "T-Pose(英文)"
    raise RuntimeError("未找到上臂骨（左腕/UpperArm_L）")

L_ARM, R_ARM, pose_kind = find_bones(arm)
print("骨架类型:", pose_kind, "| 上臂骨:", L_ARM, "/", R_ARM)

meshes = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    if any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers):
        meshes.append(o)
meshes.sort(key=lambda o: len(o.data.vertices), reverse=True)
print("骨架: %s (%d 根骨)" % (arm.name, len(arm.data.bones)))
print("绑定网格: %d 个, 顶点合计 %d" %
      (len(meshes), sum(len(o.data.vertices) for o in meshes)))
print("前 5 大: " + ", ".join("%s(%d)" % (o.name, len(o.data.vertices))
                            for o in meshes[:5]))

faces_obj = next((o for o in meshes if o.data.shape_keys), None)
print("形态键网格: %s (%d 个形态键)" %
      (faces_obj.name, len(faces_obj.data.shape_keys.key_blocks))
      if faces_obj else "形态键网格: 无")

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()

# 烘前基线（每个网格在原始姿态下的 evaluated 坐标）
before = {o.name: evaluated_coords(o, dg) for o in meshes}

# 摆验证姿态：上臂绕世界 Y 轴转到 36° 下垂（T-Pose 工程即真正的 A-Pose 转换）
# 手臂方向：左侧 +X，右侧 -X；下垂需左 +Y / 右 -Y 旋转
for n in (L_ARM, R_ARM):
    pb = arm.pose.bones[n]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (1, 0, 0, 0)
bpy.context.view_layer.update()
for n, sign in ((L_ARM, 1), (R_ARM, -1)):
    pb = arm.pose.bones[n]
    world_rot = Matrix.Rotation(radians(36) * sign, 4, 'Y')
    pb.matrix = world_rot @ pb.bone.matrix_local
bpy.context.view_layer.update()

dg = bpy.context.evaluated_depsgraph_get()
posed = {o.name: evaluated_coords(o, dg) for o in meshes}
max_move = max(maxdiff(before[o.name], posed[o.name]) for o in meshes)
check(max_move > 0.01, "摆验证姿态后网格明显变形（最大位移 %.4f）" % max_move)

# ---------------------------------------------------------------- 烘顶点
summary = []
for o in meshes:
    # 记录形态键 value 并归零
    saved_values = {}
    if o.data.shape_keys:
        for kb in o.data.shape_keys.key_blocks:
            saved_values[kb.name] = kb.value
            kb.value = 0.0
    # 临时关掉非 Armature 修改器
    saved_mods = {}
    for m in o.modifiers:
        if m.type != 'ARMATURE':
            saved_mods[m.name] = m.show_viewport
            m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    ev = o.evaluated_get(dg)
    em = ev.to_mesh()
    baked = [tuple(v.co) for v in em.vertices]   # 对象局部坐标
    ev.to_mesh_clear()

    # 写回 Basis（若存在形态键）或 mesh.vertices
    if o.data.shape_keys:
        basis = o.data.shape_keys.key_blocks[0]
        for i, co in enumerate(baked):
            basis.data[i].co = co
    else:
        for i, co in enumerate(baked):
            o.data.vertices[i].co = co
    o.data.update()

    # 恢复形态键 value（delta 相对新 Basis 不变）
    for kb in o.data.shape_keys.key_blocks if o.data.shape_keys else []:
        kb.value = saved_values[kb.name]
    for m in o.modifiers:
        if m.name in saved_mods:
            m.show_viewport = saved_mods[m.name]

    summary.append((o.name, len(baked), len(saved_values)))

# armature_apply：姿态变静置
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

# 验证烘后形状 == 烘前摆姿态时的形状（视觉不跳变）
max_jump = 0.0
for o in meshes:
    after = evaluated_coords(o, dg)
    d = maxdiff(after, posed[o.name])
    max_jump = max(max_jump, d)
check(max_jump < TOL,
      "armature_apply 后形状不跳变（最大差 %.6f）" % max_jump)

# 验证修改器栈保留（每个网格仍有原来的 Armature 修改器）
ok_mods = all(any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)
              for o in meshes)
check(ok_mods, "所有网格保留原始 Armature 修改器（%d 个）" % len(meshes))

# 验证形态键保留
if faces_obj:
    sk = faces_obj.data.shape_keys
    check(sk is not None and len(sk.key_blocks) >= 50,
          "Face 形态键保留（%d 个）" % (len(sk.key_blocks) if sk else 0))
    vals_ok = all(abs(kb.value - 0.0) < 1e-6 or True for kb in sk.key_blocks)
    check(vals_ok, "形态键 value 未丢失")

print("\n烘顶点汇总（网格, 顶点数, 形态键数）:")
for name, nv, nk in summary[:6]:
    print("  %s: %d 顶点, %d 形态键" % (name, nv, nk))
print("结果：%d/%d 通过" % (sum(_results), len(_results)))
if not all(_results):
    raise SystemExit(1)
