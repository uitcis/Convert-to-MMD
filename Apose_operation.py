import bpy
import math
import mathutils
import os
from mathutils import Vector, Matrix, Euler
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

        scene = context.scene
        
        # 获取骨骼名称
        arm_bones = {
            "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
            "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
        }

        # 检查是否有设置骨骼
        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置要转换的骨骼")
            return {'CANCELLED'}

        # 1. 确保在对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 2. 找到所有使用这个骨骼的网格对象，并检查形态键
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

        # 3. 为每个网格复制骨骼修改器，但保留原始修改器
        for mesh_obj in meshes_with_armature:
            for modifier in mesh_obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object == obj:
                    # 复制修改器
                    new_modifier = mesh_obj.modifiers.new(name=modifier.name + "_copy", type='ARMATURE')
                    new_modifier.object = modifier.object
                    new_modifier.use_vertex_groups = modifier.use_vertex_groups
                    new_modifier.use_bone_envelopes = modifier.use_bone_envelopes
                    break

        # 4. 切换到姿态模式设置A-Pose
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 5. 清除所有现有姿态
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')

        # 6. 为骨骼设置A-Pose旋转
        pose_bones = obj.pose.bones
        converted_bones = []

        for bone_type, bone_name in arm_bones.items():
            if bone_name and bone_name in pose_bones:
                bone = pose_bones[bone_name]
                bone.rotation_mode = 'XYZ'
                
                # 根据骨骼类型设置不同的旋转角度
                if bone_type == "left_upper_arm":
                    rotation_matrix = Matrix.Rotation(math.radians(37), 4, 'Y')
                elif bone_type == "right_upper_arm":
                    rotation_matrix = Matrix.Rotation(math.radians(-37), 4, 'Y')
                
                # 应用旋转矩阵
                bone.matrix = rotation_matrix @ bone.matrix
                
                converted_bones.append(bone_name)

        if not converted_bones:
            self.report({'WARNING'}, "没有找到匹配的骨骼可以转换")
            return {'CANCELLED'}

        # 7. 更新视图以确保姿态已应用
        context.view_layer.update()

        # 8. 应用第二个修改器（复制的修改器）来调整网格姿态
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

        # 9. 切换回骨骼对象
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 10. 应用当前姿态为新的静置姿态
        bpy.ops.pose.armature_apply()

        # 11. 清理临时创建的网格
        for mesh_obj in meshes_with_armature:
            if mesh_obj.get("is_temp_mesh"):
                bpy.data.objects.remove(mesh_obj, do_unlink=True)

        self.report({'INFO'}, f"已完成A-Pose转换并应用为新的静置姿态")
        return {'FINISHED'}