import bpy


class OBJECT_OT_correct_bones(bpy.types.Operator):
    """归正骨骼：创建备份、设置原点并取消动画，如果骨骼原点已在正确位置，则不需要点击"""
    bl_idname = "object.correct_bones"
    bl_label = "Correct Bones"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        
        # 获取上半身骨骼
        upper_body_bone_name = getattr(scene, "upper_body_bone", None)
        if not upper_body_bone_name:
            self.report({'ERROR'}, "请先设置上半身骨骼")
            return {'CANCELLED'}

        upper_body_bone = obj.pose.bones.get(upper_body_bone_name)
        if not upper_body_bone:
            self.report({'ERROR'}, f"未找到上半身骨骼：{upper_body_bone_name}")
            return {'CANCELLED'}

        # 创建骨架备份
        backup_data = obj.data.copy()
        backup_data.name = f"{obj.data.name}_backup"
        backup_obj = bpy.data.objects.new(f"{obj.name}_backup", backup_data)
        bpy.context.collection.objects.link(backup_obj)
        
        backup_obj.matrix_world = obj.matrix_world
        backup_obj.hide_viewport = True
        backup_obj.hide_render = True
        
        self.report({'INFO'}, f"已创建骨架备份：{backup_obj.name}")

        # 获取上半身骨骼的头部位置（世界坐标）
        upper_body_bone_obj = obj.data.bones.get(upper_body_bone_name)
        if not upper_body_bone_obj:
            self.report({'ERROR'}, f"未找到骨骼数据：{upper_body_bone_name}")
            return {'CANCELLED'}
        
        # 计算目标原点位置（世界坐标）：X 为上半身骨骼的 X，Y 和 Z 为 0
        target_location = obj.matrix_world @ upper_body_bone_obj.head_local
        target_origin = (target_location.x, target_location.y, 0.0)
        
        # 保存骨架对象当前的位置
        original_location = obj.location.copy()
        
        # 将 3D 游标移动到目标原点位置
        original_cursor_location = context.scene.cursor.location.copy()
        context.scene.cursor.location = target_origin
        
        # 切换到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 选择骨架对象
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        
        # 使用 origin_set 操作符将原点设置到 3D 游标位置
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
        
        # 切换回姿态模式
        bpy.ops.object.mode_set(mode='POSE')
        
        # 将骨架坐标归零
        obj.location = (0.0, 0.0, 0.0)
        
        # 清除所有姿态和动画
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')
        
        # 删除所有动作（动画）
        if obj.animation_data:
            obj.animation_data.action = None
            if obj.animation_data.nla_tracks:
                for track in obj.animation_data.nla_tracks:
                    obj.animation_data.nla_tracks.remove(track)
        # 重新加载视图
        context.view_layer.update()
        
        self.report({'INFO'}, "已归正骨骼：设置原点并清除动画")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_correct_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_correct_bones)


if __name__ == "__main__":
    register()
