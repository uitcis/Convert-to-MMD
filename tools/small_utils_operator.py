import bpy


class OBJECT_OT_convert_bones_rotation_to_quaternion(bpy.types.Operator):
    """将所有骨骼的旋转模式转换为四元数 (Quaternion)"""
    bl_idname = "object.convert_bones_rotation_to_quaternion"
    bl_label = "转换为四元数旋转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 记录原模式以便恢复
        original_mode = obj.mode

        # 切换到姿态模式
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        converted_count = 0
        skipped_count = 0

        for p_bone in obj.pose.bones:
            if p_bone.rotation_mode != 'QUATERNION':
                p_bone.rotation_mode = 'QUATERNION'
                converted_count += 1
            else:
                skipped_count += 1

        # 恢复原模式
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode=original_mode)

        if converted_count > 0:
            self.report(
                {'INFO'},
                f"已将 {converted_count} 个骨骼的旋转模式转换为四元数"
                + (f"（{skipped_count} 个骨骼已是四元数）" if skipped_count > 0 else "")
            )
        else:
            self.report({'INFO'}, "所有骨骼已是四元数旋转模式，无需转换。")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_convert_bones_rotation_to_quaternion)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_convert_bones_rotation_to_quaternion)


if __name__ == "__main__":
    register()
