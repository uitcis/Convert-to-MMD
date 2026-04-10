import bpy
import math
from mathutils import Vector


class OBJECT_OT_add_shoulder_p_bones(bpy.types.Operator):
    """添加MMD肩P骨骼"""
    bl_idname = "object.add_shoulder_p_bones"
    bl_label = "添加肩P骨骼"
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        # 切换到编辑模式
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature.data.edit_bones
        
        # 检查是否已经存在肩P骨骼
        existing_shoulder_p_bones = []
        for bone in edit_bones:
            if '肩P' in bone.name:
                existing_shoulder_p_bones.append(bone.name)
        
        if existing_shoulder_p_bones:
            self.report({'INFO'}, f"已经存在肩P骨骼: {', '.join(existing_shoulder_p_bones)}，跳过操作")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}
        
        # 定义肩部骨骼映射 (现有肩骨骼名, 肩P骨骼名, 肩C骨骼名, 肩P父级, 肩C父级, dummy父级, shadow父级)
        shoulder_bones_config = [
            # 右侧
            ("右肩", "右肩P", "右肩C", "上半身2", "右肩", "右肩P", "上半身2"),
            # 左侧
            ("左肩", "左肩P", "左肩C", "上半身2", "左肩", "左肩P", "上半身2"),
        ]
        
        bones_added = 0
        
        # 先创建所有骨骼
        created_bones = []
        for original_name, p_name, c_name, p_parent_name, c_parent_name, dummy_parent_name, shadow_parent_name in shoulder_bones_config:
            original_bone = edit_bones.get(original_name)
            if not original_bone:
                continue
            
            # 保存标准骨骼的位置信息
            head_pos = original_bone.head.copy()
            tail_pos = original_bone.tail.copy()
            
            # 保存标准骨骼的父级
            original_parent = original_bone.parent
            
            # 获取肩P骨骼的父级骨骼
            p_parent_bone = edit_bones.get(p_parent_name) if p_parent_name else original_parent
            
            # 创建肩P骨骼
            p_bone = edit_bones.new(p_name)
            p_bone.head = head_pos
            # 调整肩P骨骼的尾端到头部上方（保持头部位置，向上延伸）
            up_vector = Vector((0, 0, 0.08))  # 向上延伸0.08个单位
            p_bone.tail = head_pos + up_vector
            
            # 设置肩P骨骼的父级
            if p_parent_bone:
                p_bone.parent = p_parent_bone
                p_bone.use_connect = False  # 肩P骨骼不连接，保持独立控制
            else:
                p_bone.parent = original_parent
                p_bone.use_connect = False
            
            # 创建肩C骨骼
            c_bone = edit_bones.new(c_name)
            c_bone.head = tail_pos
            # 调整肩C骨骼的尾端到头部上方（保持头部位置，向上延伸）
            c_bone.tail = tail_pos + up_vector
            
            # 获取肩C骨骼的父级骨骼
            c_parent_bone = edit_bones.get(c_parent_name) if c_parent_name else original_bone
            
            # 设置肩C骨骼的父级
            if c_parent_bone:
                c_bone.parent = c_parent_bone
                c_bone.use_connect = False  # 肩C骨骼不连接，保持独立控制
            else:
                c_bone.parent = original_bone
                c_bone.use_connect = False
            
            # 创建dummy骨骼
            dummy_bone_name = f"_dummy_{c_name}"
            dummy_bone = edit_bones.new(dummy_bone_name)
            dummy_bone.head = head_pos
            dummy_bone.tail = head_pos + up_vector  # 向上延伸0.08个单位
            
            # 设置dummy骨骼的父级
            dummy_parent_bone = edit_bones.get(dummy_parent_name) if dummy_parent_name else p_bone
            if dummy_parent_bone:
                dummy_bone.parent = dummy_parent_bone
            else:
                dummy_bone.parent = p_bone
            dummy_bone.use_connect = False
            
            # 创建shadow骨骼
            shadow_bone_name = f"_shadow_{c_name}"
            shadow_bone = edit_bones.new(shadow_bone_name)
            shadow_bone.head = head_pos
            shadow_bone.tail = head_pos + up_vector  # 向上延伸0.08个单位
            
            # 设置shadow骨骼的父级
            shadow_parent_bone = edit_bones.get(shadow_parent_name) if shadow_parent_name else p_parent_bone
            if shadow_parent_bone:
                shadow_bone.parent = shadow_parent_bone
            else:
                shadow_bone.parent = p_parent_bone
            shadow_bone.use_connect = False
            
            # 更新标准骨骼的父级，连接到肩P骨骼，但断开连接
            original_bone.parent = p_bone
            original_bone.use_connect = False
            
            # 查找腕骨骼并将其父级设置为肩C
            wrist_bone_name = "右腕" if original_name == "右肩" else "左腕"
            if wrist_bone_name in edit_bones:
                wrist_bone = edit_bones[wrist_bone_name]
                # 保存腕骨骼的原始头部和尾部位置
                original_wrist_head = wrist_bone.head.copy()
                original_wrist_tail = wrist_bone.tail.copy()
                # 修改父级
                wrist_bone.parent = c_bone
                wrist_bone.use_connect = False
                # 恢复腕骨骼的原始位置
                wrist_bone.head = original_wrist_head
                wrist_bone.tail = original_wrist_tail
            
            # 记录创建的骨骼信息
            created_bones.append((c_name, shadow_bone_name))
            
            bones_added += 1
        
        # 一次性切换到姿态模式添加约束
        if created_bones:
            bpy.ops.object.mode_set(mode='POSE')
            
            for c_name, shadow_bone_name in created_bones:
                # 获取肩C骨骼的骨骼对象
                c_pose_bone = armature.pose.bones[c_name]
                
                # 锁定肩C骨骼的移动
                c_pose_bone.lock_location[0] = True
                c_pose_bone.lock_location[1] = True
                c_pose_bone.lock_location[2] = True
                
                # 为肩C骨骼添加TRANSFORM约束
                transform_constraint = c_pose_bone.constraints.new('TRANSFORM')
                transform_constraint.name = "mmd_additional_rotation"
                transform_constraint.target = armature
                transform_constraint.subtarget = shadow_bone_name
                transform_constraint.influence = 1.0
                transform_constraint.use_motion_extrapolate = True
                # 设置所有者空间为局部空间
                transform_constraint.owner_space = 'LOCAL'
                # 设置目标空间为局部空间
                transform_constraint.target_space = 'LOCAL'
                # 设置从旋转映射到旋转
                transform_constraint.map_from = 'ROTATION'
                transform_constraint.map_to = 'ROTATION'
                # 设置映射自的模式为XYZ欧拉
                transform_constraint.from_rotation_mode = 'XYZ'
                # 设置映射模式为XYZ欧拉
                transform_constraint.to_euler_order = 'XYZ'
                # 设置混合选项为初始后
                transform_constraint.mix_mode_rot = 'AFTER'
                
                # 设置旋转范围（将角度转换为弧度）
                transform_constraint.from_min_x_rot = math.radians(-180.0)
                transform_constraint.from_min_y_rot = math.radians(-180.0)
                transform_constraint.from_min_z_rot = math.radians(-180.0)
                transform_constraint.from_max_x_rot = math.radians(180.0)
                transform_constraint.from_max_y_rot = math.radians(180.0)
                transform_constraint.from_max_z_rot = math.radians(180.0)
                transform_constraint.to_min_x_rot = math.radians(180.0)
                transform_constraint.to_min_y_rot = math.radians(180.0)
                transform_constraint.to_min_z_rot = math.radians(180.0)
                transform_constraint.to_max_x_rot = math.radians(-180.0)
                transform_constraint.to_max_y_rot = math.radians(-180.0)
                transform_constraint.to_max_z_rot = math.radians(-180.0)
                
                # 为shadow骨骼添加COPY_TRANSFORMS约束
                if shadow_bone_name in armature.pose.bones:
                    shadow_bone = armature.pose.bones[shadow_bone_name]
                    # 清除现有约束
                    for constraint in list(shadow_bone.constraints):
                        shadow_bone.constraints.remove(constraint)
                    # 添加COPY_TRANSFORMS约束
                    shadow_constraint = shadow_bone.constraints.new('COPY_TRANSFORMS')
                    shadow_constraint.name = "mmd_tools_at_dummy"
                    shadow_constraint.target = armature
                    shadow_constraint.subtarget = f"_dummy_{c_name}"
                    shadow_constraint.influence = 1.0
                    # 设置为姿态空间
                    shadow_constraint.owner_space = 'POSE'
                    shadow_constraint.target_space = 'POSE'
                    # 移除目标剪切
                    shadow_constraint.remove_target_shear = False
        # 对创建的骨骼进行分组
        bpy.ops.object.create_bone_group()
        
        self.report({'INFO'}, f"已添加 {bones_added} 组肩P骨骼")
        return {'FINISHED'}


# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_add_shoulder_p_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_shoulder_p_bones)


if __name__ == "__main__":
    register()