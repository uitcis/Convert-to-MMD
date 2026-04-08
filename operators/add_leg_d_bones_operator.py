import bpy
import math
from mathutils import Vector


class OBJECT_OT_add_leg_d_bones(bpy.types.Operator):
    """添加MMD腿部D骨骼"""
    bl_idname = "object.add_leg_d_bones"
    bl_label = "添加腿部D骨骼"
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        # 切换到编辑模式
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature.data.edit_bones
        
        # 检查是否已经存在D骨骼
        existing_d_bones = []
        for bone in edit_bones:
            if bone.name.endswith('D') and ('足' in bone.name or 'ひざ' in bone.name or '足首' in bone.name):
                existing_d_bones.append(bone.name)
        
        if existing_d_bones:
            self.report({'INFO'}, f"已经存在D骨骼: {', '.join(existing_d_bones)}，跳过操作")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}
        
        # 定义腿部骨骼映射 (原骨骼名, D骨骼名, 新骨骼名, D骨骼父级, shadow父级)
        # D骨骼父级为None表示保持原父级，为字符串表示指定父级骨骼名
        leg_bones_config = [
            # 右侧
            ("右足", "右足D", "右足", "下半身", "下半身"),  # 足D的父级是下半身，shadow的父级也是下半身
            ("右ひざ", "右ひざD", "右ひざ", "右足D", "右足"),  # ひざD的父级是足D，shadow的父级是原骨骼的父级
            ("右足首", "右足首D", "右足首", "右ひざD", "右ひざ"),  # 足首D的父级是ひざD，shadow的父级是原骨骼的父级
            ("右足先EX", "右足先EX", None, "右足首D", None),  # 足先EX的父级是足首D（如果存在）
            # 左侧
            ("左足", "左足D", "左足", "下半身", "下半身"),
            ("左ひざ", "左ひざD", "左ひざ", "左足D", "左足"),
            ("左足首", "左足首D", "左足首", "左ひざD", "左ひざ"),
            ("左足先EX", "左足先EX", None, "左足首D", None),
        ]
        
        bones_added = 0
        
        for original_name, d_name, new_name, d_parent_name, shadow_parent_name in leg_bones_config:
            original_bone = edit_bones.get(original_name)
            if not original_bone:
                continue
            
            # 保存原骨骼的位置信息
            head_pos = original_bone.head.copy()
            tail_pos = original_bone.tail.copy()
            
            # 保存原骨骼的父级（在重命名前保存）
            original_parent = original_bone.parent
            
            # 获取D骨骼的父级骨骼
            d_parent_bone = None
            if d_parent_name:
                d_parent_bone = edit_bones.get(d_parent_name)
            
            # 将原骨骼重命名为D骨骼
            original_bone.name = d_name
            
            # 调整D骨骼的尾端到头部上方（保持头部位置，向上延伸）
            up_vector = Vector((0, 0, 0.1))  # 向上延伸0.1个单位
            original_bone.tail = head_pos + up_vector
            
            # 设置D骨骼的父级
            if d_parent_bone:
                original_bone.parent = d_parent_bone
                original_bone.use_connect = False  # D骨骼不连接，保持独立控制
            
            # 创建dummy骨骼
            dummy_bone_name = f"_dummy_{d_name}"
            dummy_bone = edit_bones.new(dummy_bone_name)
            dummy_bone.head = head_pos
            dummy_bone.tail = head_pos + Vector((0, 0, 0.08))  # 向上延伸0.08个单位
            

            
            # 创建shadow骨骼
            shadow_bone_name = f"_shadow_{d_name}"
            shadow_bone = edit_bones.new(shadow_bone_name)
            shadow_bone.head = head_pos
            shadow_bone.tail = head_pos + Vector((0, 0, 0.08))  # 向上延伸0.08个单位
            
            # 设置shadow骨骼的父级
            if shadow_parent_name:
                shadow_parent = edit_bones.get(shadow_parent_name)
                if shadow_parent:
                    shadow_bone.parent = shadow_parent
            else:
                shadow_bone.parent = original_parent
            shadow_bone.use_connect = False
            
            # 如果new_name为None，表示不需要创建新骨骼（如足先EX）
            if new_name is None:
                bones_added += 1
                continue
            
            # 创建新的骨骼（与原来位置相同）
            new_bone = edit_bones.new(new_name)
            new_bone.head = head_pos
            new_bone.tail = tail_pos
            new_bone.parent = original_parent  # 新骨骼的父级保持与原骨骼重命名前一致
            new_bone.use_connect = False

            # 设置dummy骨骼的父级（与原骨骼相同）
            dummy_bone.parent = new_bone
            dummy_bone.use_connect = False
            
            # 切换到物体模式以添加约束
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 获取D骨骼和新骨骼的骨骼对象
            d_bone = armature.pose.bones[d_name]
            new_pose_bone = armature.pose.bones[new_name]
            
            # 复制D骨骼上的所有约束到新骨骼（包括IK约束）
            for constraint in list(d_bone.constraints):
                # 为新骨骼创建相同类型的约束
                new_constraint = new_pose_bone.constraints.new(constraint.type)
                
                # 复制约束的属性
                for attr in dir(constraint):
                    if not attr.startswith('_') and attr != 'type' and attr != 'bl_rna' and attr != 'rna_type':
                        try:
                            value = getattr(constraint, attr)
                            setattr(new_constraint, attr, value)
                        except:
                            pass
            
            # 清除D骨骼上的现有约束
            for constraint in list(d_bone.constraints):
                d_bone.constraints.remove(constraint)
            
            # 锁定腿部D骨骼的移动
            d_bone.lock_location[0] = True
            d_bone.lock_location[1] = True
            d_bone.lock_location[2] = True
            # 为D骨骼添加TRANSFORM约束
            transform_constraint = d_bone.constraints.new('TRANSFORM')
            transform_constraint.name = "mmd_additional_rotation"
            transform_constraint.target = armature
            transform_constraint.subtarget = f"_shadow_{d_name}"
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
            transform_constraint.to_min_x_rot = math.radians(-180.0)
            transform_constraint.to_min_y_rot = math.radians(-180.0)
            transform_constraint.to_min_z_rot = math.radians(-180.0)
            transform_constraint.to_max_x_rot = math.radians(180.0)
            transform_constraint.to_max_y_rot = math.radians(180.0)
            transform_constraint.to_max_z_rot = math.radians(180.0)
            
            # 为shadow骨骼添加COPY_TRANSFORMS约束
            shadow_bone_name = f"_shadow_{d_name}"
            if shadow_bone_name in armature.pose.bones:
                shadow_bone = armature.pose.bones[shadow_bone_name]
                # 清除现有约束
                for constraint in list(shadow_bone.constraints):
                    shadow_bone.constraints.remove(constraint)
                # 添加COPY_TRANSFORMS约束
                shadow_constraint = shadow_bone.constraints.new('COPY_TRANSFORMS')
                shadow_constraint.name = "mmd_tools_at_dummy"
                shadow_constraint.target = armature
                shadow_constraint.subtarget = f"_dummy_{d_name}"
                shadow_constraint.influence = 1.0
                # 设置为姿态空间
                shadow_constraint.owner_space = 'POSE'
                shadow_constraint.target_space = 'POSE'
                # 移除目标剪切
                shadow_constraint.remove_target_shear = False
            
            # 切换回编辑模式继续操作
            bpy.ops.object.mode_set(mode='EDIT')
            
            # 重新获取编辑模式下的骨骼
            original_bone = edit_bones[d_name]
            new_bone = edit_bones[new_name]
            
            # 更新子骨骼的父级（连接到新骨骼而不是D骨骼）
            for child in list(original_bone.children):
                if child != new_bone and not child.name.endswith('D'):
                    child.parent = new_bone
            
            bones_added += 1
        
        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 对创建的骨骼进行分组
        bpy.ops.object.create_bone_group()
        
        self.report({'INFO'}, f"已添加 {bones_added} 个腿部D骨骼")
        return {'FINISHED'}


# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_add_leg_d_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_leg_d_bones)


if __name__ == "__main__":
    register()
