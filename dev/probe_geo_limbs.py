"""几何身体划分的实测探针：只看骨点位置，与骨名语义对账。

划分逻辑本身在 `mapping_core.parse_body_plan`（探针不另写一套，避免漂移），
这里只负责跑模型、打印结果、和骨名语义比一比。

判据（全在 mapping_core 里）：
  ① 成对分叉：同一父骨下两根尺寸相近、挂点对称（或首骨反向）的分支；
  ② 腿 = 两根分支平行且垂得最远的那组，上方向 = 腿的平均方向取反；
  ③ 胳膊 = 横向展幅远超胯宽、顶端高于腿根、链够长的那组。

用法：
    blender -b --factory-startup --python dev/probe_geo_limbs.py -- <a.blend> [...]
"""
import math
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
from convert_to_mmd.tools.auto_bone_mapping import build_features  # noqa: E402

# 只用于「答案」的骨名语义，不参与划分
ARM_WORDS = ("arm", "hand", "fing", "thumb", "digit", "palm", "wrist", "elbow",
             "腕", "手首", "指", "ひじ")
LEG_WORDS = ("thigh", "calf", "shin", "foot", "toe", "ankle", "knee", "leg",
             "足", "ひざ", "つま先", "腿", "脚")


def gt_domain(name):
    low = name.lower()
    arm = any(w in low for w in ARM_WORDS)
    leg = any(w in low for w in LEG_WORDS)
    if arm and not leg:
        return "arm"
    if leg and not arm:
        return "leg"
    return "other"


def report(armature):
    features, _span, _diag, _zmin, up_axis = build_features(armature)
    if not features:
        return
    plan = core.parse_body_plan(features)
    print("GEO\t%s\tbones=%d" % (armature.name, len(features)))
    if plan is None:
        print("GEO\t  FAIL 未能解析出人形分叉")
        return
    up, side = plan["up"], plan["side"]
    world_up = [0.0, 0.0, 0.0]
    world_up[up_axis] = 1.0
    tilt = max(-1.0, min(1.0, sum(up[i] * world_up[i] for i in range(3))))
    print("GEO\t  up=(%.3f,%.3f,%.3f) side=(%.3f,%.3f,%.3f) "
          "与插件上轴夹角=%.1f°" % (up[0], up[1], up[2], side[0], side[1],
                                  side[2], math.degrees(math.acos(tilt))))
    print("GEO\t  胳膊分叉=%s 腿分叉=%s  %s" % (
        "|".join(plan["arm_roots"]), "|".join(plan["leg_roots"]),
        plan["detail"]))
    print("GEO\t  划分：arm=%d leg=%d torso=%d 置信=%s" % (
        len(plan["arm"]), len(plan["leg"]), len(plan["torso"]),
        "高" if plan["confident"] else "低"))

    conf, misses = {}, []
    for name in sorted(features):
        gt = gt_domain(name)
        if gt == "other":
            continue
        label = ("arm" if name in plan["arm"]
                 else "leg" if name in plan["leg"] else "torso")
        conf[(gt, label)] = conf.get((gt, label), 0) + 1
        if gt != label:
            misses.append("%s:名=%s/几何=%s" % (name, gt, label))
    total = sum(conf.values())
    hit = sum(v for (g, p), v in conf.items() if g == p)
    print("GEO\t  与骨名对账：%d/%d 一致%s" % (
        hit, total, "" if total else "（无带名骨骼）"))
    if misses:
        print("GEO\t  不一致：%s" % " | ".join(misses[:8]))


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <a.blend> [...]")
        return 1
    for path in argv[argv.index("--") + 1:]:
        try:
            bpy.ops.wm.open_mainfile(filepath=path)
        except Exception as exc:                        # noqa: BLE001
            print("GEO\t%s\tOPENFAIL %s" % (os.path.basename(path), exc))
            continue
        armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
        if not armatures:
            print("GEO\t%s\tNOARMATURE" % os.path.basename(path))
            continue
        for armature in armatures:
            if armature.data.bones:
                report(armature)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
