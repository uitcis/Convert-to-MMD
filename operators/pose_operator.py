import bpy
import math
from mathutils import Matrix, Vector
from .. import bone_utils
from ..bone_utils import apply_armature_transforms
# 新增的T-Pose到A-Pose转换操作符
class OBJECT_OT_convert_to_apose(bpy.types.Operator):
    """将骨架转换为 A-Pose 并应用为新的静置姿态"""
    bl_idname = "object.convert_to_apose" 
    bl_label = "Convert to A-Pose"

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'} 
        if not apply_armature_transforms(context, obj):
            self.report({'ERROR'}, "应用骨架变换失败")
            return {'CANCELLED'}
        scene = context.scene
        
        # 获取骨骼名称
        arm_bones = {
            "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
            "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
            "left_lower_arm": getattr(scene, "left_lower_arm_bone", ""),
            "right_lower_arm": getattr(scene, "right_lower_arm_bone", ""),          
        }

        # 检查是否有设置骨骼
        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置要转换的骨骼")
            return {'CANCELLED'}
        #作用：备份所有网格的形态键，包括基础键
        def backup_shape_keys(mesh_obj):
            backup = {}
            if mesh_obj.data.shape_keys and mesh_obj.data.shape_keys.key_blocks:
                basis = mesh_obj.data.shape_keys.key_blocks[0]
                for key_block in mesh_obj.data.shape_keys.key_blocks[1:]:
                    affected = {}
                    for i, v in enumerate(key_block.data):
                        if v.co != basis.data[i].co:
                            affected[i] = v.co - basis.data[i].co
                    backup[key_block.name] = {
                        'affected': affected,
                        'relative_key': key_block.relative_key.name if key_block.relative_key else None,
                        'slider_min': key_block.slider_min,
                        'slider_max': key_block.slider_max,
                        'mute': key_block.mute,
                        'value': key_block.value
                    }
            if mesh_obj.data.shape_keys:
                keys_to_remove = list(mesh_obj.data.shape_keys.key_blocks)
                for key_block in reversed(keys_to_remove):
                    mesh_obj.shape_key_remove(key_block)
            return backup

        def restore_shape_keys(mesh_obj, backup):
            if not backup:
                return
            context.view_layer.objects.active = mesh_obj
            bpy.ops.object.shape_key_add(from_mix=False)
            new_basis = mesh_obj.data.shape_keys.key_blocks[0]
            for key_name, key_data in backup.items():
                new_key = mesh_obj.shape_key_add(name=key_name)
                for i, delta in key_data['affected'].items():
                    new_key.data[i].co = new_basis.data[i].co + delta
                new_key.slider_min = key_data['slider_min']
                new_key.slider_max = key_data['slider_max']
                new_key.mute = key_data['mute']
                new_key.value = key_data['value']
                if key_data['relative_key'] and key_data['relative_key'] in mesh_obj.data.shape_keys.key_blocks:
                    new_key.relative_key = mesh_obj.data.shape_keys.key_blocks[key_data['relative_key']]

        meshes_with_armature = []
        shape_key_backups = {}
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type == 'MESH':
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj:
                        shape_key_backups[mesh_obj.name] = backup_shape_keys(mesh_obj)
                        meshes_with_armature.append(mesh_obj)
                        break

        if not meshes_with_armature:
            self.report({'WARNING'}, "未找到有上臂权重的网格，跳过网格姿态调整")

        # 切换到编辑模式，将upper_arm的尾部连接到lowerarm的头部
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones
        
        # 获取骨骼位置（先验证骨骼是否存在）
        missing = [f"{k}='{v}'" for k, v in arm_bones.items() if v and v not in edit_bones]
        if missing:
            bpy.ops.object.mode_set(mode='OBJECT')
            self.report({'ERROR'}, f"编辑模式中未找到以下骨骼：{'; '.join(missing)}")
            return {'CANCELLED'}
        
        left_upper_arm = edit_bones[arm_bones["left_upper_arm"]]
        left_lower_arm = edit_bones[arm_bones["left_lower_arm"]]
        right_upper_arm = edit_bones[arm_bones["right_upper_arm"]]
        right_lower_arm = edit_bones[arm_bones["right_lower_arm"]]
        
        # 调整尾部位置
        left_upper_arm.tail = left_lower_arm.head
        right_upper_arm.tail = right_lower_arm.head

        # 5. 为每个网格复制骨骼修改器，但保留原始修改器
        for mesh_obj in meshes_with_armature:
            for modifier in mesh_obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object == obj:
                    # 复制修改器
                    new_modifier = mesh_obj.modifiers.new(name=modifier.name + "_copy", type='ARMATURE')
                    new_modifier.object = modifier.object
                    new_modifier.use_vertex_groups = modifier.use_vertex_groups
                    new_modifier.use_bone_envelopes = modifier.use_bone_envelopes
                    break

        # 6. 切换到姿态模式设置A-Pose
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        pose_bones = obj.pose.bones

        # 7. 仅清除手臂链的既有姿态，保留面部等其它骨骼的姿态
        bpy.ops.pose.select_all(action='DESELECT')
        for arm_bone_name in arm_bones.values():
            if arm_bone_name and arm_bone_name in pose_bones:
                pose_bones[arm_bone_name].select = True
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')
        context.view_layer.update()

        # 8. 为骨骼设置A-Pose旋转
        edit_bones = obj.data.bones
        converted_bones = []

        # 上臂目标仰角（向下为负）
        upper_arm_target = 36

        def _elevation(vec):
            """方向向量相对水平面的仰角（度），向上为正"""
            return math.degrees(math.atan2(vec.z, math.hypot(vec.x, vec.y)))

        def _rotate_bone_to_target(bone_name, bone_type, target_angle):
            """按世界方向把上臂旋转到目标仰角（绕肩关节，与骨骼roll无关）"""
            bone = pose_bones[bone_name]
            bone.rotation_mode = 'XYZ'
            mw = obj.matrix_world.copy()
            head_w = mw @ bone.head
            tail_w = mw @ bone.tail
            current_dir = (tail_w - head_w).normalized()
            elevation_before = _elevation(current_dir)

            # 用当前朝向判断左右，避免骨骼命名与实际镜像不一致时转错方向
            if abs(current_dir.x) > 1e-4:
                side = 1.0 if current_dir.x > 0 else -1.0
            else:
                side = 1.0 if "left" in bone_type else -1.0

            rad = math.radians(target_angle)
            target_dir = Vector((side * math.cos(rad), 0.0, -math.sin(rad)))
            quat = current_dir.rotation_difference(target_dir)

            # 绕肩关节（骨头）在世界空间旋转，再换算回姿态空间
            pivot = (Matrix.Translation(head_w) @ quat.to_matrix().to_4x4()
                     @ Matrix.Translation(-head_w))
            bone.matrix = mw.inverted() @ pivot @ mw @ bone.matrix
            context.view_layer.update()

            new_head_w = mw @ bone.head
            new_tail_w = mw @ bone.tail
            elevation_after = _elevation((new_tail_w - new_head_w).normalized())
            print(f"[A-Pose] {bone_name}: 仰角 {elevation_before:.2f}° -> "
                  f"目标 {-target_angle:.2f}° -> 实际 {elevation_after:.2f}°")
            converted_bones.append(bone_name)

        # 处理上臂
        for bone_type, bone_name in arm_bones.items():
            if "lower_arm" in bone_type:
                continue
            if bone_name and bone_name in pose_bones and bone_name in edit_bones:
                _rotate_bone_to_target(bone_name, bone_type, upper_arm_target)

        if not converted_bones:
            self.report({'WARNING'}, "没有找到匹配的骨骼可以转换")
            return {'CANCELLED'}

        # 9. 更新视图以确保姿态已应用
        context.view_layer.update()

        # 10. 应用第二个修改器（复制的修改器）来调整网格姿态
        try:
            for mesh_obj in meshes_with_armature:
                context.view_layer.objects.active = mesh_obj
                bpy.ops.object.mode_set(mode='OBJECT')
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj and "_copy" in modifier.name:
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
                        break
                if mesh_obj.name in shape_key_backups:
                    restore_shape_keys(mesh_obj, shape_key_backups[mesh_obj.name])
        except RuntimeError as e:
            self.report({'ERROR'}, f"应用修改器时出错：{str(e)}")
            return {'CANCELLED'}

        # 11. 切换回骨骼对象
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 12. 应用当前姿态为新的静置姿态
        bpy.ops.pose.armature_apply()

        # 13. 清理临时创建的网格
        for mesh_obj in meshes_with_armature:
            if mesh_obj.get("is_temp_mesh"):
                bpy.data.objects.remove(mesh_obj, do_unlink=True)

        self.report({'INFO'}, f"已完成A-Pose转换并应用为新的静置姿态")
        return {'FINISHED'}