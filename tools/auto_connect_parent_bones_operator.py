import bpy
from mathutils import Vector


class OBJECT_OT_auto_connect_parent_bones(bpy.types.Operator):
    """自动将头部与尾部位置匹配的骨骼设为父子关系（保持偏移量）"""
    bl_idname = "object.auto_connect_parent_bones"
    bl_label = "自动连接父级骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架对象")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        precision = 2
        connection_count = 0

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
            parent_bones = tail_map.get(key)
            if parent_bones:
                for parent_bone in parent_bones:
                    if parent_bone != child_bone:
                        child_bone.parent = parent_bone
                        child_bone.use_connect = False
                        connection_count += 1
                        break

        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"已自动连接 {connection_count} 个骨骼的父子关系")
        return {'FINISHED'}


class OBJECT_OT_unlock_all_bones(bpy.types.Operator):
    """解锁所有骨骼的旋转、位置锁定"""
    bl_idname = "object.unlock_all_bones"
    bl_label = "解锁所有骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架对象")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='POSE')
        for pose_bone in obj.pose.bones:
            pose_bone.bone.use_inherit_rotation = True
            pose_bone.lock_rotation[0] = False
            pose_bone.lock_rotation[1] = False
            pose_bone.lock_rotation[2] = False
            pose_bone.lock_rotation_w = False
            pose_bone.lock_location[0] = False
            pose_bone.lock_location[1] = False
            pose_bone.lock_location[2] = False

        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"已解锁 {len(obj.pose.bones)} 个骨骼的旋转、位置锁定")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.register_class(OBJECT_OT_unlock_all_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_connect_parent_bones)
    bpy.utils.unregister_class(OBJECT_OT_unlock_all_bones)
