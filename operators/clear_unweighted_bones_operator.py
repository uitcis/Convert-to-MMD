import bpy
from mathutils import Vector
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..bone_map_and_group import mmd_bone_map, mmd_bone_group

class OBJECT_OT_clear_unweighted_bones(bpy.types.Operator):
    """清理没有权重的骨骼"""
    bl_idname = "object.clear_unweighted_bones"
    bl_label = "Clear Unweighted Bones"
    
    def get_mmd_bone_whitelist(self):
        """获取MMD骨骼白名单"""
        # 从bone_map中获取所有MMD骨骼名称
        mmd_bones = set(mmd_bone_map.values())
        
        # 从bone_group中获取所有MMD骨骼名称
        for group in mmd_bone_group:
            mmd_bones.update(group["bones"])
        
        return mmd_bones
    
    def preprocess_mesh_weights(self, mesh_objects):
        """预处理所有网格对象的权重信息，构建骨骼名称到是否有权重的映射"""
        bone_weight_map = {}
        
        for mesh_obj in mesh_objects:
            # 遍历所有顶点组
            for vg in mesh_obj.vertex_groups:
                bone_name = vg.name
                # 如果该骨骼已经被标记为有权重，跳过
                if bone_name in bone_weight_map and bone_weight_map[bone_name]:
                    continue
                
                # 检查该顶点组是否有权重
                has_weight = False
                # 获取对应的网格数据
                mesh = mesh_obj.data
                if mesh.vertices:
                    # 遍历所有顶点
                    for v in mesh.vertices:
                        # 遍历顶点的所有组
                        for g in v.groups:
                            if g.group == vg.index and g.weight > 0:
                                has_weight = True
                                break
                        if has_weight:
                            break
                
                # 如果有权重，更新映射
                if has_weight:
                    bone_weight_map[bone_name] = True
        
        return bone_weight_map
    
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
            
        # 预处理所有网格对象的权重信息
        bone_weight_map = self.preprocess_mesh_weights(mesh_objects)
        
        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 获取MMD骨骼白名单
        mmd_bone_whitelist = self.get_mmd_bone_whitelist()
        
        # 收集要删除的骨骼
        bones_to_remove = []
        for bone in armature.data.edit_bones:
            # 检查是否是MMD骨骼，如果是则跳过
            if bone.name in mmd_bone_whitelist:
                continue
                
            # 检查骨骼是否有权重
            has_weights = bone.name in bone_weight_map
            
            if not has_weights:
                bones_to_remove.append(bone.name)
        
        # 准备删除骨骼
        self.bones_to_remove = bones_to_remove
        self.armature = armature
        self.remove_bones_with_threads()  # 批量删除骨骼
        
        return {'RUNNING_MODAL'}
    
    def remove_bones_with_threads(self):
        """使用批处理方式删除骨骼，避免线程安全问题"""
        # 批量删除骨骼
        for bone_name in self.bones_to_remove:
            bone = self.armature.data.edit_bones.get(bone_name)
            if bone:
                self.armature.data.edit_bones.remove(bone)
        
        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, f"已删除 {len(self.bones_to_remove)} 个无权重骨骼")

# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_clear_unweighted_bones)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_clear_unweighted_bones)

if __name__ == "__main__":
    register()
