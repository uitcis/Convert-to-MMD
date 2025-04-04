import bpy
import sys
from bpy.props import BoolProperty

def load_bone_presets():
    import json
    from pathlib import Path

    json_path = Path(__file__).parent / 'bone_groups_info.json'
    try:
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                presets = json.load(f)
                preset_dict = {}
                for p in presets:
                    name = p.get('name')
                    if not name:
                        continue
                    if name in preset_dict:
                        print(f"发现重复的骨骼分组名称: {name}")
                        continue
                    # 使用集合去重骨骼名称
                    unique_bones = list({b for b in p['bones'] if b.strip()})
                    preset_dict[name] = unique_bones
                return preset_dict
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载预设文件失败: {str(e)}")
    
    if not json_path.exists():
        self.report({'ERROR'}, "未找到骨骼分组配置文件 bone_groups_info.json")
    return {}

BONE_GROUPING_PRESETS = load_bone_presets()

class OBJECT_OT_create_bone_grouping(bpy.types.Operator):
    bl_idname = "object.create_bone_grouping"
    bl_label = "创建骨骼集合"
    bl_description = "根据Blender版本自动创建骨骼组或骨骼集合"

    use_presets: BoolProperty(
        name="使用预设分组",
        description="使用预定义的骨骼分组配置",
        default=True
    )

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        if self.use_presets and not BONE_GROUPING_PRESETS:
            self.report({'ERROR'}, "未找到有效的骨骼分组配置，请检查bone_groups_info.json文件")
            return {'CANCELLED'}

        # 根据API特性自动适配版本
        if hasattr(obj.data, 'collections'):
            self.create_bone_collections(obj)
        else:
            self.create_bone_groups(obj)

        return {'FINISHED'}

    def create_bone_collections(self, obj):
        if not (armature := getattr(obj, 'data', None)):
            return
        
        # 安全清空现有骨骼集合
        # 完全使用新API并保持向后兼容
        for coll in list(getattr(armature, 'collections', [])):
            armature.collections.remove(coll)
        # 清理旧版本残留数据（适用于3.6之前版本）
        if not hasattr(armature, 'collections') and hasattr(armature, 'collections_all'):
            while armature.collections_all:
                armature.collections.remove(armature.collections_all[0])

        # 创建分组时添加保护判断
        target_groups = BONE_GROUPING_PRESETS if self.use_presets else {}
        for group_name, bones in (target_groups or {}).items():
            if bones:
                existing = next((coll for coll in armature.collections if coll.name == group_name), None)
                new_collection = existing or armature.collections.new(group_name)
                for bone_name in bones:
                    if bone := armature.bones.get(bone_name):
                        new_collection.assign(bone)

    def create_bone_groups(self, obj):
        armature = obj.data
        
        # 旧版本处理逻辑（Blender < 3.6）
        if hasattr(obj.pose.bones[0], 'bone_group'):
            # 旧版API处理：通过pose_bone直接操作
            bone_groups = {}
            
            if self.use_presets:
                # 创建临时bone_groups字典
                original_mode = obj.mode
                # 强制进入姿态模式
                if original_mode != 'POSE':
                    bpy.ops.object.mode_set(mode='POSE')
                
                # 使用临时上下文覆盖
                for group_name in BONE_GROUPING_PRESETS:
                    # 检查是否已存在同名骨骼组
                    existing_group = next((g for g in obj.pose.bone_groups if g.name == group_name), None)
                    if existing_group:
                        bone_groups[group_name] = existing_group
                        continue
                    
                    with bpy.context.temp_override(
                        selected_objects=[obj],
                        active_object=obj,
                        active_pose_bone=obj.pose.bones[0],
                        mode='POSE'
                    ):
                        bpy.ops.pose.group_add()
                        new_group = bpy.context.object.pose.bone_groups.active
                        if new_group:
                            new_group.name = group_name
                            bone_groups[group_name] = new_group
                        else:
                            self.report({'WARNING'}, f"骨骼组{group_name}创建失败，请检查Blender版本兼容性")
                            continue
                
                # 恢复原始模式
                if original_mode != 'POSE':
                    bpy.ops.object.mode_set(mode=original_mode)
            
            # 分配骨骼到对应组
            for group_name, bones in BONE_GROUPING_PRESETS.items():
                for bone_name in bones:
                    if (bone := armature.bones.get(bone_name)) and (pose_bone := obj.pose.bones.get(bone_name)):
                        pose_bone.bone_group = bone_groups.get(group_name)

        # 最终兼容性检查
        if not hasattr(obj.pose.bones[0], 'bone_group'):
            self.report({'ERROR'}, "当前Blender版本不支持旧式骨骼组功能")