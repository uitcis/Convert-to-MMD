"""纯几何求骨架侧轴：搜索使「镜像重合度最高」的平面法向。

用法：
    blender --background --factory-startup --python dev/probe_symmetry.py -- <model.blend> [...]

完全不读骨名。人的骨架近似关于矢状面对称，所以存在一个平面，把骨点集
关于它镜像后能与自身高度重合；该平面的法向即侧轴方向（不限于坐标轴——
旋转 45° 的骨架也能求出正确方向）。

残差用**截尾均值**：单侧骨（武器、尾巴、单边披风）没有镜像伙伴，
若不截尾会把所有方向都拉平，正是 leviathan 上「三轴残差 0.12/0.10/0.10
无差别」的原因。
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

from convert_to_mmd.tools.auto_bone_mapping import (  # noqa: E402
    build_features, detect_side_axis)

AXIS = "XYZ"
SAMPLE_LIMIT = 400
GRID = 12          # 纬度/经度各 12 档（半球，方向符号无关）


def mirror_residual(points, normal, scale, trim=0.7):
    """关于平面 (normal, median) 镜像后的截尾平均最近邻距离。"""
    projection = points @ normal
    centre = float(np.median(projection))
    mirrored = points - 2.0 * np.outer(projection - centre, normal)
    target = mirrored @ normal

    order = np.argsort(projection)
    sorted_points = points[order]
    sorted_projection = projection[order]
    index = np.searchsorted(sorted_projection, target)
    best = np.full(len(points), np.inf)
    for offset in range(-3, 4):
        cursor = np.clip(index + offset, 0, len(points) - 1)
        distance = np.linalg.norm(mirrored - sorted_points[cursor], axis=1)
        best = np.minimum(best, distance)
    keep = int(len(best) * trim)
    return float(np.sort(best)[:keep].mean()) / scale


def candidate_normals(grid):
    """半球均匀网格（避免重复的 ±n）。"""
    normals = []
    for i in range(1, grid):
        theta = np.pi * i / grid
        for j in range(grid * 2):
            phi = 2.0 * np.pi * j / (grid * 2)
            normals.append([np.sin(theta) * np.cos(phi),
                            np.sin(theta) * np.sin(phi),
                            np.cos(theta)])
    normals.append([0.0, 0.0, 1.0])
    return np.array(normals)


def refine(points, normal, scale):
    """以当前方向为起点做小步长局部搜索。"""
    best = normal
    best_cost = mirror_residual(points, best, scale)
    step = 0.25
    for _ in range(12):
        improved = False
        for delta in ([step, 0, 0], [-step, 0, 0], [0, step, 0],
                      [0, -step, 0], [0, 0, step], [0, 0, -step]):
            trial = best + np.array(delta, dtype=float)
            norm = np.linalg.norm(trial)
            if norm < 1e-9:
                continue
            trial = trial / norm
            cost = mirror_residual(points, trial, scale)
            if cost < best_cost - 1e-6:
                best, best_cost, improved = trial, cost, True
        if not improved:
            step *= 0.5
    return best, best_cost


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    normals = candidate_normals(GRID)
    for model in argv[argv.index("--") + 1:]:
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, _diagonal, _z_min, up_axis = build_features(armature)
            if not features or span <= 0:
                continue
            names = list(features)
            points = np.array([features[n].head for n in names], dtype=float)
            if len(points) > SAMPLE_LIMIT:
                # 等距抽样，保持空间分布
                pick = np.linspace(0, len(points) - 1, SAMPLE_LIMIT).astype(int)
                sample = points[pick]
            else:
                sample = points
            extent = points.max(axis=0) - points.min(axis=0)
            scale = float(np.sqrt((extent ** 2).sum())) or 1.0

            costs = [mirror_residual(sample, n, scale) for n in normals]
            order = np.argsort(costs)
            best_normal, best_cost = refine(sample, normals[order[0]], scale)
            second = costs[order[1]] if len(order) > 1 else best_cost
            # 置信度：最优显著优于次优（否则说明骨架不对称，判据无信号）
            margin = best_cost / max(second, 1e-9)

            side_axis = detect_side_axis(features, up_axis)
            print(f"  SYM  {armature.name:<28s} bones={len(features):<5d}")
            print(f"    normal=({best_normal[0]:+.3f} {best_normal[1]:+.3f} "
                  f"{best_normal[2]:+.3f}) 残差={best_cost:.4f} "
                  f"次优={second:.4f} 余量={margin:.2f} "
                  f"轴对齐={'是' if abs(best_normal).max() > 0.95 else '否'}")
            print(f"    CUR  side={AXIS[side_axis]} up={AXIS[up_axis]}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
