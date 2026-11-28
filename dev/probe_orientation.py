"""诊断骨架方向判定：对比「命名配对」与「几何对称面」两种判据。

用法：
    blender --background --factory-startup --python dev/probe_orientation.py -- <model.blend> [...]

每套骨架输出：
    ORI  <骨架> bones=<n>
      CUR  up=? side=? pairs=?        现状判据（依赖左右命名配对）
      SYM  各轴 <near> <sym> <side_sym>   对称面检测（完全不用命名）
      PCA  主轴跨度与特征值
      AGREE / CONFLICT

SYM 的含义：对每个候选轴 a，把骨点集关于平面 x_a = median 做镜像，
求镜像点到原始点集的最近邻平均距离（除以骨架尺度）。骨架左右对称时，
**只有真正的侧轴**镜像残差接近 0——左右骨严格成对，误差是零；
另两轴会差出一个体厚 / 身高量级。这条判据不读任何骨名。
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


def mirror_residual(points, axis, centre):
    """镜像到平面 points[:,axis]=centre 后，到原点集的最近邻平均距离。

    用按该轴排序 + 二分定位候选窗口，避免 n² 距离矩阵。
    """
    order = np.argsort(points[:, axis])
    sorted_points = points[order]
    mirrored = points.copy()
    mirrored[:, axis] = 2.0 * centre - mirrored[:, axis]
    target = mirrored[:, axis]
    index = np.searchsorted(sorted_points[:, axis], target)
    best = np.full(len(points), np.inf)
    for offset in range(-3, 4):
        cursor = np.clip(index + offset, 0, len(points) - 1)
        candidate = sorted_points[cursor]
        distance = np.linalg.norm(mirrored - candidate, axis=1)
        best = np.minimum(best, distance)
    return float(best.mean())


def symmetry_report(points, scale):
    """返回 {轴: (贴平面比例, 镜像残差/尺度)}。"""
    report = {}
    n = len(points)
    for axis in range(3):
        values = points[:, axis]
        centre = float(np.median(values))
        tolerance = scale * 0.04
        near = float(np.mean(np.abs(values - centre) <= tolerance))
        residual = mirror_residual(points, axis, centre) / scale
        report[axis] = (near, residual)
    return report


def pair_geometry(points_by_name, features):
    """成对骨中点（现状 up 判据的输入），用于对照。"""
    pairs = []
    for left, right in core._named_side_pairs(features, include_middle=True):
        if left in points_by_name and right in points_by_name:
            a, b = points_by_name[left], points_by_name[right]
            pairs.append((a + b) * 0.5)
    return np.array(pairs) if pairs else np.zeros((0, 3))


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
            side_axis = detect_side_axis(features, up_axis)
            names = list(features)
            points = np.array([features[n].head for n in names], dtype=float)
            points_by_name = dict(zip(names, points))

            # 尺度用点云的最小外接边长方根，避免被单根道具骨拉大
            extent = points.max(axis=0) - points.min(axis=0)
            scale = float(np.sqrt((extent ** 2).sum())) or 1.0

            report = symmetry_report(points, scale)
            # 侧轴 = 镜像残差最小的轴；残差并列时取贴平面比例高的
            sym_side = min(range(3), key=lambda a: (round(report[a][1], 4),
                                                    -report[a][0]))

            mid = pair_geometry(points_by_name, features)
            if len(mid) >= 3:
                centred = mid - mid.mean(axis=0)
                eig = np.linalg.eigvalsh(np.cov(centred.T))
                mid_min = int(np.argmin(eig))
            else:
                mid_min = -1

            print(f"  ORI  {armature.name:<30s} bones={len(features):<5d}")
            print(f"    CUR up={AXIS[up_axis]} side={AXIS[side_axis]} "
                  f"pairs={len(mid)}")
            for axis in range(3):
                near, residual = report[axis]
                mark = "  <- 侧轴" if axis == sym_side else ""
                print(f"    SYM {AXIS[axis]} 贴平面={near:5.2f} "
                      f"镜像残差={residual:7.4f}{mark}")
            verdict = ("AGREE" if sym_side == side_axis else "CONFLICT")
            print(f"    {verdict} sym_side={AXIS[sym_side]} "
                  f"cur_side={AXIS[side_axis]} "
                  f"mid_pair_pca_min={AXIS[mid_min] if mid_min >= 0 else 'n/a'}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
