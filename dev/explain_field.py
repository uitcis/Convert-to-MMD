"""字段候选解释：某字段为什么选中的是这根骨、正确骨为什么没被选中。

用法：
    blender --background --factory-startup --python dev/explain_field.py -- \
        <model.blend> [--armature <名称或序号>] <字段1> <字段2> ...

输出每个字段的候选列表（分数 + 各分项）与被否决的原因，
用于定位「上臂被大腿骨抢走」这类问题。
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

args = sys.argv[sys.argv.index("--") + 1:]
model = args[0]
want = None
if "--armature" in args:
    i = args.index("--armature")
    want = args[i + 1]
    del args[i:i + 2]
fields = args[1:] or ["left_upper_arm_bone"]

bpy.ops.wm.open_mainfile(filepath=model)
armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
if want is None:
    armature = armatures[0]
elif want.isdigit():
    armature = armatures[int(want)]
else:
    armature = next(o for o in armatures if o.name == want)
print(f"EXPLAIN_ARMATURE {armature.name}")

features, span, diagonal, z_min, up_axis = build_features(armature)
side_axis = detect_side_axis(features, up_axis)
print(f"EXPLAIN_AXES up={up_axis} side={side_axis} span={span:.3f} "
      f"pairs={len(core._named_side_pairs(features))}")

# 截获打分过程：solve 内部按全局名调用 score_candidate，换掉即可
records = {}
_rejected = {}
_orig_score = core.score_candidate


def _patched(field, feature, features_, ctx):
    result = _orig_score(field, feature, features_, ctx)
    if result is None:
        reasons = []
        if core.chain_relation_violated(field, feature, features_):
            reasons.append("父子关系反了")
        if core._shadowed_by_main_bone(field, feature, features_):
            reasons.append("同父下有正牌骨")
        if (core._category(field) != "finger"
                and feature.name in (ctx.get("finger_roles") or {})):
            reasons.append("这是手指骨")
        _rejected.setdefault(field, []).append(
            (feature.name, "、".join(reasons) or "其它前置限制"))
    else:
        records.setdefault(field, []).append(result)
    return result


core.score_candidate = _patched
stats = core.load_preset_stats()
filled, low_conf, result = core.solve(
    core.FIELD_ORDER, features, span, diagonal, z_min, up_axis, side_axis,
    stats=stats)
core.score_candidate = _orig_score

print(f"EXPLAIN_STAT filled={result['filled']} solid={result['solid']} "
      f"broken_overall={result['low_conf']}")

for field in fields:
    chosen = filled.get(field)
    print(f"\nFIELD {field}  -> {chosen['bone'] if chosen else '-'} "
          f"({chosen['score']:.3f})" if chosen else f"\nFIELD {field}  -> 空")
    rows = sorted(records.get(field, []), key=lambda c: -c["score"])
    for c in rows[:8]:
        parts = " ".join(f"{k}={v:.3f}" for k, v in c["parts"].items())
        print(f"  CAND {c['score']:.3f} {c['bone']:34s} {parts}")
    rej = _rejected.get(field, [])
    if rej:
        print(f"  REJECTED {len(rej)} 根：")
        for name, reason in rej:
            print(f"    - {name:34s} {reason}")

print("\nEXPLAIN_DONE")
