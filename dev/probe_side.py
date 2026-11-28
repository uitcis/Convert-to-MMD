"""诊断左右侧别判定：配对数量、左右骨的实际坐标均值、侧轴与符号关系。

用法：
    blender --background --factory-startup --python dev/probe_side.py -- <model.blend> [...]

对每个模型里的每套骨架输出：
    SIDE <骨架> bones=<n> up=<axis> side=<axis> pairs=<n>
    PAIR L骨名(x) / R骨名(x)       前若干对
    SIGN left_mid=<x> right_mid=<x> => 左侧应在 <正/负> 半轴
"""
import os
import sys
import importlib.util

import bpy

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

AXIS_NAME = ("X", "Y", "Z")


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    models = argv[argv.index("--") + 1:]
    for model in models:
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, diagonal, z_min, up_axis = build_features(armature)
            if not features:
                print(f"SIDE {armature.name} 无骨骼")
                continue
            side_axis = detect_side_axis(features, up_axis)
            pairs = [(l, r) for l, r in core._named_side_pairs(
                features, include_middle=True)
                if l in features and r in features]
            left_x = [features[l].head[side_axis] for l, _r in pairs]
            right_x = [features[r].head[side_axis] for _l, r in pairs]
            symmetric, sym_err = core.detect_symmetry(
                features, span, side_axis, up_axis)
            print(f"SIDE {armature.name} bones={len(features)} "
                  f"up={AXIS_NAME[up_axis]} side={AXIS_NAME[side_axis]} "
                  f"pairs={len(pairs)} sym={symmetric} err={sym_err:.3f}")
            for left_name, right_name in pairs[:6]:
                print(f"  PAIR {left_name}({features[left_name].head[side_axis]:+.3f})"
                      f" / {right_name}({features[right_name].head[side_axis]:+.3f})")
            if pairs:
                lm = sum(left_x) / len(left_x)
                rm = sum(right_x) / len(right_x)
                verdict = "正" if lm > rm else "负"
                print(f"  SIGN left_mid={lm:+.3f} right_mid={rm:+.3f} "
                      f"=> 左侧应在{verdict}半轴 "
                      f"(当前代码固定按正半轴)")
            if len(pairs) < 6:
                sample = sorted(features)[:14]
                print("  NAMES " + " | ".join(sample))
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
