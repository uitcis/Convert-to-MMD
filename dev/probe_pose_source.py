"""判断一套骨架的「当前姿势」到底来自哪里。

三个层次要分清：
  ① rest pose（编辑模式骨骼 head_local/tail_local）—— 文件里存的就是这个；
  ② pose（pose.bones[].location/rotation/scale）—— 由动作/NLA/手动摆出来；
  ③ 动作数据（animation_data.action、NLA tracks、drivers）—— 随时间变化。

用法：
  blender -b --factory-startup --python dev/probe_pose_source.py -- model.blend
"""
import sys

import bpy
from mathutils import Vector


def describe(path):
    print(f"MODEL {path}")
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    print(f"  SCENE frame_current={scene.frame_current} "
          f"range={scene.frame_start}-{scene.frame_end}")

    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE':
            continue
        data = obj.data
        print(f"  ARM {obj.name} bones={len(data.bones)} "
              f"pose_position={data.pose_position}")

        # ① rest 是否本身就是这个姿态
        print(f"    REST 样本: " + " ".join(
            f"{b}={tuple(round(v, 2) for v in data.bones[b].head_local)}"
            for b in list(data.bones.keys())[:3] if b in data.bones))

        # ③ 动作数据
        anim = obj.animation_data
        if anim is None:
            print("    ANIM 无 animation_data")
        else:
            act = anim.action
            print(f"    ANIM action={act.name if act else None} "
                  f"nla={len(anim.nla_tracks)} "
                  f"drivers={len(anim.drivers)}")
            if act:
                curves = getattr(act, "fcurves", [])
                print(f"      fcurves={len(curves)} "
                      f"range={tuple(round(v, 1) for v in act.frame_range)}")
                bone_curves = [c for c in curves
                               if c.data_path.startswith("pose.bones[")]
                print(f"      其中作用于 pose.bones 的={len(bone_curves)}")
                if bone_curves:
                    print("      样例: " + "; ".join(
                        f"{c.data_path}[{c.array_index}]"
                        f"@{len(c.keyframe_points)}key"
                        for c in bone_curves[:3]))
            for track in anim.nla_tracks:
                print(f"      NLA {track.name} strips={len(track.strips)}")

        # ② pose 层是否被摆过
        moved = []
        for pbone in obj.pose.bones:
            t = pbone.matrix_basis.to_translation()
            q = pbone.matrix_basis.to_quaternion()
            s = pbone.matrix_basis.to_scale()
            if (t.length > 1e-6
                    or abs(q.w - 1.0) > 1e-6
                    or any(abs(v - 1.0) > 1e-6 for v in s)):
                moved.append((pbone.name, round(t.length, 4),
                              round(q.angle, 3)))
        print(f"    POSE 非单位 matrix_basis 的骨={len(moved)}/{len(obj.pose.bones)}")
        for name, tr, ang in moved[:5]:
            print(f"      {name} 位移={tr} 旋转={ang}rad")

        # 骨骼约束（也可能把姿态掰歪）
        constrained = [pb.name for pb in obj.pose.bones if pb.constraints]
        print(f"    CONSTRAINT 带约束的骨={len(constrained)}")
        if constrained:
            print("      " + ", ".join(constrained[:5]))

        # rest 与 posed 的实际差（关键骨）
        probes = ["DEF-head", "DEF-spine", "DEF-foot.L", "DEF-hand.L"]
        deltas = []
        for name in probes:
            bone = data.bones.get(name)
            pbone = obj.pose.bones.get(name)
            if bone is None or pbone is None:
                continue
            delta = (pbone.head - bone.head_local).length
            deltas.append(f"{name}={delta:.4f}")
        print(f"    DIFF rest→posed: {' '.join(deltas) or '无匹配骨'}")
    sys.stdout.flush()


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for item in args:
        describe(item)
