"""核心骨（面板带 *）分配情况检查。

用法：blender --background --factory-startup --python check_core.py -- <model.blend>
"""

import os
import sys

import bpy

# 项目根目录由脚本位置推导，换机器/换路径不用改
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "convert_to_mmd", os.path.join(ROOT, "__init__.py"),
    submodule_search_locations=[ROOT])
_plugin = importlib.util.module_from_spec(spec)
sys.modules["convert_to_mmd"] = _plugin
spec.loader.exec_module(_plugin)

from convert_to_mmd.tools import mapping_core as core  # noqa: E402
from convert_to_mmd.tools.auto_bone_mapping import (  # noqa: E402
    build_features, detect_side_axis,
)

model = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=model)
armature = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
features, span, diagonal, z_min, up_axis = build_features(armature)
side_axis = detect_side_axis(features, up_axis)
stats = core.load_preset_stats()
filled, low_conf, result = core.solve(
    core.FIELD_ORDER, features, span, diagonal, z_min, up_axis, side_axis,
    stats=stats)

print(f"MODEL {os.path.basename(model)}")
print(f"SUMMARY filled={result['filled']}/64 solid={result['solid']} "
      f"lowconf={result['low_conf']}")

CORE = [
    ("上半身*", "upper_body_bone"), ("首*", "neck_bone"), ("頭*", "head_bone"),
    ("肩*", "left_shoulder_bone"), ("腕*", "left_upper_arm_bone"),
    ("ひじ*", "left_lower_arm_bone"), ("手首*", "left_hand_bone"),
    ("足*", "left_thigh_bone"), ("ひざ*", "left_calf_bone"),
    ("足首*", "left_foot_bone"),
]
NON_CORE = [
    ("操作中心", "control_center_bone"), ("全ての親", "all_parents_bone"),
    ("センター", "center_bone"), ("グルーブ", "groove_bone"),
    ("腰", "hip_bone"), ("下半身", "lower_body_bone"),
    ("目", "left_eye_bone"), ("足先EX", "left_toe_bone"),
]
for title, group in (("核心骨", CORE), ("扩展骨", NON_CORE)):
    print(f"-- {title} --")
    for label, field in group:
        candidate = filled.get(field)
        if candidate is None:
            print(f"   {label:10s} (空)")
        else:
            flag = "推导" if candidate.get("derived") else ""
            print(f"   {label:10s} {candidate['bone']:24s} "
                  f"{candidate['score']:.2f} {flag}")
