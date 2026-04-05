import bpy
import math
from mathutils import Matrix
from ..bone_utils import apply_armature_transforms
# 新增的T-Pose到A-Pose转换操作符
class OBJECT_OT_convert_to_apose(bpy.types.Operator):
    """将骨架转换为 A-Pose 并应用为新的静置姿态"""
    bl_idname = "object.convert_to_apose" 
    bl_label = "Convert to A-Pose"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
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

        #1. 检查是否有设置骨骼
        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置要转换的骨骼")
            return {'CANCELLED'}
        # 2. 切换到编辑模式，将upper_arm的尾部连接到lowerarm的头部
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones
        
        # 获取骨骼位置
        left_upper_arm = edit_bones[arm_bones["left_upper_arm"]]
        left_lower_arm = edit_bones[arm_bones["left_lower_arm"]]
        right_upper_arm = edit_bones[arm_bones["right_upper_arm"]]
        right_lower_arm = edit_bones[arm_bones["right_lower_arm"]]
        
        # 调整尾部位置
        left_upper_arm.tail = left_lower_arm.head
        right_upper_arm.tail = right_lower_arm.head



        # 4. 找到所有使用这个骨骼的网格对象，并检查形态键
        meshes_with_armature = []
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type == 'MESH':
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj:
                        # 检查是否有形态键
                        if not mesh_obj.data.shape_keys:
                            meshes_with_armature.append(mesh_obj)
                        break

        # 检查是否找到可用的网格
        if not meshes_with_armature:
            # 创建临时测试网格
            try:
                bpy.ops.mesh.primitive_cube_add(size=0.5)
                temp_mesh = context.active_object
                temp_mesh.name = "CTMMD_TEMP_MESH"
                
                # 添加骨架修改器
                modifier = temp_mesh.modifiers.new(name="Armature", type='ARMATURE')
                modifier.object = obj
                
                # 添加到可用网格列表
                meshes_with_armature.append(temp_mesh)
                
                # 标记为临时网格
                temp_mesh["is_temp_mesh"] = True
                
            except Exception as e:
                self.report({'ERROR'}, f"创建临时网格失败：{str(e)}")
                return {'CANCELLED'}

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

        # 7. 清除所有现有姿态
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')

        # 8. 为骨骼设置A-Pose旋转
        pose_bones = obj.pose.bones
        edit_bones = obj.data.bones
        converted_bones = []
        target_angle = 36  # 目标角度36度

        for bone_type, bone_name in arm_bones.items():
            if bone_name and bone_name in pose_bones and bone_name in edit_bones:
                bone = pose_bones[bone_name]
                edit_bone = edit_bones[bone_name]
                bone.rotation_mode = 'XYZ'
                
                # 获取骨骼的头部和尾部坐标
                head = edit_bone.head_local
                tail = edit_bone.tail_local
                
                # 计算方向向量（从尾指向头）
                vec = head - tail
                
                # 使用四元数转换得到欧拉角
                quat = vec.to_track_quat('Z', 'Y')
                euler = quat.to_euler('XYZ')
                
                # 获取当前X轴旋转角度
                current_angle = math.degrees(euler.x)
                
                # 计算角度差（左右两侧使用相同的计算逻辑）
                angle_diff = current_angle - target_angle
                
                # 重置旋转，确保从默认状态开始
                bone.rotation_euler = (0, 0, 0)
                
                # 绕全局空间Y轴旋转
                if bone_type == "left_upper_arm":
                    # 左上肢：绕全局Y轴旋转angle_diff角度
                    # 计算全局旋转矩阵
                    global_rotation = Matrix.Rotation(math.radians(angle_diff), 4, 'Y')
                    # 应用全局旋转
                    bone.matrix = global_rotation @ bone.matrix
                elif bone_type == "right_upper_arm":
                    # 右上肢：绕全局Y轴旋转-angle_diff角度
                    # 计算全局旋转矩阵
                    global_rotation = Matrix.Rotation(math.radians(-angle_diff), 4, 'Y')
                    # 应用全局旋转
                    bone.matrix = global_rotation @ bone.matrix
                
                converted_bones.append(bone_name)

        if not converted_bones:
            self.report({'WARNING'}, "没有找到匹配的骨骼可以转换")
            return {'CANCELLED'}

        # 9. 更新视图以确保姿态已应用
        context.view_layer.update()

        # 10. 应用第二个修改器（复制的修改器）来调整网格姿态
        try:
            for mesh_obj in meshes_with_armature:
                context.view_layer.objects.active = mesh_obj
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj and "_copy" in modifier.name:
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
                        break
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