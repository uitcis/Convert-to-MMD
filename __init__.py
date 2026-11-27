bl_info = {
    "name": "Convert to MMD",
    "author": "UITCIS(空想幻灵)",
    "version": (2, 6),
    "blender": (4, 0, 0),  # 最低支持 Blender 4.0
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
from .operators import auto_mapping_operator

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
from .tools import arm_forearm_tool
from .tools import adjust_bone_rolls_operator


# ============================================================
# 骨骼备份清理操作符
# ============================================================
class OBJECT_OT_cleanup_backups(bpy.types.Operator):
    """清理所有骨架备份对象"""
    bl_idname = "object.cleanup_backups"
    bl_label = "清理备份"
    bl_description = "清理所有自动生成的骨架备份对象，释放内存和文件空间"

    def execute(self, context):
        """执行备份清理

        Returns:
            dict: Blender operator 返回状态
        """
        removed_count = 0
        removed_data_count = 0

        # 清理备份对象：只处理骨架备份，避免误删用户自己的 *_backup 网格/空物体
        for obj in list(bpy.data.objects):
            if obj.type != 'ARMATURE':
                continue
            obj_data = obj.data
            is_backup = (obj.name.endswith("_backup")
                         or (obj_data is not None and obj_data.name.endswith("_backup")))
            if is_backup:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    removed_count += 1
                except Exception as e:
                    print(f"[Convert-to-MMD] 清理备份对象失败: {obj.name} - {e}")

        # 清理未使用的数据块
        for block in list(bpy.data.armatures):
            if block.name.endswith("_backup") and block.users == 0:
                try:
                    bpy.data.armatures.remove(block)
                    removed_data_count += 1
                except Exception as e:
                    print(f"[Convert-to-MMD] 清理备份数据块失败: {block.name} - {e}")

        self.report({'INFO'}, f"已清理 {removed_count} 个备份对象，{removed_data_count} 个数据块")
        return {'FINISHED'}


# ============================================================
# 所有需要注册的类，新增功能只需在此列表中添加一行
# ============================================================
CLASSES = [
    # UI 面板
    OBJECT_PT_skeleton_hierarchy,
    # 预设加载（原在 ui_panel.py 中）
    OBJECT_OT_load_preset,
    # 骨骼备份清理
    OBJECT_OT_cleanup_backups,
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
    auto_mapping_operator.OBJECT_OT_auto_detect_bone_mapping,
    auto_mapping_operator.OBJECT_OT_view_auto_mapping_report,
    pose_operator.OBJECT_OT_convert_to_apose,
    ik_operator.OBJECT_OT_add_ik,
    collection_operator.OBJECT_OT_create_bone_group,
    clear_unweighted_bones_operator.OBJECT_OT_clear_unweighted_bones,
    add_leg_d_bones_operator.OBJECT_OT_add_leg_d_bones,
    merge_bones_operator.OBJECT_OT_merge_leg_bones,
    merge_bones_operator.OBJECT_OT_merge_arm_bones,
    merge_bones_operator.OBJECT_OT_merge_selected_bones_weights,
    merge_bones_operator.OBJECT_OT_merge_selected_bones_and_weights,
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
    arm_forearm_tool.OBJECT_OT_align_forearm_from_selection,
    adjust_bone_rolls_operator.OBJECT_OT_calculate_bone_rolls,
]


def register():
    encoding_patch.apply_encoding_patch()
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    # 注册动态属性
    bones = preset_operator.get_bones_list()
    properties.register_properties(bones)
    properties.register_convert_options()

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
            ('option2', "次标准骨骼与物理", "次标准骨骼追加和刚体构建"),
            ('option3', "通用工具", "骨骼通用操作和调试工具"),
        ],
        default='option1'
    )

    # 自动骨骼映射结果摘要（供面板显示与低置信度高亮）
    bpy.types.Scene.auto_map_summary = bpy.props.StringProperty(
        name="自动映射摘要",
        description="最近一次自动骨骼映射的结果摘要",
        default="",
    )
    bpy.types.Scene.auto_map_low_confidence = bpy.props.StringProperty(
        name="低置信度详情",
        description="置信度低于阈值、已留空的字段及最佳候选分数",
        default="",
    )
    bpy.types.Scene.auto_map_low_conf_fields = bpy.props.StringProperty(
        name="低置信度字段",
        description="置信度不足的字段名（逗号分隔），用于面板高亮",
        default="",
    )
    bpy.types.Scene.auto_map_report_path = bpy.props.StringProperty(
        name="映射依据报告路径",
        description="最近一次自动骨骼映射依据的临时文件路径",
        default="",
    )


def unregister():
    encoding_patch.remove_encoding_patch()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

    # 注销动态属性（更安全的删除方式）
    bones = preset_operator.get_bones_list()
    properties.unregister_properties(bones)
    properties.unregister_convert_options()

    # 安全删除属性，忽略不存在的情况
    for attr_name in ["preset_enum", "my_enum", "auto_map_summary",
                      "auto_map_low_confidence", "auto_map_low_conf_fields",
                      "auto_map_report_path"]:
        try:
            delattr(bpy.types.Scene, attr_name)
        except AttributeError:
            pass  # 属性不存在，忽略

    # 清理缓存
    global _preset_cache, _preset_cache_mtime
    _preset_cache = None
    _preset_cache_mtime = 0

    # 清理未执行的预设加载定时器
    global _preset_load_timer
    if _preset_load_timer is not None:
        try:
            bpy.app.timers.unregister(_preset_load_timer)
        except ValueError:
            pass  # 定时器已被移除，忽略
        _preset_load_timer = None


# 预设枚举缓存变量
_preset_cache = None
_preset_cache_mtime = 0

# 预设加载定时器句柄（防止定时器堆积）
_preset_load_timer = None


def get_preset_enum(self, context):
    """获取预设枚举，使用缓存优化性能。

    Args:
        self: Scene 对象
        context: Blender 上下文对象

    Returns:
        包含预设信息的元组列表，每个元组格式为 (identifier, name, description)
    """
    global _preset_cache, _preset_cache_mtime

    script_dir = os.path.dirname(os.path.realpath(__file__))
    presets_dir = os.path.join(script_dir, "presets")

    # 检查缓存是否有效
    current_mtime = os.path.getmtime(presets_dir) if os.path.exists(presets_dir) else 0
    if _preset_cache is not None and _preset_cache_mtime == current_mtime:
        return _preset_cache

    # 重建缓存
    preset_items = []
    if os.path.exists(presets_dir):
        for preset_file in os.listdir(presets_dir):
            if preset_file.endswith('.json'):
                preset_name = os.path.splitext(preset_file)[0]
                preset_items.append((preset_name, preset_name, ""))

    _preset_cache = preset_items
    _preset_cache_mtime = current_mtime
    return preset_items


def preset_enum_update(self, context):
    """延迟执行预设加载，避免阻塞 UI 和无限递归风险。

    使用 Blender 的 timer 延迟到下一帧执行，确保：
    1. UI 响应不阻塞（update 回调需在 <10ms 内完成）
    2. 避免因 operator 修改 preset_enum 导致的无限递归
    3. timer 只执行一次，执行后自动移除

    Args:
        self: Scene 对象
        context: Blender 上下文对象

    Returns:
        None
    """
    global _preset_load_timer

    # 捕获当前选择的预设名（防止延迟期间用户再次切换导致值错乱）
    preset_name = self.preset_enum

    # 移除之前未执行的定时器，避免快速切换时堆积
    if _preset_load_timer is not None:
        try:
            bpy.app.timers.unregister(_preset_load_timer)
        except ValueError:
            pass
        _preset_load_timer = None

    def delayed_load():
        """延迟加载预设的实际执行函数（timer 只执行一次）"""
        global _preset_load_timer
        _preset_load_timer = None
        try:
            bpy.ops.object.load_preset(preset_name=preset_name)
        except Exception as e:
            print(f"[Convert-to-MMD] 预设加载失败: {e}")
        return None  # 返回 None 表示只执行一次

    # 延迟到下一帧执行（load_post 只在文件加载时触发，不适用于此场景）
    _preset_load_timer = bpy.app.timers.register(delayed_load, first_interval=0.01)
    return None


if __name__ == "__main__":
    register()
