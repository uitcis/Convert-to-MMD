bl_info = {
    "name": "Convert to MMD",
    "author": "UITCIS(空想幻灵)",
    "version": (1, 1),
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
from . import bone_mapping
from . import operations
from .ui_panel import OBJECT_PT_skeleton_hierarchy
from .bone_operations import OBJECT_OT_add_ik, OBJECT_OT_complete_missing_bones

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
    bpy.utils.register_class(OBJECT_PT_skeleton_hierarchy)
    bpy.utils.register_class(operations.OBJECT_OT_rename_to_mmd)
    bpy.utils.register_class(OBJECT_OT_complete_missing_bones)
    bpy.utils.register_class(operations.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.register_class(operations.OBJECT_OT_export_preset)
    bpy.utils.register_class(operations.OBJECT_OT_import_preset)
    bpy.utils.register_class(OBJECT_OT_add_ik)
    bones = operations.get_bones_list()
    register_properties(bones)

def unregister():
    bpy.utils.unregister_class(OBJECT_PT_skeleton_hierarchy)
    bpy.utils.unregister_class(operations.OBJECT_OT_rename_to_mmd)
    bpy.utils.unregister_class(OBJECT_OT_complete_missing_bones)
    bpy.utils.unregister_class(operations.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.unregister_class(operations.OBJECT_OT_export_preset)
    bpy.utils.unregister_class(operations.OBJECT_OT_import_preset)
    bpy.utils.unregister_class(OBJECT_OT_add_ik)
    bones = operations.get_bones_list()
    unregister_properties(bones)

if __name__ == "__main__":
    register()