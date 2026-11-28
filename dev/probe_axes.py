"""打印影响几何判定的关键中间量：up/side 轴、span、中轴、手掌骨。

用法：
    blender --background --factory-startup --python dev/probe_axes.py -- <model.blend> [骨架名]

用于新旧实现对照：轴判定一致时，差异必然出在 span/中轴/手掌推断上。
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
        return 1
    args = argv[argv.index("--") + 1:]
    model = args[0]
    want = args[1] if len(args) > 1 else None
    bpy.ops.wm.open_mainfile(filepath=model)
    for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
        if want and armature.name != want:
            continue
        features, span, diagonal, z_min, up_axis = build_features(armature)
        if not features:
            continue
        side_axis = detect_side_axis(features, up_axis)
        midline = core.detect_midline(features, side_axis)
        palms = sorted(core._find_palm_bones(features, span))
        pairs = core._named_side_pairs(features)
        print(f"AXES {armature.name} bones={len(features)} "
              f"up={up_axis} side={side_axis} span={span:.4f} "
              f"mid={midline:+.4f} pairs={len(pairs)} palms={len(palms)}")
        print(f"     PALMS {palms[:6]}")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
