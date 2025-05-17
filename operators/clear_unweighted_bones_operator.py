import bpy
from mathutils import Vector

class OBJECT_OT_clear_unweighted_bones(bpy.types.Operator):
    """清理没有权重的骨骼"""
    bl_idname = "object.clear_unweighted_bones"
    bl_label = "Clear Unweighted Bones"
    
    def has_vertex_groups(self, bone_name, obj):
        """检查骨骼是否有对应的顶点组且有权重"""
        # 查找与骨骼同名的顶点组
        vertex_group = obj.vertex_groups.get(bone_name)
        if not vertex_group:
            return False
            
        # 检查该顶点组是否有权重
        for mesh in bpy.data.meshes:
            if mesh.vertices:
                for v in mesh.vertices:
                    for g in v.groups:
                        if g.group == vertex_group.index and g.weight > 0:
                            return True
        return False
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
            
        # 获取场景中的所有网格对象
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "场景中没有网格对象")
            return {'CANCELLED'}
            
        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 收集要删除的骨骼
        bones_to_remove = []
        for bone in armature.data.edit_bones:
            has_weights = False
            # 检查所有网格对象中是否有该骨骼的权重
            for mesh_obj in mesh_objects:
                if self.has_vertex_groups(bone.name, mesh_obj):
                    has_weights = True
                    break
            
            if not has_weights:
                bones_to_remove.append(bone.name)
        
        # 使用定时器分步删除骨骼，防止界面卡死
        self.bones_to_remove = bones_to_remove
        self.armature = armature
        self.current_index = 0
        bpy.app.timers.register(self.remove_bones_step)
        
        return {'RUNNING_MODAL'}
    
    def remove_bones_step(self):
        if self.current_index >= len(self.bones_to_remove):
            # 返回物体模式
            bpy.ops.object.mode_set(mode='OBJECT')
            self.report({'INFO'}, f"已删除 {len(self.bones_to_remove)} 个无权重骨骼")
            return None
        
        bone_name = self.bones_to_remove[self.current_index]
        bone = self.armature.data.edit_bones.get(bone_name)
        if bone:
            self.armature.data.edit_bones.remove(bone)
        
        self.current_index += 1
        return 0.01  # 每0.01秒处理一个骨骼

class OBJECT_OT_merge_single_child_bones(bpy.types.Operator):
    """合并只有一个子级的骨骼"""
    bl_idname = "object.merge_single_child_bones"
    bl_label = "Merge Single Child Bones"
    
    def should_merge_bone(self, bone):
        """检查骨骼是否应该被合并"""
        # 计算直接子骨骼数量
        children = [child for child in bone.children]
        # 如果只有一个子骨骼，且该子骨骼没有其他子骨骼，则可以合并
        if len(children) == 1 and len(children[0].children) == 0:
            return True
        return False
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        bones_merged = 0
        # 遍历所有骨骼
        for bone in list(armature.data.edit_bones):  # 创建副本以避免在迭代时修改
            if not bone.parent:  # 跳过没有父级的骨骼
                continue
                
            if self.should_merge_bone(bone.parent):
                parent = bone.parent
                # 更新父骨骼的尾部位置为子骨骼的尾部位置
                parent.tail = bone.tail
                # 重新连接所有原来连接到子骨骼的骨骼
                for child in bone.children:
                    child.parent = parent
                # 删除子骨骼
                armature.data.edit_bones.remove(bone)
                bones_merged += 1
        
        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        self.report({'INFO'}, f"已合并 {bones_merged} 个单子级骨骼")
        return {'FINISHED'}

# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_clear_unweighted_bones)
    bpy.utils.register_class(OBJECT_OT_merge_single_child_bones)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_clear_unweighted_bones)
    bpy.utils.unregister_class(OBJECT_OT_merge_single_child_bones)

if __name__ == "__main__":
    register()
