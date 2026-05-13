import bpy


class OBJECT_OT_clear_all_bone_constraints(bpy.types.Operator):
    """清除所有骨骼的约束"""
    bl_idname = "object.clear_all_bone_constraints"
    bl_label = "清除所有骨骼约束"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 切换到姿态模式
        if obj.mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        # 统计被清除的约束数量
        total_removed = 0

        # 遍历所有骨骼并清除约束
        for p_bone in obj.pose.bones:
            constraints_count = len(p_bone.constraints)
            total_removed += constraints_count
            # 逆序删除所有约束
            for i in range(len(p_bone.constraints) - 1, -1, -1):
                constraint = p_bone.constraints[i]
                p_bone.constraints.remove(constraint)

        if total_removed > 0:
            self.report({'INFO'}, f"已清除 {total_removed} 个约束。")
        else:
            self.report({'INFO'}, "没有需要清除的约束。")

        return {'FINISHED'}


class OBJECT_OT_clear_all_bone_drivers(bpy.types.Operator):
    """清除所有骨骼的驱动器"""
    bl_idname = "object.clear_all_bone_drivers"
    bl_label = "清除所有骨骼驱动器"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 统计被清除的驱动器数量
        total_removed = 0

        # 清除骨骼上的所有驱动器
        # 遍历动作数据中的所有FCurves（可能包含驱动器）
        if obj.animation_data:
            # 收集所有属于骨骼属性的驱动器
            drivers_to_remove = []
            for driver in obj.animation_data.drivers:
                # 检查是否是骨骼属性的驱动器
                if driver.data_path.startswith('pose.bones['):
                    drivers_to_remove.append(driver)

            total_removed = len(drivers_to_remove)
            for driver in drivers_to_remove:
                obj.animation_data.drivers.remove(driver)

        # 清除数据块级别的驱动器（如果有的话）
        if obj.data.animation_data:
            drivers_to_remove = []
            for driver in obj.data.animation_data.drivers:
                drivers_to_remove.append(driver)

            total_removed += len(drivers_to_remove)
            for driver in drivers_to_remove:
                obj.data.animation_data.drivers.remove(driver)

        if total_removed > 0:
            self.report({'INFO'}, f"已清除 {total_removed} 个驱动器。")
        else:
            self.report({'INFO'}, "没有需要清除的驱动器。")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_clear_all_bone_constraints)
    bpy.utils.register_class(OBJECT_OT_clear_all_bone_drivers)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_clear_all_bone_constraints)
    bpy.utils.unregister_class(OBJECT_OT_clear_all_bone_drivers)


if __name__ == "__main__":
    register()