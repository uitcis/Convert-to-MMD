import bpy
import sys
from bpy.props import BoolProperty
from functools import lru_cache

@lru_cache(maxsize=None)
def load_bone_presets():
    from .bone_map_and_group import mmd_bone_group
    all_bones = set()
    try:
        valid_groups = []
        for group in mmd_bone_group:
            if not isinstance(group, dict):
                continue
            if 'name' not in group or 'bones' not in group:
                continue
            if not isinstance(group['bones'], list):
                continue
            valid_groups.append(group)

        if not valid_groups:
            raise ValueError("bone_map_and_group.py中未找到有效的骨骼分组配置")

        preset_dict = {}
        for p in valid_groups:
            if p['name'] not in preset_dict:
                cleaned_bones = list({b.strip() for b in p['bones'] if b.strip()})
                preset_dict[p['name']] = cleaned_bones
        all_bones.update(*(p['bones'] for p in valid_groups))
        return preset_dict, all_bones
    except Exception as e:
        print(f"加载骨骼分组配置失败: {str(e)}")
    return {}, set()

BONE_GROUPING_PRESETS, PRESET_BONES = load_bone_presets()

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
            self.report({'ERROR'}, "未找到有效的骨骼分组配置，请检查bone_map_and_group.py文件")
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
        
        # 预生成骨骼名称字典加速查询
        bone_dict = {b.name: b for b in armature.bones}
        
        # 批量删除集合操作
        if collections := getattr(armature, 'collections', None):
            # 适配Blender 4.0+的删除方式
            for coll in list(collections):
                collections.remove(coll)
        
        # 使用集合差集优化剩余骨骼计算
        remaining_bones = set(bone_dict.keys()) - PRESET_BONES
        print(f'预设应包含骨骼数量: {len(PRESET_BONES)} 实际骨骼数量: {len(bone_dict)} 初始剩余骨骼数量: {len(remaining_bones)}')
        
        # 批量创建集合并分配骨骼
        for group_name, bones in BONE_GROUPING_PRESETS.items():
            if valid_bones := [b for b in bones if b in bone_dict]:
                coll = armature.collections.new(group_name)
                for b in valid_bones:
                    coll.assign(bone_dict[b])
                remaining_bones -= set(valid_bones)
            print(f'处理分组【{group_name}】后剩余骨骼数量: {len(remaining_bones)}')

        # 优化other分组处理
        if remaining_bones:
            coll = armature.collections.new('other')
            for b in remaining_bones:
                coll.assign(bone_dict[b])

    def create_bone_groups(self, obj):
        # 使用预生成的骨骼字典
        bone_dict = {b.name: b for b in obj.data.bones}
        
        # 批量创建骨骼组
        groups_to_create = [g for g in BONE_GROUPING_PRESETS 
                          if g not in obj.pose.bone_groups]
        
        with bpy.context.temp_override(selected_objects=[obj],
                                      active_object=obj):
            for group_name in groups_to_create:
                bpy.ops.pose.group_add()
                obj.pose.bone_groups[-1].name = group_name
        
        # 使用字典加速查找
        group_dict = {g.name: g for g in obj.pose.bone_groups}
        
        # 批量分配骨骼组
        for group_name, bones in BONE_GROUPING_PRESETS.items():
            if group_name in group_dict:
                for b in bones:
                    if pose_bone := obj.pose.bones.get(b):
                        pose_bone.bone_group = group_dict[group_name]
        
        # 优化remaining_bones计算
        assigned = {b for g in BONE_GROUPING_PRESETS.values() for b in g}
        remaining_bones = set(bone_dict.keys()) - assigned
        
        if remaining_bones:
            other_group = group_dict.get('other') or obj.pose.bone_groups.new(name='other')
            for b in remaining_bones:
                if pose_bone := obj.pose.bones.get(b):
                    pose_bone.bone_group = other_group
