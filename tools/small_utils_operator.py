import bpy


class OBJECT_OT_convert_bones_rotation_to_quaternion(bpy.types.Operator):
    """将所有骨骼的旋转模式转换为四元数 (Quaternion)"""
    bl_idname = "object.convert_bones_rotation_to_quaternion"
    bl_label = "转换为四元数旋转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 记录原模式以便恢复
        original_mode = obj.mode

        # 切换到姿态模式
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        converted_count = 0
        skipped_count = 0

        for p_bone in obj.pose.bones:
            if p_bone.rotation_mode != 'QUATERNION':
                p_bone.rotation_mode = 'QUATERNION'
                converted_count += 1
            else:
                skipped_count += 1

        # 恢复原模式
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode=original_mode)

        if converted_count > 0:
            self.report(
                {'INFO'},
                f"已将 {converted_count} 个骨骼的旋转模式转换为四元数"
                + (f"（{skipped_count} 个骨骼已是四元数）" if skipped_count > 0 else "")
            )
        else:
            self.report({'INFO'}, "所有骨骼已是四元数旋转模式，无需转换。")

        return {'FINISHED'}


class OBJECT_OT_split_bones_to_individual_objects(bpy.types.Operator):
    """将骨架中的每个骨骼拆分为独立的空物体（仅保留骨骼变换信息）"""
    bl_idname = "object.split_bones_to_individual_objects"
    bl_label = "拆分骨骼为独立物体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 记录原模式
        original_mode = obj.mode

        # 切换到编辑模式以读取骨骼数据
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones
        bone_data_list = []

        for e_bone in edit_bones:
            bone_data_list.append({
                'name': e_bone.name,
                'head': e_bone.head.copy(),
                'tail': e_bone.tail.copy(),
                'roll': e_bone.roll,
                'parent_name': e_bone.parent.name if e_bone.parent else None,
            })

        # 恢复原模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 取消选中所有物体
        bpy.ops.object.select_all(action='DESELECT')

        # 为每个骨骼创建空物体
        created_empty_map = {}  # 骨骼名 -> 空物体

        for bone_data in bone_data_list:
            # 创建空物体
            bpy.ops.object.empty_add(
                type='PLAIN_AXES',
                location=bone_data['head'],
                rotation=(0, 0, 0),
            )
            empty_obj = context.active_object
            empty_obj.name = f"{obj.name}_{bone_data['name']}"

            # 计算骨骼方向并设置旋转
            direction = (bone_data['tail'] - bone_data['head']).normalized()
            track_axis = 'Y'  # Blender 骨骼默认沿 Y 轴
            empty_obj.rotation_mode = 'QUATERNION'

            # 计算使 Y 轴指向 tail 方向的四元数
            quat = direction.to_track_quat(track_axis, 'Z')
            empty_obj.rotation_quaternion = quat

            # 存储原始骨骼方向向量，后续在姿态模式下重新读取
            created_empty_map[bone_data['name']] = {
                'obj': empty_obj,
                'parent_name': bone_data['parent_name'],
                'head': bone_data['head'],
                'tail': bone_data['tail'],
                'roll': bone_data['roll'],
            }

        # 切换到姿态模式获取正确的变换
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        for bone_name, info in created_empty_map.items():
            empty_obj = info['obj']
            p_bone = obj.pose.bones.get(bone_name)
            if p_bone:
                # 使用姿态骨骼的矩阵获取世界空间变换
                matrix = obj.matrix_world @ p_bone.matrix
                empty_obj.location = matrix.to_translation()
                empty_obj.rotation_mode = 'QUATERNION'
                empty_obj.rotation_quaternion = matrix.to_quaternion()
                empty_obj.scale = matrix.to_scale()

        # 设置父子关系
        for bone_name, info in created_empty_map.items():
            empty_obj = info['obj']
            parent_name = info['parent_name']
            if parent_name and parent_name in created_empty_map:
                empty_obj.parent = created_empty_map[parent_name]['obj']

        # 恢复对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 选中所有创建的空物体
        bpy.ops.object.select_all(action='DESELECT')
        for info in created_empty_map.values():
            info['obj'].select_set(True)
        if created_empty_map:
            context.view_layer.objects.active = list(created_empty_map.values())[0]['obj']

        self.report(
            {'INFO'},
            f"已将 {len(bone_data_list)} 个骨骼拆分为独立空物体。"
        )

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_convert_bones_rotation_to_quaternion)
    bpy.utils.register_class(OBJECT_OT_split_bones_to_individual_objects)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_convert_bones_rotation_to_quaternion)
    bpy.utils.unregister_class(OBJECT_OT_split_bones_to_individual_objects)


if __name__ == "__main__":
    register()
