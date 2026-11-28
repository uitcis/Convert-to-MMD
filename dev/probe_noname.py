"""诊断：模拟「骨名无左右标识」时侧轴判定的退化程度。

用法：
    blender --background --factory-startup --python dev/probe_noname.py -- <model.blend> [...]

monkeypatch 掉 _named_side_pairs 让命名证据完全失效，对比：
    NO-NAME  现有回退（_axis_spread 跨度最大的垂直轴）
    SYM      对称面搜索（不读骨名）
    TRUE     命名证据完整时的结果（基准）
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


def mirror_residual(points, normal, scale, trim=0.7):
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


def search_normal(points, scale, grid=12):
    normals = []
    for i in range(1, grid):
        theta = np.pi * i / grid
        for j in range(grid * 2):
            phi = 2.0 * np.pi * j / (grid * 2)
            normals.append([np.sin(theta) * np.cos(phi),
                            np.sin(theta) * np.sin(phi),
                            np.cos(theta)])
    normals.append([0.0, 0.0, 1.0])
    normals = np.array(normals)
    costs = [mirror_residual(points, n, scale) for n in normals]
    order = np.argsort(costs)
    return normals[order[0]], costs[order[0]], costs[order[1]]


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    original = core._named_side_pairs
    for model in argv[argv.index("--") + 1:]:
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, _diagonal, _z_min, up_axis = build_features(armature)
            if not features or span <= 0:
                continue
            names = list(features)
            points = np.array([features[n].head for n in names], dtype=float)
            extent = points.max(axis=0) - points.min(axis=0)
            scale = float(np.sqrt((extent ** 2).sum())) or 1.0

            core._named_side_pairs = original
            truth = detect_side_axis(features, up_axis)
            pair_count = len([1 for l, r in original(
                features, include_middle=True)
                if l in features and r in features])

            core._named_side_pairs = lambda *a, **k: []
            fallback = detect_side_axis(features, up_axis)

            normal, best, second = search_normal(points, scale)
            sym_side = int(np.argmax(np.abs(normal)))
            margin = best / max(second, 1e-9)

            core._named_side_pairs = original
            ok = "OK" if fallback == truth and sym_side == truth else "DIFF"
            print(f"  {armature.name:<28s} bones={len(features):<5d} "
                  f"pairs={pair_count:<4d} TRUE={AXIS[truth]} "
                  f"NO-NAME={AXIS[fallback]} SYM={AXIS[sym_side]} "
                  f"余量={margin:.2f} {ok}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
