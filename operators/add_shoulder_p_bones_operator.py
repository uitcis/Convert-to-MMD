import bpy
import math
from mathutils import Vector
from .. import bone_utils
from ..bone_utils import create_or_update_bone, context_mode_to_mode_set


class OBJECT_OT_add_shoulder_p_bones(bpy.types.Operator):
    """添加MMD肩P骨骼"""
    bl_idname = "object.add_shoulder_p_bones"
    bl_label = "添加肩P骨骼"
    
    def execute(self, context):
        armature = bone_utils.resolve_armature(context)
        if not armature:
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        original_mode = context.mode
        # mode_set 只接受 OBJECT/EDIT/POSE，而 context.mode 返回 'EDIT_ARMATURE' 等值
        restore_mode = context_mode_to_mode_set(original_mode)
        # 切换到编辑模式
        if original_mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature.data.edit_bones
        
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
            
            # 创建/复用肩P骨骼（已存在则不重复创建，仅调整位置与关系）
            up_vector = Vector((0, 0, 0.08))  # 向上延伸0.08个单位
            p_bone = create_or_update_bone(
                edit_bones, p_name, head_pos, head_pos + up_vector,
                use_connect=False, parent_name=None,
            )
            # 设置肩P骨骼的父级（不连接，保持独立控制）
            if p_parent_bone:
                p_bone.parent = p_parent_bone
            else:
                p_bone.parent = original_parent
            p_bone.use_connect = False
            
            # 创建/复用肩C骨骼
            c_bone = create_or_update_bone(
                edit_bones, c_name, tail_pos, tail_pos + up_vector,
                use_connect=False, parent_name=None,
            )
            # 获取肩C骨骼的父级骨骼并设置（不连接，保持独立控制）
            c_parent_bone = edit_bones.get(c_parent_name) if c_parent_name else original_bone
            if c_parent_bone:
                c_bone.parent = c_parent_bone
            else:
                c_bone.parent = original_bone
            c_bone.use_connect = False
            
            # 创建/复用dummy骨骼
            dummy_bone_name = f"_dummy_{c_name}"
            dummy_bone = create_or_update_bone(
                edit_bones, dummy_bone_name, head_pos, head_pos + up_vector,
                use_connect=False, parent_name=None,
            )
            # 设置dummy骨骼的父级
            dummy_parent_bone = edit_bones.get(dummy_parent_name) if dummy_parent_name else p_bone
            if dummy_parent_bone:
                dummy_bone.parent = dummy_parent_bone
            else:
                dummy_bone.parent = p_bone
            dummy_bone.use_connect = False
            
            # 创建/复用shadow骨骼
            shadow_bone_name = f"_shadow_{c_name}"
            shadow_bone = create_or_update_bone(
                edit_bones, shadow_bone_name, head_pos, head_pos + up_vector,
                use_connect=False, parent_name=None,
            )
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
        
        # 关键修复：退出编辑模式使pose数据与新骨骼同步。
        # 编辑模式下pose.bones是进入编辑模式前的快照，不含新建骨骼，
        # 直接访问会触发KeyError（如 '右肩C' not found）。
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # 添加约束（必须在非编辑模式下进行，此时pose.bones已包含新建骨骼）
        if created_bones:
            for c_name, shadow_bone_name in created_bones:
                # 获取肩C骨骼的骨骼对象
                c_pose_bone = armature.pose.bones.get(c_name)
                if c_pose_bone is None:
                    print(f"警告: 未在姿态骨骼中找到 {c_name}，跳过约束设置")
                    continue
                
                # 锁定肩C骨骼的移动
                c_pose_bone.lock_location[0] = True
                c_pose_bone.lock_location[1] = True
                c_pose_bone.lock_location[2] = True
                
                # 清除现有约束，避免重复运行累加
                for constraint in list(c_pose_bone.constraints):
                    c_pose_bone.constraints.remove(constraint)
                
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
        # 对创建的骨骼进行分组（切到物体模式，兼容 Blender 3.x 的 pose.group_add 分支）
        # 注意：上方已切换到物体模式以同步pose数据，此处无需再次切换
        bpy.ops.object.create_bone_group()

        # 恢复进入时的模式（context.mode 的值需转换为 mode_set 接受的枚举）
        if context.mode != original_mode:
            bpy.ops.object.mode_set(mode=restore_mode)
        
        self.report({'INFO'}, f"已处理 {bones_added} 组肩P骨骼（已存在的骨骼自动复用，仅调整关系）")
        return {'FINISHED'}


# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_add_shoulder_p_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_shoulder_p_bones)


if __name__ == "__main__":
    register()