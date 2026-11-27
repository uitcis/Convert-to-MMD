"""父子关系否决的针对性验证：各类错配是否被排除。

用法：blender --background --factory-startup --python check_chain.py -- <model.blend>
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
armature = next(o for o in bpy.data.objects
                if o.type == 'ARMATURE' and not o.name.endswith("_backup"))
features, span, diagonal, z_min, up_axis = build_features(armature)
side_axis = detect_side_axis(features, up_axis)
stats = core.load_preset_stats()

ctx = {
    "span": span, "diagonal": diagonal, "z_min": z_min,
    "up_axis": up_axis, "side_axis": side_axis, "stats": stats,
}
ctx["symmetric"], _e = core.detect_symmetry(features, span, side_axis, up_axis)
ctx["midline"] = core.detect_midline(features, side_axis)
ctx["spine_chain"] = core.detect_spine_chain(features, up_axis)
palms = list(core._find_palm_bones(features, span))
_limb, torso = core._compute_limb_domains(features, palms)
ctx["torso_domain"] = torso
roles, sides, domains = core.infer_finger_roles(features, span, side_axis, up_axis)
ctx["finger_roles"] = roles
ctx["finger_sides"] = sides
ctx["finger_domains"] = domains


def find(name_part):
    """按名称片段找骨（忽略大小写与后缀编号）。"""
    lower = name_part.lower()
    for bone in features:
        if lower in bone.lower():
            return bone
    return None


CASES = [
    # (字段, 应该被否决的骨名片段, 说明)
    ("left_upper_arm_bone", "ForeArm", "小臂骨填给上臂"),
    ("left_upper_arm_bone", "Hand", "手骨填给上臂"),
    ("left_lower_arm_bone", "UpperArm", "上臂骨填给小臂"),
    ("left_lower_arm_bone", "Thigh", "大腿骨填给小臂"),
    ("left_hand_bone", "ForeArm", "小臂骨填给手"),
    ("left_thigh_bone", "Calf", "小腿骨填给大腿"),
    ("left_calf_bone", "Thigh", "大腿骨填给小腿"),
    ("left_foot_bone", "Calf", "小腿骨填给脚"),
    ("neck_bone", "ForeArm", "小臂骨填给首"),
    ("neck_bone", "Thigh", "大腿骨填给首"),
    ("head_bone", "Hand", "手骨填给头"),
    ("head_bone", "ForeArm", "小臂骨填给头"),
    ("upper_body_bone", "ForeArm", "小臂骨填给上半身"),
    ("upper_body_bone", "Hand", "手骨填给上半身"),
]

print(f"{'字段':22s} {'错配骨':30s} 结果")
for field, name_part, note in CASES:
    bone = find(name_part)
    if bone is None:
        print(f"  {field:22s} {name_part:28s} (该模型无此骨)")
        continue
    candidate = core.score_candidate(field, features[bone], features, ctx)
    verdict = "已否决" if candidate is None else "仍可选!!"
    print(f"  {field:22s} {bone[:28]:28s} {verdict}  ({note})")
