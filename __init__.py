bl_info = {
    "name": "Convert to MMD",
    "author": "UITCIS(空想幻灵)",
    "version": (2, 6),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar",
    "description": "Plugin to automatically rename and complete missing bones for MMD format",
    "warning": "",
    "wiki_url": "",
    "category": "Animation"
}

import bpy
import os

from . import ui_panel
from . import bone_map_and_group
from . import bone_utils
from . import properties
from . import encoding_patch

# UI 面板
from .ui_panel import OBJECT_PT_skeleton_hierarchy

# 核心操作符 (operators/)
from .operators.load_preset_operator import OBJECT_OT_load_preset
from .operators import preset_operator
from .operators import rename_bones_operator
from .operators import complete_bones_operator
from .operators import collection_operator
from .operators import ik_operator
from .operators import pose_operator
from .operators import correct_bones_operator
from .operators import add_leg_d_bones_operator
from .operators import add_twist_bone_operator
from .operators import add_shoulder_p_bones_operator

# 辅助工具操作符 (tools/)
from .tools import export_bones_info_operator
from .tools import export_constraints_operator
from .tools import merge_bones_operator
from .tools import clear_unweighted_bones_operator
from .tools import chest_physics_builder
from .tools import body_rigid_builder
from .tools import clear_constraints_and_drivers_operator
from .tools import auto_connect_parent_bones_operator
from .tools import utility_operators


# ============================================================
# 所有需要注册的类，新增功能只需在此列表中添加一行
# ============================================================
CLASSES = [
    # UI 面板
    OBJECT_PT_skeleton_hierarchy,
    # 预设加载（原在 ui_panel.py 中）
    OBJECT_OT_load_preset,
    # 核心操作符
    export_bones_info_operator.OBJECT_OT_export_selected_bones_info,
    correct_bones_operator.OBJECT_OT_correct_bones,
    rename_bones_operator.OBJECT_OT_rename_to_mmd,
    complete_bones_operator.OBJECT_OT_complete_missing_bones,
    preset_operator.OBJECT_OT_fill_from_selection_specific,
    preset_operator.OBJECT_OT_export_preset,
    preset_operator.OBJECT_OT_import_preset,
    preset_operator.OBJECT_OT_use_mmd_tools_convert,
    preset_operator.OBJECT_OT_clear_bone_selection,
    pose_operator.OBJECT_OT_convert_to_apose,
    ik_operator.OBJECT_OT_add_ik,
    collection_operator.OBJECT_OT_create_bone_group,
    clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones,
    add_leg_d_bones_operator.OBJECT_OT_add_leg_d_bones,
    merge_bones_operator.OBJECT_OT_merge_leg_bones,
    merge_bones_operator.OBJECT_OT_merge_arm_bones,
    merge_bones_operator.OBJECT_OT_merge_selected_bones_weights,
    add_twist_bone_operator.OBJECT_OT_add_twist_bone,
    add_shoulder_p_bones_operator.OBJECT_OT_add_shoulder_p_bones,
    export_constraints_operator.OBJECT_OT_export_selected_bones_constraints,
    chest_physics_builder.OBJECT_OT_auto_physics_builder,
    body_rigid_builder.OBJECT_OT_build_simple_body_rigid,
    clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_constraints,
    clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_drivers,
    auto_connect_parent_bones_operator.OBJECT_OT_auto_connect_parent_bones,
    auto_connect_parent_bones_operator.OBJECT_OT_unlock_all_bones,
    # 辅助工具
    utility_operators.OBJECT_OT_convert_bones_rotation_to_quaternion,
    utility_operators.OBJECT_OT_split_bones_to_individual_objects,
]


def register():
    encoding_patch.apply_encoding_patch()
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    # 注册动态属性
    bones = preset_operator.get_bones_list()
    properties.register_properties(bones)

    # 注册 EnumProperty
    bpy.types.Scene.preset_enum = bpy.props.EnumProperty(
        name="预设",
        description="选择一个预设",
        items=get_preset_enum,
        update=preset_enum_update
    )
    bpy.types.Scene.my_enum = bpy.props.EnumProperty(
        name="模式",
        description="选择操作模式",
        items=[
            ('option1', "主骨骼管理", "预设管理和主骨骼转换操作"),
            ('option2', "次标准骨骼管理", "次标准骨骼追加和开发工具")
        ],
        default='option1'
    )
    bpy.types.Scene.merge_bones_also = bpy.props.BoolProperty(
        name="同时合并骨骼",
        description="勾选后，合并权重时同时将所选骨骼合并到活动项骨骼",
        default=False
    )


def unregister():
    encoding_patch.remove_encoding_patch()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

    # 注销动态属性
    bones = preset_operator.get_bones_list()
    properties.unregister_properties(bones)

    if hasattr(bpy.types.Scene, "preset_enum"):
        delattr(bpy.types.Scene, "preset_enum")
    if hasattr(bpy.types.Scene, "my_enum"):
        delattr(bpy.types.Scene, "my_enum")
    if hasattr(bpy.types.Scene, "merge_bones_also"):
        delattr(bpy.types.Scene, "merge_bones_also")


def get_preset_enum(self, context):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    presets_dir = os.path.join(script_dir, "presets")
    preset_items = []
    if os.path.exists(presets_dir):
        for preset_file in os.listdir(presets_dir):
            if preset_file.endswith('.json'):
                preset_name = os.path.splitext(preset_file)[0]
                preset_items.append((preset_name, preset_name, ""))
    return preset_items


def preset_enum_update(self, context):
    bpy.ops.object.load_preset(preset_name=self.preset_enum)
    return None


if __name__ == "__main__":
    register()
