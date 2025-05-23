bl_info = {
    "name": "Convert to MMD",
    "author": "UITCIS(空想幻灵)",
    "version": (2, 2),
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
from .operators import bone_operator
from .operators import collection_operator
from .operators import ik_operator
from .operators import pose_operator
from .operators import clear_unweighted_bones_operator
from . import ui_panel
from . import bone_map_and_group
from . import bone_utils
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
    # 注册所有类
    bpy.utils.register_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.register_class(ui_panel.OBJECT_OT_load_preset)
    bpy.utils.register_class(bone_operator.OBJECT_OT_rename_to_mmd)
    bpy.utils.register_class(bone_operator.OBJECT_OT_complete_missing_bones)
    bpy.utils.register_class(preset_operator.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.register_class(preset_operator.OBJECT_OT_export_preset)
    bpy.utils.register_class(preset_operator.OBJECT_OT_import_preset)
    bpy.utils.register_class(preset_operator.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.register_class(pose_operator.OBJECT_OT_convert_to_apose)
    bpy.utils.register_class(ik_operator.OBJECT_OT_add_ik)
    bpy.utils.register_class(collection_operator.OBJECT_OT_create_bone_group)
    bpy.utils.register_class(clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones)
    bpy.utils.register_class(clear_unweighted_bones_operator.OBJECT_OT_merge_single_child_bones)
    # 注册动态属性
    bones = preset_operator.get_bones_list()
    register_properties(bones)

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
            ('option1', "骨骼映射", "进行骨骼映射"),
            ('option2', "骨骼清理", "进行骨骼清理")
        ],
        default='option1'
    )    
def unregister():
    # 注销所有类
    bpy.utils.unregister_class(ui_panel.OBJECT_PT_skeleton_hierarchy)
    bpy.utils.unregister_class(ui_panel.OBJECT_OT_load_preset)
    bpy.utils.unregister_class(bone_operator.OBJECT_OT_rename_to_mmd)
    bpy.utils.unregister_class(bone_operator.OBJECT_OT_complete_missing_bones)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_fill_from_selection_specific)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_export_preset)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_import_preset)
    bpy.utils.unregister_class(preset_operator.OBJECT_OT_use_mmd_tools_convert)
    bpy.utils.unregister_class(pose_operator.OBJECT_OT_convert_to_apose)
    bpy.utils.unregister_class(ik_operator.OBJECT_OT_add_ik)
    bpy.utils.unregister_class(collection_operator.OBJECT_OT_create_bone_group)
    bpy.utils.unregister_class(clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones)
    bpy.utils.unregister_class(clear_unweighted_bones_operator.OBJECT_OT_merge_single_child_bones)
    del bpy.types.Scene.my_enum
    # 注销动态属性
    bones = preset_operator.get_bones_list()
    unregister_properties(bones)

    # 注销 EnumProperty
    if hasattr(bpy.types.Scene, "preset_enum"):
        delattr(bpy.types.Scene, "preset_enum")

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