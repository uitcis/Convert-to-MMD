import bpy
from .. import bone_map_and_group


class OBJECT_OT_merge_bones_base(bpy.types.Operator):
    """合并骨骼链基类"""
    bl_options = {'REGISTER', 'UNDO'}
    
    # 子类需要重写这些属性
    target_bones = []
    bone_type = "骨骼"
    
    def get_mmd_bones(self):
        """获取MMD骨骼列表"""
        mmd_bones = set()
        for bone_name in bone_map_and_group.mmd_bone_map.values():
            mmd_bones.add(bone_name)
        for bone_group in bone_map_and_group.mmd_bone_group:
            for bone_name in bone_group.get("bones", []):
                mmd_bones.add(bone_name)
        return mmd_bones
    
    def find_all_children(self, start_bone, mmd_bones):
        """找到起始骨骼的所有子级骨骼（排除MMD骨骼及其子级）"""
        bones_to_merge = []
        
        def recursive_find_children(bone):
            for child in bone.children:
                if child.name not in mmd_bones:
                    bones_to_merge.append(child)
                    # 只有当子级不是MMD骨骼时，才继续递归遍历它的子级
                    recursive_find_children(child)
        
        recursive_find_children(start_bone)
        return bones_to_merge
    
    def merge_vertex_groups(self, obj, target_bone_name, source_bone_name):
        """合并顶点组"""
        if not obj or obj.type != 'MESH':
            return
        
        target_vg = obj.vertex_groups.get(target_bone_name)
        source_vg = obj.vertex_groups.get(source_bone_name)
        
        if not source_vg:
            return
        
        if not target_vg:
            target_vg = obj.vertex_groups.new(name=target_bone_name)
        
        for vertex in obj.data.vertices:
            for group in vertex.groups:
                if group.group == source_vg.index:
                    target_vg.add([vertex.index], group.weight, 'ADD')
        
        obj.vertex_groups.remove(source_vg)
    
    def merge_bone_chain(self, armature, start_bone_name, mmd_bones):
        """合并起始骨骼的所有子级骨骼（排除MMD骨骼）"""
        start_bone = armature.data.edit_bones.get(start_bone_name)
        
        if not start_bone:
            return 0
        
        bones_to_merge = self.find_all_children(start_bone, mmd_bones)
        
        if not bones_to_merge:
            return 0
        
        merged_count = 0
        
        for bone in bones_to_merge:
            children = list(bone.children)
            
            for child in children:
                if child != start_bone:
                    child.parent = start_bone
            
            for obj in bpy.context.scene.objects:
                if obj.type == 'MESH':
                    for modifier in obj.modifiers:
                        if modifier.type == 'ARMATURE' and modifier.object == armature:
                            self.merge_vertex_groups(obj, start_bone_name, bone.name)
                            break
            
            armature.data.edit_bones.remove(bone)
            merged_count += 1
        
        return merged_count
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        mmd_bones = self.get_mmd_bones()
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        total_merged = 0
        
        for bone_name in self.target_bones:
            merged = self.merge_bone_chain(armature, bone_name, mmd_bones)
            total_merged += merged
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        if total_merged > 0:
            self.report({'INFO'}, f"已合并 {total_merged} 个{self.bone_type}")
        else:
            self.report({'INFO'}, f"没有找到需要合并的{self.bone_type}")
        
        return {'FINISHED'}


class OBJECT_OT_merge_leg_bones(OBJECT_OT_merge_bones_base):
    """合并足部骨骼链"""
    bl_idname = "object.merge_leg_bones"
    bl_label = "合并足部骨骼链"
    
    target_bones = ["左足", "右足", "左ひざ", "右ひざ"]
    bone_type = "足部骨骼"


class OBJECT_OT_merge_arm_bones(OBJECT_OT_merge_bones_base):
    """合并手臂骨骼链"""
    bl_idname = "object.merge_arm_bones"
    bl_label = "合并手臂骨骼链"
    
    target_bones = ["左腕", "右腕", "左ひじ", "右ひじ"]
    bone_type = "手臂骨骼"


def register():
    bpy.utils.register_class(OBJECT_OT_merge_leg_bones)
    bpy.utils.register_class(OBJECT_OT_merge_arm_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_merge_leg_bones)
    bpy.utils.unregister_class(OBJECT_OT_merge_arm_bones)


if __name__ == "__main__":
    register()
