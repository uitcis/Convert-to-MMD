import bpy
from .. import bone_map_and_group
from .. import bone_utils
from . import preset_operator


class OBJECT_OT_rename_to_mmd(bpy.types.Operator):
    """将选定的骨骼重命名为 MMD 格式"""
    bl_idname = "object.rename_to_mmd"
    bl_label = "Rename to MMD"

    mmd_bone_map = bone_map_and_group.mmd_bone_map  # 使用导入的bone_map模块

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        # 检查选择框里是否有骨骼设置（提前校验，避免无谓的模式切换）
        has_bone_set = False
        for prop_name in preset_operator.get_bones_list():  # 从operations.py中获取骨骼属性名称列表
            if getattr(scene, prop_name, None):
                has_bone_set = True
                break
        if not has_bone_set:
            self.report({'WARNING'}, "未设置骨骼")
            return {'CANCELLED'}

        # 记录进入时的模式，结束时恢复（尽量复用已有模式窗口，减少切换）
        original_mode = context.mode
        # mode_set 只接受 OBJECT/EDIT/POSE，而 context.mode 返回 'EDIT_ARMATURE' 等值
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)

        # === 骨骼备份管理 ===
        # 1. 删除旧的备份对象（如果存在），避免累积
        old_backup_name = f"{obj.name}_backup"
        if old_backup_name in bpy.data.objects:
            try:
                old_backup_obj = bpy.data.objects[old_backup_name]
                bpy.data.objects.remove(old_backup_obj, do_unlink=True)
                print(f"[Convert-to-MMD] 已删除旧备份: {old_backup_name}")
            except Exception as e:
                print(f"[Convert-to-MMD] 删除旧备份失败: {e}")

        # 2. 创建新的骨架备份
        # 使用直接的方式复制对象，避免上下文问题
        backup_data = obj.data.copy()
        backup_data.name = f"{obj.data.name}_backup"
        backup_obj = bpy.data.objects.new(f"{obj.name}_backup", backup_data)
        bpy.context.collection.objects.link(backup_obj)

        # 设置备份对象的属性
        backup_obj.matrix_world = obj.matrix_world
        backup_obj.hide_viewport = True
        backup_obj.hide_render = True

        self.report({'INFO'}, f"已创建骨架备份: {backup_obj.name} (数据块: {backup_obj.data.name})")
        print(f"[Convert-to-MMD] 备份创建成功: {backup_obj.name}")
        # === 备份管理结束 ===

        # 检测骨架高度并自动缩放（内部已包含模式切换，结束时可能停在 OBJECT 或 EDIT）
        scaled, scale_factor, skeleton_height = bone_utils.check_and_scale_skeleton(obj)
        
        if scaled:
            self.report({'INFO'}, f"骨架高度为 {skeleton_height:.2f}m，已缩放 {scale_factor:.3f} 倍")

        # 后续重命名、设扭转、链检测统一在编辑模式完成，只进一次编辑模式
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        # 自动检测上半身骨骼链（重命名前，用原始名称识别中间骨骼）
        preset_operator.auto_detect_upper_body_chain(scene, obj)
        
        for prop_name, new_name in self.mmd_bone_map.items():
            bone_name = getattr(scene, prop_name, None)
            if bone_name:
                bone = edit_bones.get(bone_name)
                if bone:
                    # 检查骨骼是否已经重命名为 MMD 格式名称
                    if bone.name != new_name:
                        bone.name = new_name
                        # 更新场景中的骨骼属性值
                        setattr(scene, prop_name, new_name)
                    else:
                        self.report({'INFO'}, f"骨骼 '{bone_name}' 已经重命名为 {new_name}")
                else:
                    self.report({'WARNING'}, f"未找到骨骼 '{bone_name}' 以重命名为 {new_name}")
        
        # 重命名完成后，直接在编辑模式按新规则设置骨骼扭转（几何/按名，复刻 Shift+N 全局 ±Z/±Y）
        adjusted, local_count, fallback_count = bone_utils.calculate_auto_bone_roll(edit_bones, armature_obj=obj)
        if adjusted:
            self.report({'INFO'}, f"已设置骨骼扭转：局部轴(±Z) {local_count} 根、其余(±Y) {fallback_count} 根，共调整 {adjusted} 根。")

        # 恢复进入时的模式（context.mode 的值需转换为 mode_set 接受的枚举）
        if context.mode != original_mode:
            bpy.ops.object.mode_set(mode=restore_mode)

        # 用MMD名称重新检测上半身骨骼链，确保属性与重命名后的骨骼一致。
        # Armature.bones 只在对象模式下反映最新数据，编辑模式读到的是进入编辑模式时的快照，
        # 因此必须在对象模式执行检测，检测完成后再恢复用户原来的模式。
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        preset_operator.auto_detect_upper_body_chain(scene, obj)
        if context.mode != original_mode:
            bpy.ops.object.mode_set(mode=restore_mode)

        # 打开骨骼名称显示
        bpy.context.object.data.show_names = True

        return {'FINISHED'}

    def rename_finger_bone(self, context, obj, scene, base_finger_name, segment):
        for side in ["left", "right"]:
            prop_name = f"{side}_{base_finger_name}_{segment}"
            if prop_name in self.mmd_bone_map:
                new_name = self.mmd_bone_map.get(prop_name)
                bone_name = getattr(scene, prop_name, None)
                if bone_name:
                    bone = obj.pose.bones.get(bone_name)
                    if bone:
                        # Check if the bone has already been renamed to the MMD format name
                        if bone.name != new_name:
                            bone.name = new_name
                            # Update the bone property value in the scene
                            setattr(scene, prop_name, new_name)
                        else:
                            self.report({'INFO'}, f"Bone '{bone_name}' is already renamed to {new_name}")
                    else:
                        self.report({'WARNING'}, f"Bone '{bone_name}' not found for renaming to {new_name}")


def register():
    bpy.utils.register_class(OBJECT_OT_rename_to_mmd)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_rename_to_mmd)


if __name__ == "__main__":
    register()
