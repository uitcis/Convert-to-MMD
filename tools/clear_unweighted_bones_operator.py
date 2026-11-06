import bpy

from .. import bone_utils
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
    
    def preprocess_mesh_weights(self, mesh_objects, candidate_names):
        """预处理网格权重，返回至少拥有一个非零权重的候选骨骼名集合。

        只检查 candidate_names（非MMD白名单的候选清理骨骼）对应的顶点组，
        且每个顶点只遍历一次，避免原先「每个顶点组从头扫描所有顶点」的
        三层嵌套导致的大网格卡顿。
        """
        weighted_bones = set()

        for mesh_obj in mesh_objects:
            # 该网格中属于候选骨骼的顶点组：组索引 -> 骨骼名
            index_to_name = {
                vg.index: vg.name for vg in mesh_obj.vertex_groups
                if vg.name in candidate_names
            }
            if not index_to_name:
                continue

            # 每个顶点只访问一次，命中候选组且权重大于0即标记
            for v in mesh_obj.data.vertices:
                for g in v.groups:
                    if g.weight > 0 and g.group in index_to_name:
                        weighted_bones.add(index_to_name[g.group])
        
        return weighted_bones
    
    def execute(self, context):
        armature = bone_utils.resolve_armature(context)
        if not armature:
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
            
        # 获取场景中的所有网格对象
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "场景中没有网格对象")
            return {'CANCELLED'}
            
        # 获取MMD骨骼白名单，收集候选清理的骨骼（非白名单骨骼）
        mmd_bone_whitelist = self.get_mmd_bone_whitelist()
        candidate_names = {
            bone.name for bone in armature.data.bones
            if bone.name not in mmd_bone_whitelist
        }
        
        # 预处理网格权重：只检查候选骨骼是否有非零权重
        weighted_bone_names = self.preprocess_mesh_weights(mesh_objects, candidate_names)
        
        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 收集要删除的骨骼
        bones_to_remove = []
        for bone in armature.data.edit_bones:
            if bone.name in mmd_bone_whitelist:
                continue
            if bone.name not in weighted_bone_names:
                bones_to_remove.append(bone.name)
        
        # 批量删除骨骼
        for bone_name in bones_to_remove:
            bone = armature.data.edit_bones.get(bone_name)
            if bone:
                armature.data.edit_bones.remove(bone)
        
        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        if bones_to_remove:
            self.report({'INFO'}, f"已删除 {len(bones_to_remove)} 个无权重骨骼")
        else:
            self.report({'INFO'}, "没有需要删除的无权重骨骼")
        
        return {'FINISHED'}

# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_clear_unweighted_bones)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_clear_unweighted_bones)

if __name__ == "__main__":
    register()
