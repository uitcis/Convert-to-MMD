import bpy

from .. import bone_utils
from ..bone_map_and_group import mmd_bone_map, mmd_bone_group


class OBJECT_OT_clear_unweighted_bones(bpy.types.Operator):
    """清理没有权重的骨骼"""
    bl_idname = "object.clear_unweighted_bones"
    bl_label = "Clear Unweighted Bones"
    bl_options = {'REGISTER', 'UNDO'}

    def get_mmd_bone_whitelist(self):
        """获取MMD骨骼白名单"""
        # 从bone_map中获取所有MMD骨骼名称
        mmd_bones = set(mmd_bone_map.values())

        # 从bone_group中获取所有MMD骨骼名称
        for group in mmd_bone_group:
            mmd_bones.update(group["bones"])

        return mmd_bones

    def get_bound_meshes(self, armature):
        """所有绑定到该骨架的网格（Armature 修改器指向它，或父级是它，取并集）。"""
        meshes = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            has_modifier = any(
                mod.type == 'ARMATURE' and mod.object == armature
                for mod in obj.modifiers
            )
            if obj.parent == armature or has_modifier:
                meshes.append(obj)
        return meshes

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

    def collect_plan(self, armature):
        """返回 (待删除骨骼名列表, 绑定网格数量)；无绑定网格时返回 (None, 原因)。"""
        mesh_objects = self.get_bound_meshes(armature)
        if not mesh_objects:
            return None, "没有绑定到该骨架的网格，已取消"

        mmd_bone_whitelist = self.get_mmd_bone_whitelist()
        candidate_names = {
            bone.name for bone in armature.data.bones
            if bone.name not in mmd_bone_whitelist
        }
        weighted_bone_names = self.preprocess_mesh_weights(mesh_objects, candidate_names)
        bones_to_remove = [
            bone.name for bone in armature.data.bones
            if bone.name not in mmd_bone_whitelist
            and bone.name not in weighted_bone_names
        ]
        return bones_to_remove, len(mesh_objects)

    def invoke(self, context, event):
        armature = bone_utils.resolve_armature(context)
        if not armature:
            self.report({'WARNING'}, "请选择一个骨架")
            return {'CANCELLED'}

        bones_to_remove, info = self.collect_plan(armature)
        if bones_to_remove is None:
            self.report({'WARNING'}, info)
            return {'CANCELLED'}
        if not bones_to_remove:
            self.report({'INFO'}, f"没有需要删除的无权重骨骼（检查了 {info} 个绑定网格）")
            return {'CANCELLED'}

        self._pending_bones = list(bones_to_remove)
        self._bound_mesh_count = info
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        pending = list(getattr(self, "_pending_bones", []))
        layout.label(text=f"将删除 {len(pending)} 根无权重骨骼"
                          f"（检查了 {getattr(self, '_bound_mesh_count', 0)} 个绑定网格）")
        layout.label(text="删除后可用 Ctrl+Z 撤销")
        col = layout.column(align=True)
        for name in pending[:40]:
            col.label(text=name)
        if len(pending) > 40:
            col.label(text=f"... 另有 {len(pending) - 40} 根")

    def execute(self, context):
        armature = bone_utils.resolve_armature(context)
        if not armature:
            self.report({'WARNING'}, "请选择一个骨架")
            return {'CANCELLED'}

        bones_to_remove = list(getattr(self, "_pending_bones", []) or [])
        if not bones_to_remove:
            bones_to_remove, info = self.collect_plan(armature)
            if bones_to_remove is None:
                self.report({'WARNING'}, info)
                return {'CANCELLED'}
            if not bones_to_remove:
                self.report({'INFO'}, f"没有需要删除的无权重骨骼（检查了 {info} 个绑定网格）")
                return {'FINISHED'}

        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')

        removed = []
        for bone_name in bones_to_remove:
            bone = armature.data.edit_bones.get(bone_name)
            if bone:
                armature.data.edit_bones.remove(bone)
                removed.append(bone_name)

        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')

        if removed:
            self.report({'INFO'}, f"已删除 {len(removed)} 根无权重骨骼: {', '.join(removed)}")
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
