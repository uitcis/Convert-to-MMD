bl_info = {
    "name": "Convert to MMD",
    "author": "UITCIS(空想幻灵)",
    "version": (2, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar",
    "description": "Plugin to automatically rename and complete missing bones for MMD format",
    "warning": "",
    "wiki_url": "",
    "category": "Animation"
}

import bpy
from mathutils import Vector, Matrix, Euler
from math import radians
import json
from . import bone_map_and_group
from . import operations
from . import bone_operations
from . import ui_panel
from . import bone_grouping
from . import bone_utils
from . import ik_operations
from . import Apose_operation

def register_properties(properties_dict):
    """Registers properties dynamically using a dictionary."""
    for prop_name, prop_value in properties_dict.items():
        setattr(bpy.types.Scene, prop_name, bpy.props.StringProperty(default=prop_value))

def unregister_properties(properties_list):
    """Unregisters properties dynamically using a list of property names."""
    for prop_name in properties_list:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)

def register():
    bpy.utils.register_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.register_class(bone_operations.OBJECT_OT_rename_to_mmd)
    bpy.utils.register_class(bone_operations.OBJECT_OT_complete_missing_bones)
    bpy.utils.register_class(operations.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.register_class(operations.OBJECT_OT_export_preset)
    bpy.utils.register_class(operations.OBJECT_OT_import_preset)
    bpy.utils.register_class(operations.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.register_class(Apose_operation.OBJECT_OT_convert_to_apose)
    bpy.utils.register_class(ik_operations.OBJECT_OT_add_ik)
    bpy.utils.register_class(bone_grouping.OBJECT_OT_create_bone_grouping)
    bones = operations.get_bones_list()
    register_properties(bones)

def unregister():
    bpy.utils.unregister_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.unregister_class(bone_operations.OBJECT_OT_rename_to_mmd)
    bpy.utils.unregister_class(bone_operations.OBJECT_OT_complete_missing_bones)
    bpy.utils.unregister_class(operations.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.unregister_class(operations.OBJECT_OT_export_preset)
    bpy.utils.unregister_class(operations.OBJECT_OT_import_preset)
    bpy.utils.unregister_class(operations.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.unregister_class(Apose_operation.OBJECT_OT_convert_to_apose)
    bpy.utils.unregister_class(ik_operations.OBJECT_OT_add_ik)
    bpy.utils.unregister_class(bone_grouping.OBJECT_OT_create_bone_grouping)
    bones = operations.get_bones_list()
    unregister_properties(bones)

if __name__ == "__main__":
    register()