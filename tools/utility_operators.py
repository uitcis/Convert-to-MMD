import bpy

from .. import bone_utils


# ============================================================
# 通用工具操作符集合
# 放置不依赖特定业务流程的通用辅助工具
# ============================================================


class OBJECT_OT_convert_bones_rotation_to_quaternion(bpy.types.Operator):
    """将所有骨骼的旋转模式转换为四元数 (Quaternion)"""
    bl_idname = "object.convert_bones_rotation_to_quaternion"
    bl_label = "转换为四元数旋转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)

        if not obj:
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # rotation_mode 是姿态数据属性，任意模式下均可修改（无需切换到姿态模式）
        converted_count = 0
        skipped_count = 0

        for p_bone in obj.pose.bones:
            if p_bone.rotation_mode != 'QUATERNION':
                p_bone.rotation_mode = 'QUATERNION'
                converted_count += 1
            else:
                skipped_count += 1

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
