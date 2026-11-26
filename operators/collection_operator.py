import bpy
from bpy.props import BoolProperty
from functools import lru_cache

from .. import bone_utils

@lru_cache(maxsize=None)
def load_bone_presets():
    from ..bone_map_and_group import mmd_bone_group
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
        group_visibility = {}
        for p in valid_groups:
            if p['name'] not in preset_dict:
                cleaned_bones = list({b.strip() for b in p['bones'] if b.strip()})
                preset_dict[p['name']] = cleaned_bones
                group_visibility[p['name']] = p.get('visible', True)
        all_bones.update(*(p['bones'] for p in valid_groups))
        return preset_dict, all_bones, group_visibility
    except Exception as e:
        print(f"加载骨骼分组配置失败: {str(e)}")
    return {}, set(), {}

BONE_GROUP_PRESETS, PRESET_BONES, GROUP_VISIBILITY = load_bone_presets()

class OBJECT_OT_create_bone_group(bpy.types.Operator):
    bl_idname = "object.create_bone_group"
    bl_label = "创建骨骼集合"
    bl_description = "根据Blender版本自动创建骨骼组或骨骼集合"

    use_presets: BoolProperty(
        name="使用预设分组",
        description="使用预定义的骨骼分组配置",
        default=True
    )

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        if self.use_presets and not BONE_GROUP_PRESETS:
            self.report({'ERROR'}, "未找到有效的骨骼分组配置，请检查bone_map_and_group.py文件")
            return {'CANCELLED'}

        # 根据API特性自动适配版本
        if hasattr(obj.data, 'collections'):
            self.create_bone_collections(obj)
        else:
            self.create_bone_groups(obj)

        return {'FINISHED'}

    def _report_changes(self, changes):
        """把归组改动写入报告：骨骼名 + 原集合 → 目标集合。"""
        if not changes:
            self.report({'INFO'}, "骨骼集合已符合预设，无需调整")
            return
        self.report({'INFO'},
                    f"骨骼集合调整 {len(changes)} 项（格式：骨骼: 原集合 → 目标集合）")
        for i in range(0, len(changes), 3):
            self.report({'INFO'}, "；".join(changes[i:i + 3]))
        for line in changes:
            print(f"[骨骼集合] {line}")

    def _preset_owner_map(self, bone_dict):
        """骨骼名 -> 目标预设集合名（同一骨骼只取第一个预设组）。"""
        owner = {}
        for group_name, bones in BONE_GROUP_PRESETS.items():
            for bone_name in bones:
                if bone_name in bone_dict:
                    owner.setdefault(bone_name, group_name)
        return owner

    def create_bone_collections(self, obj):
        armature = getattr(obj, 'data', None)
        if not armature:
            return

        bone_dict = {b.name: b for b in armature.bones}
        existing = {coll.name: coll for coll in armature.collections}
        changes = []
        owner = self._preset_owner_map(bone_dict)

        # 补建缺失的预设集合；已有集合（含用户自建）保持原样
        for group_name, bones in BONE_GROUP_PRESETS.items():
            if not any(b in bone_dict for b in bones):
                continue
            coll = existing.get(group_name)
            if coll is None:
                coll = armature.collections.new(group_name)
                coll.is_visible = GROUP_VISIBILITY.get(group_name, True)
                existing[group_name] = coll

        # 归组（始终严格校正）：
        # 预设骨骼只保留在目标集合，从其它集合移除（集合本身不删）；
        # 用户自建集合和非预设骨骼不受影响。
        for bone_name, target_name in owner.items():
            bone = bone_dict[bone_name]
            target = existing.get(target_name)
            if target is None:
                continue
            current = [coll for coll in armature.collections
                       if bone_name in {b.name for b in coll.bones}]
            in_target = target in current
            extras = [coll for coll in current if coll != target]
            if extras:
                for coll in extras:
                    coll.unassign(bone)
                changes.append(
                    f"{bone_name}: {', '.join(c.name for c in extras)} → {target_name}")
            if not in_target:
                target.assign(bone)
                if not extras:
                    changes.append(f"{bone_name}: 无 → {target_name}")

        # 未加入任何集合的骨骼归入 other；非预设骨骼原有归属不动
        assigned = set()
        for coll in armature.collections:
            assigned.update(b.name for b in coll.bones)
        remaining_bones = [name for name in bone_dict if name not in assigned]
        if remaining_bones:
            coll = existing.get('other')
            if coll is None:
                coll = armature.collections.new('other')
                coll.is_visible = True
                existing['other'] = coll
            for name in remaining_bones:
                coll.assign(bone_dict[name])
                changes.append(f"{name}: 无 → other")

        self._report_changes(changes)

    def create_bone_groups(self, obj):
        bone_dict = {b.name: b for b in obj.data.bones}

        # 批量创建骨骼组
        groups_to_create = [g for g in BONE_GROUP_PRESETS
                            if g not in obj.pose.bone_groups]

        with bpy.context.temp_override(selected_objects=[obj],
                                       active_object=obj):
            for group_name in groups_to_create:
                bpy.ops.pose.group_add()
                obj.pose.bone_groups[-1].name = group_name

        group_dict = {g.name: g for g in obj.pose.bone_groups}
        owner = self._preset_owner_map(bone_dict)
        changes = []

        for bone_name, target_name in owner.items():
            pose_bone = obj.pose.bones.get(bone_name)
            target = group_dict.get(target_name)
            if pose_bone is None or target is None:
                continue
            if pose_bone.bone_group is None:
                pose_bone.bone_group = target
                changes.append(f"{bone_name}: 无 → {target_name}")
            elif pose_bone.bone_group != target:
                # 始终按预设严格归组
                changes.append(f"{bone_name}: {pose_bone.bone_group.name} → {target_name}")
                pose_bone.bone_group = target

        # 计算未分配骨骼
        remaining_bones = [
            name for name, pose_bone in ((b.name, b) for b in obj.pose.bones)
            if pose_bone.bone_group is None
        ]
        print(f'总骨骼数: {len(bone_dict)} 未分配: {len(remaining_bones)}')

        if remaining_bones:
            other_group = group_dict.get('other') or obj.pose.bone_groups.new(name='other')
            for b in remaining_bones:
                if pose_bone := obj.pose.bones.get(b):
                    pose_bone.bone_group = other_group
                    changes.append(f"{b}: 无 → other")

        self._report_changes(changes)
