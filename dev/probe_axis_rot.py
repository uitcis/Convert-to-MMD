"""诊断：用成对骨向量求侧轴【方向】（而非从三个轴里挑一个）。

用法：
    blender --background --factory-startup --python dev/probe_axis_rot.py -- <model.blend> [...]

判据：
    每对 (L, R) 给出向量 v = head(L) - head(R)，它一定近似平行于侧轴。
    对全部 v 做鲁棒主方向（剔除离群配对后取均值），得到 3D 单位向量 s，
    其符号天然由「L 减 R」确定——不需要「左在正半轴」这类假设。

    轴对齐的骨架会给出 s ≈ (±1,0,0) 这类结果；旋转过的骨架给出
    一般方向（leviathan 实测 X 与 Y 分量各占一半）。
    同时输出 up 轴的候选：配对中点去掉 s 分量后的主方向。
"""
import os
import sys
import importlib.util

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "convert_to_mmd", os.path.join(ROOT, "__init__.py"),
    submodule_search_locations=[ROOT])
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["convert_to_mmd"] = _pkg
_spec.loader.exec_module(_pkg)

from convert_to_mmd.tools import mapping_core as core  # noqa: E402
from convert_to_mmd.tools.auto_bone_mapping import (  # noqa: E402
    build_features, detect_side_axis)

AXIS = "XYZ"


def unit(vector):
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 1e-12 else vector


def robust_side_vector(vectors):
    """成对骨向量的鲁棒主方向：先取均值方向，剔除夹角过大的配对再重算。"""
    stack = np.array(vectors)
    direction = unit(stack.mean(axis=0))
    for _ in range(4):
        cosine = (stack @ direction) / np.maximum(
            np.linalg.norm(stack, axis=1), 1e-12)
        keep = stack[cosine > 0.5]
        if len(keep) == len(stack):
            break
        stack = keep
        direction = unit(stack.mean(axis=0))
    return direction, len(stack)


def principal_up(points, side_vector):
    """去掉侧向分量后，点云第一主成分——身高方向。"""
    centred = points - points.mean(axis=0)
    flat = centred - np.outer(centred @ side_vector, side_vector)
    if len(flat) < 3:
        return np.zeros(3)
    eigvals, eigvecs = np.linalg.eigh(np.cov(flat.T))
    return unit(eigvecs[:, int(np.argmax(eigvals))])


def endpoint_widths(points, up_vector, side_vector):
    """沿 up 取最低/最高 10% 的骨，量它们在侧轴上的散布宽度。

    解剖事实：脚端左右分开（两条腿），头端只有一个头。姿势无关
    （除非双手举过头顶）。用于确定 up 的符号。
    """
    projection = points @ up_vector
    order = np.argsort(projection)
    count = max(3, len(order) // 10)
    low = points[order[:count]] @ side_vector
    high = points[order[-count:]] @ side_vector
    return float(low.std()), float(high.std())


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    for model in argv[argv.index("--") + 1:]:
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, _diagonal, _z_min, up_axis = build_features(armature)
            if not features or span <= 0:
                continue
            names = list(features)
            points = {n: np.array(features[n].head, dtype=float) for n in names}
            pairs = [(l, r) for l, r in core._named_side_pairs(
                features, include_middle=True)
                if l in points and r in points]
            if len(pairs) < 3:
                print(f"  AXIS {armature.name:<28s} bones={len(features):<5d} "
                      f"配对数={len(pairs)} 不足，跳过")
                continue
            vectors = [points[l] - points[r] for l, r in pairs]
            side_vec, used = robust_side_vector(vectors)
            side_axis = detect_side_axis(features, up_axis)

            # 侧向投影的分离度：成对骨在侧轴上的间距均值 / 骨架尺度
            separation = np.mean([abs(v @ side_vec) for v in vectors])

            # up 候选 A：配对中点（现状判据的输入）
            midpoints = np.array([(points[l] + points[r]) * 0.5
                                  for l, r in pairs])
            up_mid = principal_up(midpoints, side_vec)
            # up 候选 B：全部骨点（点云形状先验：身高跨度 >> 体厚）
            cloud = np.array([points[n] for n in names], dtype=float)
            up_all = principal_up(cloud, side_vec)

            sign_low, sign_high = endpoint_widths(cloud, up_all, side_vec)
            flipped = sign_low < sign_high

            print(f"  AXIS {armature.name:<28s} bones={len(features):<5d} "
                  f"pairs={len(pairs)}->{used}")
            print(f"    CUR  side={AXIS[side_axis]} "
                  f"up={AXIS[up_axis]}")
            print(f"    SIDE vec=({side_vec[0]:+.3f} {side_vec[1]:+.3f} "
                  f"{side_vec[2]:+.3f}) 分离度={separation:.3f} "
                  f"轴对齐={'是' if abs(side_vec).max() > 0.95 else '否'}")
            for label, vector in (("配对中点", up_mid), ("全骨点", up_all)):
                print(f"    UP-{label} vec=({vector[0]:+.3f} "
                      f"{vector[1]:+.3f} {vector[2]:+.3f}) "
                      f"轴对齐={'是' if abs(vector).max() > 0.95 else '否'}")
            print(f"    符号 低端侧宽={sign_low:.3f} 高端侧宽={sign_high:.3f} "
                  f"=> {'需翻转（低端更窄，说明脚在高端）' if flipped else '朝向正确'}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
