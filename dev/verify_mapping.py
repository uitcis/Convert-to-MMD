"""自动骨骼映射的端到端验证：真实模型上跑一次，检查两项新行为。

用法：
  blender --background --factory-startup --python verify_mapping.py -- <model.blend>
"""

import os
import sys

import bpy

# 项目根目录由脚本位置推导，换机器/换路径不用改
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# 以包方式注册插件，tools.auto_bone_mapping 的相对导入才能生效
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

print("VERIFY_MODEL", model)
bpy.ops.wm.open_mainfile(filepath=model)

armature = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if armature is None:
    print("VERIFY_FAIL no armature")
    raise SystemExit(1)

print("VERIFY_ARMATURE", armature.name)
features, span, diagonal, z_min, up_axis = build_features(armature)
side_axis = detect_side_axis(features, up_axis)
print("VERIFY_BONES", len(features))
print("VERIFY_AXES", "up", up_axis, "side", side_axis, "span", round(span, 4))

# --- 手指身份推断 ---
roles, _sides, _domains = core.infer_finger_roles(features, span, side_axis, up_axis)
print("VERIFY_FINGER_ROLES", len(roles))
by_finger = {}
for bone, (finger, segment) in roles.items():
    by_finger.setdefault(finger, []).append((segment, bone))
for finger in sorted(by_finger):
    items = sorted(by_finger[finger])
    print(f"VERIFY_FINGER {finger}: " +
          " ".join(f"{bone}#{seg}" for seg, bone in items))

# --- 完整求解 ---
stats = core.load_preset_stats()
filled, low_conf, result = core.solve(
    core.FIELD_ORDER, features, span, diagonal, z_min, up_axis, side_axis,
    stats=stats)

print("VERIFY_FILLED", result["filled"], "/", len(core.FIELD_ORDER))
print("VERIFY_SOLID", result["solid"])
print("VERIFY_LOWCONF", result["low_conf"])
print("VERIFY_AVERAGE", round(result["average"], 4))

# 低置信度字段应仍然被填写，并打上标记
flagged = {f: c for f, c in filled.items() if c.get("low_confidence")}
print("VERIFY_FLAGGED_COUNT", len(flagged))
listed = {f for f, _s, _r in low_conf}
missing = set(flagged) - listed
print("VERIFY_FLAGGED_IN_LOWCONF", "OK" if not missing else f"MISSING {missing}")
for field in sorted(flagged)[:10]:
    print(f"VERIFY_LOW {field} -> {flagged[field]['bone']} "
          f"{flagged[field]['score']:.2f}")

# 手指字段的填充情况
finger_filled = [f for f in filled if core._category(f) == "finger"]
print("VERIFY_FINGER_FILLED", len(finger_filled), "/", len(core.FINGER_FIELDS))
for field in sorted(finger_filled):
    print(f"VERIFY_FINGER_FIELD {field} -> {filled[field]['bone']} "
          f"{filled[field]['score']:.2f}")
print("VERIFY_DONE")
