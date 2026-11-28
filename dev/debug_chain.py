"""单个候选骨的链关系判定细节（为什么被判「父子关系反了」）。

用法：
    blender --background --factory-startup --python dev/debug_chain.py -- \
        <model.blend> --armature <名称> <field> <bone> [<field> <bone> ...]
"""
import os
import re
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

args = sys.argv[sys.argv.index("--") + 1:]
model = args[0]
want = None
if "--armature" in args:
    i = args.index("--armature")
    want = args[i + 1]
    del args[i:i + 2]
pairs = args[1:]

bpy.ops.wm.open_mainfile(filepath=model)
armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
armature = (armatures[0] if want is None
            else armatures[int(want)] if want.isdigit()
            else next(o for o in armatures if o.name == want))
features, span, diagonal, z_min, up_axis = build_features(armature)
print(f"DEBUG_ARMATURE {armature.name}")


def categories_of(name):
    return [c for c in core._CHAIN_CATEGORIES
            if core._bone_matches_category(name, c)]


for i in range(0, len(pairs), 2):
    field, bone = pairs[i], pairs[i + 1]
    feature = features[bone]
    base = re.sub(r"^(left|right)_", "", field)
    category = core._category(field)
    neighbors = core.FIELD_CHAIN_NEIGHBORS.get(base)
    print(f"\nPAIR {field} <- {bone}")
    print(f"  category={category} neighbors={neighbors}")
    print(f"  self_categories={categories_of(bone)}")
    print(f"  parent={feature.parent!r} "
          f"parent_categories={categories_of(feature.parent) if feature.parent else []}")
    for child in feature.children:
        print(f"  child={child!r} categories={categories_of(child)}")
    print(f"  chain_relation_violated={core.chain_relation_violated(field, feature, features)}")
    print(f"  shadowed={core._shadowed_by_main_bone(field, feature, features)}")
    print(f"  support_bone_name={core._is_support_bone_name(bone)}")

print("\nDEBUG_DONE")
