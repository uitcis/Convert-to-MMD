"""小臂对齐工具 —— 独立的小臂调整逻辑，方便单独调试和调整参数"""

import bpy
import math
from mathutils import Quaternion

from .. import bone_utils


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

    # 计算期间使用四元数，结束后恢复用户原本的旋转模式
    old_mode = lower_pbone.rotation_mode
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
    # 直接把世界空间的旋转作用到 pose 矩阵上（绕骨骼头部旋转），
    # 由 Blender 反解局部旋转。这样直链和弯臂静置链都能真正对齐。
    head = lower_pbone.matrix.translation.copy()
    rotated_matrix = world_correction.to_matrix().to_4x4() @ lower_pbone.matrix
    rotated_matrix.translation = head
    lower_pbone.matrix = rotated_matrix
    bpy.context.view_layer.update()

    # 恢复原有旋转模式（Blender 会自动把四元数结果转换为对应模式）
    if old_mode != 'QUATERNION':
        lower_pbone.rotation_mode = old_mode

    return True


# ============================================================
# 操作符
# ============================================================

class OBJECT_OT_align_forearm_from_selection(bpy.types.Operator):
    """将选中的骨骼与各自父骨骼方向对齐"""
    bl_idname = "object.align_forearm_from_selection"
    bl_label = "对齐骨骼"
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
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'WARNING'}, "请选中一个骨架对象")
            return {'CANCELLED'}

        if context.mode != 'POSE':
            self.report({'WARNING'}, "请在姿态模式下使用此功能")
            return {'CANCELLED'}

        selected_bones = [b for b in context.selected_pose_bones]
        if not selected_bones:
            self.report({'WARNING'}, "请先选中骨骼")
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
    bpy.utils.register_class(OBJECT_OT_align_forearm_from_selection)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_align_forearm_from_selection)


if __name__ == "__main__":
    register()
