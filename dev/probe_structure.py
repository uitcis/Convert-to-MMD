"""骨架结构探针：列出 .blend 里所有骨架对象、骨数、根骨与命名样本。

用法：
    blender --background --factory-startup --python dev/probe_structure.py -- <model.blend> [--all]

默认只列前 40 根骨名；加 --all 列全部。
用途：新模型上手时先看命名体系与骨架数量，再决定跑哪个检查脚本。
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    print("用法：-- <model.blend> [--all]")
    raise SystemExit(1)
model = argv[0]
show_all = "--all" in argv
# --armature <名称或序号>：只看其中一套骨架，其余跳过
want = argv[argv.index("--armature") + 1] if "--armature" in argv else None

bpy.ops.wm.open_mainfile(filepath=model)

print(f"PROBE_MODEL {os.path.basename(model)}")
armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
print(f"PROBE_ARMATURE_COUNT {len(armatures)}")
if want is not None:
    picked = armatures[int(want)] if want.isdigit() else next(
        (o for o in armatures if o.name == want), None)
    if picked is None:
        print(f"找不到骨架 {want}")
        raise SystemExit(1)
    armatures = [picked]

for obj in armatures:
    bones = list(obj.data.bones)
    roots = [b.name for b in bones if b.parent is None]
    print(f"PROBE_ARMATURE {obj.name} bones={len(bones)} "
          f"roots={roots}")
    names = [b.name for b in bones]
    limit = len(names) if show_all else 40
    for name in names[:limit]:
        bone = obj.data.bones[name]
        parent = bone.parent.name if bone.parent else "-"
        head = bone.head_local
        print(f"  BONE {name!r:34s} parent={parent!r:30s} "
              f"head=({head.x:.3f},{head.y:.3f},{head.z:.3f}) "
              f"len={bone.length:.3f}")
    if len(names) > limit:
        print(f"  ... 其余 {len(names) - limit} 根省略（加 --all 查看）")

print("PROBE_DONE")
