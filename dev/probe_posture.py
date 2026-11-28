"""查看骨架的姿态判定结果（站立的 A/T-pose / 非站立 / 无法判定）。

直接调用 mapping_core.detect_posture，避免探针与插件两套实现漂移。

用法：
    blender -b --factory-startup --python dev/probe_posture.py -- <a.blend> [...]
输出（TAB 分隔）：
    POST <骨架> <bones> <up> <kind> <state> <detail> <文件>
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


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> [...]")
        return 1
    for model in argv[argv.index("--") + 1:]:
        try:
            bpy.ops.wm.open_mainfile(filepath=model)
        except Exception as exc:                       # noqa: BLE001
            print(f"ERR {model} {exc}")
            continue
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, _diag, _zmin, up_axis = build_features(armature)
            if not features:
                continue
            side_axis = detect_side_axis(features, up_axis)
            kind, _kind_detail = core.classify_skeleton(
                features, span, side_axis, up_axis)
            state, detail = core.detect_posture(features, span, up_axis)
            print(f"POST\t{armature.name}\t{len(features)}\t{up_axis}\t"
                  f"{kind}\t{state}\t{detail}\t{os.path.basename(model)}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
