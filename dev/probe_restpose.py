"""诊断：区分「rest pose 畸形」与「pose 被摆歪」。

用法：
    blender --background --factory-startup --python dev/probe_restpose.py -- <model.blend> [...]

输出三组信息：
    1. 骨架对象的变换（object matrix）与 pose_position 设置；
    2. 有多少 pose bone 带非单位变换（即 pose 模式被摆过）；
    3. 关键骨的 rest（head_local）与 posed（pose.bones[].head）坐标对比。

算法读的是 head_local（rest），所以第 3 组里 rest 两列的差异才是
真正影响映射的数据；若 rest 本身就左右不对称，重置 pose 也无济于事。
"""
import os
import sys

import bpy

CHECK = ("head", "neck", "spine", "chest", "hip", "pelvis",
         "shoulder.L", "shoulder.R", "hand.L", "hand.R",
         "foot.L", "foot.R", "thigh.L", "thigh.R", "eye.L")


def find_bone(bones, key):
    """按后缀模糊匹配（骨架命名前缀不统一）。"""
    for bone in bones:
        name = bone.name.lower()
        if name.endswith(key.lower()) or name == key.lower():
            return bone
    for bone in bones:
        if key.lower() in bone.name.lower():
            return bone
    return None


def is_identity(matrix):
    return all(abs(matrix[i][j] - (1.0 if i == j else 0.0)) < 1e-5
               for i in range(4) for j in range(4))


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    for model in argv[argv.index("--") + 1:]:
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            data = armature.data
            print(f"  ARM {armature.name} bones={len(data.bones)} "
                  f"pose_position={data.pose_position}")
            print(f"    obj loc={tuple(round(v, 3) for v in armature.location)} "
                  f"rot={tuple(round(v, 3) for v in armature.rotation_euler)} "
                  f"scale={tuple(round(v, 3) for v in armature.scale)}")
            print(f"    matrix_world=单位阵? {is_identity(armature.matrix_world)}")

            posed = [pb for pb in armature.pose.bones
                     if not is_identity(pb.matrix_basis)]
            print(f"    pose 有非单位变换的骨: {len(posed)}/{len(armature.pose.bones)}")
            for pb in posed[:4]:
                quat = tuple(round(v, 3) for v in pb.rotation_quaternion)
                print(f"      {pb.name:<24s} quat={quat} "
                      f"loc={tuple(round(v, 3) for v in pb.location)}")

            print(f"    {'骨':<20s} {'rest x/y/z':<26s} {'posed x/y/z':<26s} 差")
            for key in CHECK:
                bone = find_bone(data.bones, key)
                if bone is None:
                    continue
                rest = bone.head_local
                pose_bone = armature.pose.bones.get(bone.name)
                posed_head = pose_bone.head if pose_bone else rest
                delta = (posed_head - rest).length
                flag = "  <- 差异" if delta > 1e-4 else ""
                print(f"    {bone.name:<20s} "
                      f"{rest.x:7.3f} {rest.y:7.3f} {rest.z:7.3f}   "
                      f"{posed_head[0]:7.3f} {posed_head[1]:7.3f} "
                      f"{posed_head[2]:7.3f}   {delta:.4f}{flag}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
