"""批量扫描：目录里每个 .blend 的每套骨架能否被自动映射识别。

用法：
    blender --background --python dev/scan_all_models.py -- <a.blend> [b.blend ...]

每套骨架输出一行（TAB 分隔，便于后续汇总）：
    R  <路径>  <骨架名>  <骨数>  <filled> <solid> <broken> <core_ok> <side> <note>

core_ok ：CORE_BONE_FIELDS 里是否全部填上
side    ：左右成对字段的 head 在侧轴上符号是否相反（OK / BAD / -）
note    ：NOARMATURE / LOWCORE:<字段> / SIDEBAD:<字段对> 等
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

# 左右成对字段（用于侧别方向自检）
SIDE_PAIRS = (
    ("left_shoulder_bone", "right_shoulder_bone"),
    ("left_upper_arm_bone", "right_upper_arm_bone"),
    ("left_lower_arm_bone", "right_lower_arm_bone"),
    ("left_hand_bone", "right_hand_bone"),
    ("left_thigh_bone", "right_thigh_bone"),
    ("left_calf_bone", "right_calf_bone"),
    ("left_foot_bone", "right_foot_bone"),
    ("left_toe_bone", "right_toe_bone"),
)


def scan_one(path, armature):
    features, span, diagonal, z_min, up_axis = build_features(armature)
    side_axis = detect_side_axis(features, up_axis)
    stats = core.load_preset_stats()
    filled, _low, result = core.solve(
        core.FIELD_ORDER, features, span, diagonal, z_min, up_axis,
        side_axis, stats=stats)

    broken = []
    for parent_field, child_field in core.CHAIN_PAIRS:
        if parent_field not in filled or child_field not in filled:
            continue
        parent_bone = filled[parent_field]["bone"]
        child_bone = filled[child_field]["bone"]
        if parent_bone not in features or child_bone not in features:
            continue
        if not core._is_ancestor(features, parent_bone, child_bone):
            broken.append(f"{child_field}<{parent_field}")

    # CORE_BONE_FIELDS 是 frozenset，遍历顺序每进程随机，必须排序后再输出
    missing_core = [f for f in sorted(core.CORE_BONE_FIELDS) if f not in filled]

    side_bad = []
    for left_field, right_field in SIDE_PAIRS:
        left = filled.get(left_field)
        right = filled.get(right_field)
        if not left or not right:
            continue
        lx = features[left["bone"]].head[side_axis]
        rx = features[right["bone"]].head[side_axis]
        # 左右应落在侧轴的两侧，同号说明侧别判反了
        if lx * rx > 0 and abs(lx) > 1e-6 and abs(rx) > 1e-6:
            side_bad.append(f"{left_field[5:-5]}")

    notes = []
    if "NOARMATURE" in scan_one.notes:
        notes.append("NOARMATURE")
    if missing_core:
        notes.append("低核心:" + ",".join(f[:14] for f in missing_core[:3])
                     + ("" if len(missing_core) <= 3
                        else f"(+{len(missing_core) - 3})"))
    if side_bad:
        notes.append("侧别反:" + ",".join(side_bad[:3]))
    if broken:
        notes.append("链断:" + ",".join(broken[:2]))

    print("R\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\t%s" % (
        path, armature.name, len(features), result["filled"], result["solid"],
        len(broken), len(core.CORE_BONE_FIELDS) - len(missing_core),
        "BAD" if side_bad else "OK", " | ".join(notes) or "ok"))
    sys.stdout.flush()


scan_one.notes = set()


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <a.blend> [...]")
        return 1
    for path in argv[argv.index("--") + 1:]:
        scan_one.notes = set()
        label = os.path.relpath(path, r"E:/3D Objects/downloaded_models")
        label = label.replace("\\", "/")
        try:
            bpy.ops.wm.open_mainfile(filepath=path)
        except Exception as exc:  # noqa: BLE001
            print("R\t%s\t-\t0\t0\t0\t0\t0\t-\tOPENFAIL:%s"
                  % (label, str(exc)[:60]))
            continue
        armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
        if not armatures:
            print("R\t%s\t-\t0\t0\t0\t0\t0\t-\tNOARMATURE" % label)
            continue
        for armature in armatures:
            if not armature.data.bones:
                print("R\t%s\t%s\t0\t0\t0\t0\t0\t-\tEMPTYBONES"
                      % (label, armature.name))
                continue
            scan_one.notes = set()
            try:
                scan_one(label, armature)
            except Exception as exc:  # noqa: BLE001
                print("R\t%s\t%s\t0\t0\t0\t0\t0\t-\tFAIL:%s"
                      % (label, armature.name, str(exc)[:60]))
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
