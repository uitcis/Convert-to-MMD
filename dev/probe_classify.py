"""诊断骨架体型分类：humanoid / partial / non_humanoid。

用法：
    blender --background --factory-startup --python dev/probe_classify.py -- <model.blend> [...]

每套骨架输出一行：
    KIND <骨架> bones=<n> <分类> <脊柱节数/高度占比/配对数/分支数>
用于检查非人形骨架（尾巴/道具/毛发/单件服装）是否被正确识别。
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
        bpy.ops.wm.open_mainfile(filepath=model)
        print(f"MODEL {os.path.basename(model)}")
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            features, span, _diagonal, _z_min, up_axis = build_features(armature)
            if not features:
                continue
            side_axis = detect_side_axis(features, up_axis)
            kind, detail = core.classify_skeleton(
                features, span, side_axis, up_axis)
            print(f"KIND {kind:13s} bones={len(features):<5d} "
                  f"{armature.name:<28s} {detail}")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
