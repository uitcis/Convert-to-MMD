"""基线检查：填充数 / 稳妥数 / 链关系断裂 / 关键字段取值。

用法：
    blender --background --factory-startup --python tools/check_baseline.py -- <model.blend>

输出形如：
    MODEL gai.blend
    STAT filled=59 solid=50 low=14 broken=0
    KEY  肩*=G Clavicle L
    ...
"""
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "convert_to_mmd", os.path.join(ROOT, "__init__.py"),
    submodule_search_locations=[ROOT])
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["convert_to_mmd"] = _pkg
_spec.loader.exec_module(_pkg)

from convert_to_mmd.tools import mapping_core as core  # noqa: E402
from convert_to_mmd.tools.auto_bone_mapping import (  # noqa: E402
    build_features, detect_side_axis)

# 关心的关键字段（按解剖顺序，便于逐行比对）
KEY_FIELDS = (
    "all_parents_bone", "control_center_bone", "center_bone", "groove_bone",
    "hip_bone", "upper_body_bone", "lower_body_bone", "neck_bone", "head_bone",
    "left_shoulder_bone", "left_upper_arm_bone", "left_lower_arm_bone",
    "left_hand_bone", "left_thigh_bone", "left_calf_bone", "left_foot_bone",
    "left_toe_bone",
)


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend>")
        return 1
    model = argv[argv.index("--") + 1]
    bpy.ops.wm.open_mainfile(filepath=model)
    armature = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    features, span, diagonal, z_min, up_axis = build_features(armature)
    side_axis = detect_side_axis(features, up_axis)
    stats = core.load_preset_stats()
    filled, low_conf, result = core.solve(
        core.FIELD_ORDER, features, span, diagonal, z_min, up_axis,
        side_axis, stats=stats)

    # 链关系断裂数：CHAIN_PAIRS 里已填的父子是否真的构成祖先关系
    broken = []
    for parent_field, child_field in core.CHAIN_PAIRS:
        if parent_field not in filled or child_field not in filled:
            continue
        parent_bone = filled[parent_field]["bone"]
        child_bone = filled[child_field]["bone"]
        if parent_bone not in features or child_bone not in features:
            continue
        if not core._is_ancestor(features, parent_bone, child_bone):
            broken.append((parent_field, child_field, parent_bone, child_bone))

    print(f"MODEL {os.path.basename(model)}")
    print(f"STAT filled={result['filled']} solid={result['solid']} "
          f"low={result['low_conf']} broken={len(broken)}")
    for parent_field, child_field, parent_bone, child_bone in broken:
        print(f"  !! {child_field} < {parent_field}: "
              f"{child_bone} 不是 {parent_bone} 的后代")
    for field in KEY_FIELDS:
        candidate = filled.get(field)
        if candidate is None:
            print(f"KEY  {field:24s} -")
        else:
            flag = " (低)" if candidate.get("low_confidence") else ""
            print(f"KEY  {field:24s} {candidate['score']:.3f} "
                  f"{candidate['bone']}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
