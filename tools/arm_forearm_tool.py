"""小臂对齐工具 —— 独立的小臂调整逻辑，方便单独调试和调整参数"""

import bpy
import math
from mathutils import Quaternion


def get_arm_bone_names_from_scene(scene):
    """从场景属性中获取手臂骨骼名称"""
    return {
        "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
        "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
        "left_lower_arm": getattr(scene, "left_lower_arm_bone", ""),
        "right_lower_arm": getattr(scene, "right_lower_arm_bone", ""),
    }


def align_forearm_to_upper_arm(obj, upper_name, lower_name, elbow_angle=0.0):
    """
    将小臂方向对齐到上臂方向，实现肘关节伸直（或指定角度）。

    参数:
        obj: 骨架对象（必须在 POSE 模式下）
        upper_name: 上臂骨骼名称
        lower_name: 小臂骨骼名称
        elbow_angle: 肘关节弯曲角度（度数），0=完全伸直，正数=向内弯曲

    返回:
        成功时返回 True，失败时返回错误信息字符串
    """
    if not obj or obj.type != 'ARMATURE':
        return "不是有效的骨架对象"

    pose_bones = obj.pose.bones

    if upper_name not in pose_bones:
        return f"上臂骨骼 '{upper_name}' 不存在"
    if lower_name not in pose_bones:
        return f"小臂骨骼 '{lower_name}' 不存在"

    upper_pbone = pose_bones[upper_name]
    lower_pbone = pose_bones[lower_name]

    # 保存并设置旋转模式
    old_mode = lower_pbone.rotation_mode
    old_quat = lower_pbone.rotation_quaternion.copy() if old_mode == 'QUATERNION' else None
    lower_pbone.rotation_mode = 'QUATERNION'

    # 上臂当前世界方向
    upper_dir = (upper_pbone.tail - upper_pbone.head).normalized()

    # 小臂当前世界方向（归零本地旋转后只看父骨骼的影响）
    lower_pbone.rotation_quaternion = (1, 0, 0, 0)
    bpy.context.view_layer.update()
    lower_dir = (lower_pbone.tail - lower_pbone.head).normalized()

    if elbow_angle == 0.0:
        # 完全伸直：小臂方向 = 上臂方向
        world_correction = lower_dir.rotation_difference(upper_dir)
    else:
        # 中间状态：在 zero_dir 和 upper_dir 之间插值
        angle_rad = math.radians(elbow_angle)
        # 计算旋转轴（垂直于上臂方向和归零小臂方向的平面）
        rotation_axis = lower_dir.cross(upper_dir)
        if rotation_axis.length < 1e-6:
            # 方向平行或反平行，直接用上臂方向
            world_correction = lower_dir.rotation_difference(upper_dir)
        else:
            rotation_axis.normalize()
            # 从归零方向旋转 elbow_angle 度得到目标方向
            half_angle_q = Quaternion(rotation_axis, angle_rad * 0.5)
            target_dir = half_angle_q @ lower_dir
            target_dir.normalize()
            world_correction = lower_dir.rotation_difference(target_dir)

    # 转换为骨骼本地空间
    parent_rot = upper_pbone.matrix.to_quaternion()
    local_correction = parent_rot.inverted() @ world_correction

    lower_pbone.rotation_quaternion = local_correction

    return True


def align_all_forearms(obj, arm_bones, elbow_angle=0.0):
    """
    对齐所有小臂。

    参数:
        obj: 骨架对象（必须在 POSE 模式下）
        arm_bones: {left_upper_arm, right_upper_arm, left_lower_arm, right_lower_arm} 字典
        elbow_angle: 肘关节弯曲角度（度数）

    返回:
        (成功数, 失败信息列表)
    """
    results = {"left": None, "right": None}
    success_count = 0

    for prefix in ("left", "right"):
        lower_name = arm_bones.get(f"{prefix}_lower_arm")
        upper_name = arm_bones.get(f"{prefix}_upper_arm")
        if not lower_name or not upper_name:
            continue
        result = align_forearm_to_upper_arm(obj, upper_name, lower_name, elbow_angle)
        results[prefix] = result
        if result is True:
            success_count += 1

    errors = [f"{k}: {v}" for k, v in results.items() if v is not True and v is not None]
    return success_count, errors


# ============================================================
# 操作符
# ============================================================

class OBJECT_OT_align_forearm_straight(bpy.types.Operator):
    """将小臂与上臂对齐，使肘关节完全伸直（当前选中的骨架）"""
    bl_idname = "object.align_forearm_straight"
    bl_label = "伸直小臂"
    bl_options = {'REGISTER', 'UNDO'}

    elbow_angle: bpy.props.FloatProperty(
        name="肘关节角度",
        description="0°=完全伸直，正值=向内弯曲（度）",
        default=0.0,
        min=-90.0,
        max=90.0,
        step=1.0,
    )  # type: ignore[assignment]

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架对象")
            return {'CANCELLED'}

        # 获取骨骼名称
        arm_bones = get_arm_bone_names_from_scene(context.scene)

        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置手臂骨骼名称")
            return {'CANCELLED'}

        # 保存当前模式
        original_mode = context.mode
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        # 检查骨骼是否存在
        pose_bones = obj.pose.bones
        missing = [k for k, v in arm_bones.items() if v and v not in pose_bones]
        if missing:
            self.report({'ERROR'}, f"以下骨骼不存在：{', '.join(missing)}")
            if original_mode != 'POSE':
                bpy.ops.object.mode_set(mode=original_mode)
            return {'CANCELLED'}

        success_count, errors = align_all_forearms(obj, arm_bones, self.elbow_angle)

        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode=original_mode)

        if errors:
            self.report({'WARNING'}, f"已对齐 {success_count} 条小臂，失败：{'；'.join(errors)}")
        else:
            self.report({'INFO'}, f"已对齐 {success_count} 条小臂，肘关节角度={self.elbow_angle}°")
        return {'FINISHED'}


class OBJECT_OT_align_forearm_from_selection(bpy.types.Operator):
    """基于当前选中的小臂骨骼，将其与父级上臂对齐"""
    bl_idname = "object.align_forearm_from_selection"
    bl_label = "对齐选中骨骼的小臂"
    bl_options = {'REGISTER', 'UNDO'}

    elbow_angle: bpy.props.FloatProperty(
        name="肘关节角度",
        description="0°=完全伸直，正值=向内弯曲（度）",
        default=0.0,
        min=-90.0,
        max=90.0,
        step=1.0,
    )  # type: ignore[assignment]

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架对象")
            return {'CANCELLED'}

        if context.mode != 'POSE':
            self.report({'ERROR'}, "请在姿态模式下使用此功能")
            return {'CANCELLED'}

        selected_bones = [b for b in context.selected_pose_bones]
        if not selected_bones:
            self.report({'ERROR'}, "请先选中骨骼")
            return {'CANCELLED'}

        success_count = 0
        errors = []

        for pbone in selected_bones:
            if not pbone.parent:
                continue
            lower_name = pbone.name
            upper_name = pbone.parent.name
            result = align_forearm_to_upper_arm(obj, upper_name, lower_name, self.elbow_angle)
            if result is True:
                success_count += 1
            else:
                errors.append(f"{lower_name}: {result}")

        if errors:
            self.report({'WARNING'}, f"已对齐 {success_count} 根骨骼，失败：{'；'.join(errors)}")
        else:
            self.report({'INFO'}, f"已对齐 {success_count} 根骨骼，肘关节角度={self.elbow_angle}°")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_align_forearm_straight)
    bpy.utils.register_class(OBJECT_OT_align_forearm_from_selection)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_align_forearm_from_selection)
    bpy.utils.unregister_class(OBJECT_OT_align_forearm_straight)


if __name__ == "__main__":
    register()
