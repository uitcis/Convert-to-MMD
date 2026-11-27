import bpy
from .. import bone_utils


class OBJECT_OT_calculate_bone_rolls(bpy.types.Operator):
    """按骨骼名与几何方向计算扭转（roll）：

    - 手臂链/扭转骨/手指：左侧→全局+Z，右侧→全局-Z
    - 其余所有骨骼：头部高于尾部→全局+Y，否则→全局-Y
    """
    bl_idname = "object.calculate_bone_rolls"
    bl_label = "设置骨骼扭转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'WARNING'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        original_mode = context.mode
        # mode_set 只接受 OBJECT/EDIT/POSE，而 context.mode 返回 'EDIT_ARMATURE' 等值
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones

        # 检测是否为 MMD 骨架：未检测到任何 MMD 标准骨骼则提示并跳过（非MMD骨骼无作用）
        if bone_utils.count_mmd_bones(edit_bones) == 0:
            if context.mode != original_mode:
                bpy.ops.object.mode_set(mode=restore_mode)
            self.report({'WARNING'}, "未检测到MMD骨骼：非MMD骨骼无作用，操作已跳过。")
            return {'CANCELLED'}

        # 按骨骼名与几何方向计算扭转：
        #   手臂链/扭转骨/手指 → 左侧全局+Z、右侧全局-Z；其余 → 头高于尾用+Y、否则-Y
        adjusted, local_count, fallback_count = bone_utils.calculate_auto_bone_roll(
            edit_bones, armature_obj=obj)

        # 恢复进入时的模式（context.mode 的值需转换为 mode_set 接受的枚举）
        if context.mode != original_mode:
            bpy.ops.object.mode_set(mode=restore_mode)

        if adjusted > 0:
            self.report({'INFO'},
                f"已设置扭转：局部轴骨骼(±Z) {local_count} 根、其余骨骼(±Y) {fallback_count} 根，共调整 {adjusted} 根。")
        else:
            self.report({'INFO'}, "所有骨骼扭转值已符合规则（无需调整）。")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_calculate_bone_rolls)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_calculate_bone_rolls)


if __name__ == "__main__":
    register()
