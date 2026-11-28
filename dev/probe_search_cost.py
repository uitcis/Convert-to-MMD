"""搜索开销探针：统计每套骨架的回溯节点数、耗时、是否撞上限。

用法：
    blender --background --python dev/probe_search_cost.py -- <a.blend> [...]

输出（TAB 分隔）：
    C  <路径>  <骨架>  <骨数>  <nodes>  <ms>  <filled>  <solid>  <caps>

caps 标记：
    HITCAP  节点数达到 MAX_SEARCH_NODES（搜索被截断，结果只是贪心下界）
    SLOW    单套耗时 > SLOW_MS

用途：判断「搜索上限」到底是不是真瓶颈。若 HITCAP 极少，
优化方向应放在候选生成/约束，而不是换求解器。
"""
import os
import sys
import time

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

SLOW_MS = 1500.0
# 临时放宽搜索上限做对照实验：SEARCH_CAP=5000000 看精确解质量
if os.environ.get("SEARCH_CAP"):
    core.MAX_SEARCH_NODES = int(os.environ["SEARCH_CAP"])
# NO_EDIT=1 关闭编辑距离档（阈值抬到 1.1 使其永不命中），用于评估
# 「这档 0.15 分到底值不值 40% 耗时」
if os.environ.get("NO_EDIT"):
    core.EDIT_MIN_RATIO = 1.1


def probe_one(label, armature):
    features, span, diagonal, z_min, up_axis = build_features(armature)
    side_axis = detect_side_axis(features, up_axis)
    stats = core.load_preset_stats()
    started = time.perf_counter()
    filled, _low, result = core.solve(
        core.FIELD_ORDER, features, span, diagonal, z_min, up_axis,
        side_axis, stats=stats)
    elapsed = (time.perf_counter() - started) * 1000.0

    nodes = result.get("search_nodes", 0)
    caps = []
    if nodes >= core.MAX_SEARCH_NODES:
        caps.append("HITCAP")
    if elapsed > SLOW_MS:
        caps.append("SLOW")
    print("C\t%s\t%s\t%d\t%d\t%.0f\t%d\t%d\t%s" % (
        label, armature.name, len(features), nodes, elapsed,
        result["filled"], result["solid"], ",".join(caps) or "-"))
    sys.stdout.flush()


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <a.blend> [...]")
        return 1
    for path in argv[argv.index("--") + 1:]:
        label = os.path.relpath(path, r"E:/3D Objects/downloaded_models")
        label = label.replace("\\", "/")
        try:
            bpy.ops.wm.open_mainfile(filepath=path)
        except Exception as exc:  # noqa: BLE001
            print("C\t%s\t-\t0\t0\t0\t0\t0\tOPENFAIL:%s"
                  % (label, str(exc)[:50]))
            continue
        for armature in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            if not armature.data.bones:
                continue
            try:
                probe_one(label, armature)
            except Exception as exc:  # noqa: BLE001
                print("C\t%s\t%s\t0\t0\t0\t0\t0\tFAIL:%s"
                      % (label, armature.name, str(exc)[:50]))
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
