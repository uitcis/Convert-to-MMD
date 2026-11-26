import bpy
from mathutils import Euler

from .. import bone_utils


# ============================================================
# 通用工具操作符集合
# 放置不依赖特定业务流程的通用辅助工具
# ============================================================


def _convert_euler_curves_to_quaternion(action, bone_name, rotation_mode):
    """把某根骨骼的 Euler 旋转曲线改写为四元数曲线。

    返回写入的关键帧数；0 表示没有可转换的曲线；
    -1 表示已存在四元数曲线（为安全起见跳过）。
    """
    path_prefix = f'pose.bones["{bone_name}"].'
    euler_curves = {}
    for fcurve in list(action.fcurves):
        if (fcurve.data_path == path_prefix + "rotation_euler"
                and fcurve.array_index in (0, 1, 2)):
            euler_curves[fcurve.array_index] = fcurve
    if len(euler_curves) < 3:
        return 0

    quat_path = path_prefix + "rotation_quaternion"
    if any(fcurve.data_path == quat_path for fcurve in action.fcurves):
        return -1

    times = sorted({kp.co.x for fc in euler_curves.values()
                    for kp in fc.keyframe_points})
    if not times:
        return 0

    quats = []
    for t in times:
        euler = Euler((
            euler_curves[0].evaluate(t),
            euler_curves[1].evaluate(t),
            euler_curves[2].evaluate(t),
        ), rotation_mode)
        quat = euler.to_quaternion()
        # 保持四元数符号连续，避免插值走远路
        if quats and quat.dot(quats[-1]) < 0:
            quat.negate()
        quats.append(quat)

    first_curve = next(iter(euler_curves.values()))
    interpolation = (first_curve.keyframe_points[0].interpolation
                     if first_curve.keyframe_points else 'BEZIER')

    for index in (0, 1, 2, 3):
        fcurve = action.fcurves.new(quat_path, index=index, action_group=bone_name)
        fcurve.keyframe_points.add(len(times))
        for key_point, time, quat in zip(fcurve.keyframe_points, times, quats):
            key_point.co = (time, quat[index])
            key_point.interpolation = interpolation
        fcurve.update()

    for fcurve in euler_curves.values():
        action.fcurves.remove(fcurve)

    return len(times)


class OBJECT_OT_convert_bones_rotation_to_quaternion(bpy.types.Operator):
    """将所有骨骼的旋转模式转换为四元数 (Quaternion)"""
    bl_idname = "object.convert_bones_rotation_to_quaternion"
    bl_label = "转换为四元数旋转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)

        if not obj:
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # rotation_mode 是姿态数据属性，任意模式下均可修改（无需切换到姿态模式）
        converted_count = 0
        skipped_count = 0
        converted_curves = 0
        skipped_actions = []

        action = None
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action

        for p_bone in obj.pose.bones:
            old_mode = p_bone.rotation_mode
            if old_mode == 'QUATERNION':
                skipped_count += 1
                continue

            if action and old_mode in ('XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'):
                result = _convert_euler_curves_to_quaternion(
                    action, p_bone.name, old_mode)
                if result > 0:
                    converted_curves += result
                elif result < 0:
                    skipped_actions.append(p_bone.name)

            p_bone.rotation_mode = 'QUATERNION'
            converted_count += 1

        if converted_count > 0:
            message = f"已将 {converted_count} 个骨骼的旋转模式转换为四元数"
            if skipped_count > 0:
                message += f"（{skipped_count} 个骨骼已是四元数）"
            if converted_curves > 0:
                message += f"，并转换了 {converted_curves} 个动画关键帧"
            if skipped_actions:
                message += (f"；{len(skipped_actions)} 个骨骼已存在四元数曲线，"
                            f"未改写其 Euler 曲线: {', '.join(skipped_actions[:5])}")
            self.report({'WARNING'} if skipped_actions else {'INFO'}, message)
        else:
            self.report({'INFO'}, "所有骨骼已是四元数旋转模式，无需转换。")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_convert_bones_rotation_to_quaternion)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_convert_bones_rotation_to_quaternion)


if __name__ == "__main__":
    register()
