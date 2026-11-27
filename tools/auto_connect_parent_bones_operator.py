import bpy
from mathutils import Vector

from .. import bone_utils


class OBJECT_OT_auto_connect_parent_bones(bpy.types.Operator):
    """自动将头部与尾部位置匹配的骨骼设为父子关系（保持偏移量）"""
    bl_idname = "object.auto_connect_parent_bones"
    bl_label = "自动连接父级骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'WARNING'}, "请选择一个骨架对象")
            return {'CANCELLED'}

        original_mode = obj.mode
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        precision = 2
        connection_count = 0
        ambiguous = []

        tail_map = {}
        for bone in edit_bones:
            tail = bone.tail
            key = (round(tail.x, precision), round(tail.y, precision), round(tail.z, precision))
            if key not in tail_map:
                tail_map[key] = []
            tail_map[key].append(bone)

        for child_bone in edit_bones:
            if child_bone.parent:
                continue
            head = child_bone.head
            key = (round(head.x, precision), round(head.y, precision), round(head.z, precision))
            candidates = [b for b in tail_map.get(key, []) if b != child_bone]
            if not candidates:
                continue
            if len(candidates) > 1:
                # 坐标重合时无法确定唯一父级，跳过并提示，避免挂错父级
                ambiguous.append((child_bone.name, [c.name for c in candidates]))
                continue
            child_bone.parent = candidates[0]
            child_bone.use_connect = False
            connection_count += 1

        for child_name, candidate_names in ambiguous:
            message = (f"{child_name} 的父级候选不唯一（{', '.join(candidate_names)}），已跳过")
            self.report({'WARNING'}, message)
            print(f"[自动连接] {message}")

        if obj.mode != original_mode:
            bpy.ops.object.mode_set(mode=original_mode)

        self.report({'INFO'}, f"已自动连接 {connection_count} 个骨骼的父子关系"
                              + (f"，跳过 {len(ambiguous)} 个歧义骨骼" if ambiguous else ""))
        return {'FINISHED'}


class OBJECT_OT_unlock_all_bones(bpy.types.Operator):
    """解锁所有骨骼的旋转、位置锁定"""
    bl_idname = "object.unlock_all_bones"
    bl_label = "解锁所有骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'WARNING'}, "请选择一个骨架对象")
            return {'CANCELLED'}

        # 锁定属性是姿态数据属性，任意模式下均可修改（无需切换模式）
        # 只解除锁定，不改变 use_inherit_rotation 等绑定行为
        for pose_bone in obj.pose.bones:
            pose_bone.lock_rotation[0] = False
            pose_bone.lock_rotation[1] = False
            pose_bone.lock_rotation[2] = False
            pose_bone.lock_rotation_w = False
            pose_bone.lock_location[0] = False
            pose_bone.lock_location[1] = False
            pose_bone.lock_location[2] = False

        self.report({'INFO'}, f"已解锁 {len(obj.pose.bones)} 个骨骼的旋转、位置锁定")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.register_class(OBJECT_OT_unlock_all_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.unregister_class(OBJECT_OT_unlock_all_bones)
