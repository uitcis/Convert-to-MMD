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
import os  # 新增：导入os模块

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
from .tools import export_bones_info_operator
from .tools import export_constraints_operator
from .tools import merge_bones_operator
from .tools import clear_unweighted_bones_operator
from .tools import auto_physics_builder
from .tools import clear_constraints_and_drivers_operator
from .tools import auto_connect_parent_bones_operator
from . import ui_panel
from . import bone_map_and_group
from . import bone_utils
from . import properties
from . import encoding_patch

def register():
    # 应用中文编码补丁
    encoding_patch.apply_encoding_patch()
    # 注册所有类
    bpy.utils.register_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.register_class(ui_panel.OBJECT_OT_load_preset)
    bpy.utils.register_class(export_bones_info_operator.OBJECT_OT_export_selected_bones_info)
    bpy.utils.register_class(correct_bones_operator.OBJECT_OT_correct_bones)
    bpy.utils.register_class(rename_bones_operator.OBJECT_OT_rename_to_mmd)
    bpy.utils.register_class(complete_bones_operator.OBJECT_OT_complete_missing_bones)
    bpy.utils.register_class(preset_operator.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.register_class(preset_operator.OBJECT_OT_export_preset)
    bpy.utils.register_class(preset_operator.OBJECT_OT_import_preset)
    bpy.utils.register_class(preset_operator.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.register_class(preset_operator.OBJECT_OT_clear_bone_selection)
    bpy.utils.register_class(pose_operator.OBJECT_OT_convert_to_apose)
    bpy.utils.register_class(ik_operator.OBJECT_OT_add_ik)
    bpy.utils.register_class(collection_operator.OBJECT_OT_create_bone_group)
    bpy.utils.register_class(clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones)
    bpy.utils.register_class(add_leg_d_bones_operator.OBJECT_OT_add_leg_d_bones)
    bpy.utils.register_class(merge_bones_operator.OBJECT_OT_merge_leg_bones)
    bpy.utils.register_class(merge_bones_operator.OBJECT_OT_merge_arm_bones)
    bpy.utils.register_class(merge_bones_operator.OBJECT_OT_merge_selected_bones_weights)
    bpy.utils.register_class(add_twist_bone_operator.OBJECT_OT_add_twist_bone)
    bpy.utils.register_class(add_shoulder_p_bones_operator.OBJECT_OT_add_shoulder_p_bones)
    bpy.utils.register_class(export_constraints_operator.OBJECT_OT_export_selected_bones_constraints)
    bpy.utils.register_class(auto_physics_builder.OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(auto_physics_builder.OBJECT_OT_build_simple_body_rigid)
    bpy.utils.register_class(auto_physics_builder.OBJECT_OT_build_advanced_body_rigid)
    bpy.utils.register_class(clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_constraints)
    bpy.utils.register_class(clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_drivers)
    bpy.utils.register_class(auto_connect_parent_bones_operator.OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.register_class(auto_connect_parent_bones_operator.OBJECT_OT_unlock_all_bones)
    # 注册动态属性
    bones = preset_operator.get_bones_list()
    properties.register_properties(bones)

    # 注册 EnumProperty
    bpy.types.Scene.preset_enum = bpy.props.EnumProperty(
        name="预设",
        description="选择一个预设",
        items=get_preset_enum,
        update=preset_enum_update  # 使用显式函数替代 lambda
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
    bpy.types.Scene.body_rigid_min_segment_length = bpy.props.FloatProperty(
        name="最小段长度",
        description="刚体段的最小长度（米）",
        default=0.1,
        min=0.01,
        max=0.5
    )
    bpy.types.Scene.body_rigid_max_segment_length = bpy.props.FloatProperty(
        name="最大段长度",
        description="刚体段的最大长度（米）",
        default=0.2,
        min=0.01,
        max=1.0
    )    
def unregister():
    # 移除中文编码补丁
    encoding_patch.remove_encoding_patch()
    # 注销所有类
    bpy.utils.unregister_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.unregister_class(ui_panel.OBJECT_OT_load_preset)
    bpy.utils.unregister_class(export_bones_info_operator.OBJECT_OT_export_selected_bones_info)
    bpy.utils.unregister_class(correct_bones_operator.OBJECT_OT_correct_bones)
    bpy.utils.unregister_class(rename_bones_operator.OBJECT_OT_rename_to_mmd)
    bpy.utils.unregister_class(complete_bones_operator.OBJECT_OT_complete_missing_bones)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_export_preset)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_import_preset)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_clear_bone_selection)
    bpy.utils.unregister_class(pose_operator.OBJECT_OT_convert_to_apose)
    bpy.utils.unregister_class(ik_operator.OBJECT_OT_add_ik)
    bpy.utils.unregister_class(collection_operator.OBJECT_OT_create_bone_group)
    bpy.utils.unregister_class(clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones)
    bpy.utils.unregister_class(add_leg_d_bones_operator.OBJECT_OT_add_leg_d_bones)
    bpy.utils.unregister_class(merge_bones_operator.OBJECT_OT_merge_leg_bones)
    bpy.utils.unregister_class(merge_bones_operator.OBJECT_OT_merge_arm_bones)
    bpy.utils.unregister_class(merge_bones_operator.OBJECT_OT_merge_selected_bones_weights)
    bpy.utils.unregister_class(add_twist_bone_operator.OBJECT_OT_add_twist_bone)
    bpy.utils.unregister_class(add_shoulder_p_bones_operator.OBJECT_OT_add_shoulder_p_bones)
    bpy.utils.unregister_class(export_constraints_operator.OBJECT_OT_export_selected_bones_constraints)
    bpy.utils.unregister_class(auto_physics_builder.OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(auto_physics_builder.OBJECT_OT_build_simple_body_rigid)
    bpy.utils.unregister_class(auto_physics_builder.OBJECT_OT_build_advanced_body_rigid)
    bpy.utils.unregister_class(clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_constraints)
    bpy.utils.unregister_class(clear_constraints_and_drivers_operator.OBJECT_OT_clear_all_bone_drivers)
    bpy.utils.unregister_class(auto_connect_parent_bones_operator.OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.unregister_class(auto_connect_parent_bones_operator.OBJECT_OT_unlock_all_bones)
    # 注销动态属性
    bones = preset_operator.get_bones_list()
    properties.unregister_properties(bones)

    # 注销 EnumProperty
    if hasattr(bpy.types.Scene, "preset_enum"):
        delattr(bpy.types.Scene, "preset_enum")
    if hasattr(bpy.types.Scene, "merge_bones_also"):
        delattr(bpy.types.Scene, "merge_bones_also")
    if hasattr(bpy.types.Scene, "body_rigid_min_segment_length"):
        delattr(bpy.types.Scene, "body_rigid_min_segment_length")
    if hasattr(bpy.types.Scene, "body_rigid_max_segment_length"):
        delattr(bpy.types.Scene, "body_rigid_max_segment_length")

# 新增 EnumProperty 定义
def get_preset_enum(self, context):
    # 修改: 确保路径解析正确，使用bpy.utils.script_path_user()获取用户脚本目录
    script_dir = os.path.dirname(os.path.realpath(__file__))
    presets_dir = os.path.join(script_dir, "presets")
    preset_items = []
    if os.path.exists(presets_dir):
        for preset_file in os.listdir(presets_dir):
            if preset_file.endswith('.json'):
                # 修改: 使用文件名作为选项的标识符
                preset_name = os.path.splitext(preset_file)[0]
                preset_items.append((preset_name, preset_name, ""))
    return preset_items

# 修改: 将 update 回调函数改为显式函数定义
def preset_enum_update(self, context):
    # 调用加载预设的操作符
    bpy.ops.object.load_preset(preset_name=self.preset_enum)
    return None  # 确保返回值为 None

if __name__ == "__main__":
    register()