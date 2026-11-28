"""性能剖析：把 solve 各阶段耗时拆开，定位真正的瓶颈。

用法：
    blender --background --python dev/probe_profile.py -- <a.blend>
"""
import cProfile
import io
import os
import pstats
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


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <a.blend>")
        return 1
    path = argv[argv.index("--") + 1]
    bpy.ops.wm.open_mainfile(filepath=path)
    for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
        if not armature.data.bones:
            continue
        features, span, diagonal, z_min, up_axis = build_features(armature)
        side_axis = detect_side_axis(features, up_axis)
        stats = core.load_preset_stats()
        profiler = cProfile.Profile()
        profiler.enable()
        _filled, _low, result = core.solve(
            core.FIELD_ORDER, features, span, diagonal, z_min, up_axis,
            side_axis, stats=stats)
        profiler.disable()
        print("\n===== %s  bones=%d nodes=%d filled=%d =====" % (
            armature.name, len(features), result["search_nodes"],
            result["filled"]))
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats(
            "cumulative").print_stats(18)
        print(stream.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main())
