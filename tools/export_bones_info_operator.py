import bpy
import json
from bpy_extras.io_utils import ExportHelper

class OBJECT_OT_export_selected_bones_info(bpy.types.Operator, ExportHelper):
    bl_idname = "object.export_selected_bones_info"
    bl_label = "导出所选骨骼信息"
    bl_description = "导出当前所选骨骼的位置、权重和父子关系"
    
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})
    
    def invoke(self, context, event):
        # 设置默认文件名为活动对象的名称
        if context.active_object:
            self.filepath = f"{context.active_object.name}_bones_info.json"
        return super().invoke(context, event)
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}
        
        # 获取选中的骨骼
        selected_bones = []
        mode = obj.mode
        
        if mode == 'EDIT':
            # 在编辑模式下，从edit_bones获取
            selected_bones = [edit_bone.bone for edit_bone in obj.data.edit_bones if edit_bone.select]
        elif mode == 'POSE':
            # 在姿态模式下，从pose_bones获取
            selected_bones = [p_bone.bone for p_bone in obj.pose.bones if p_bone.select]
        else:
            # 在对象模式下，检查是否选中了整个骨架
            if obj.select:
                selected_bones = list(obj.data.bones)
            else:
                self.report({'ERROR'}, "没有选中任何骨骼")
                return {'CANCELLED'}
        
        # 如果没有选中的骨骼，返回错误
        if not selected_bones:
            self.report({'ERROR'}, "没有选中任何骨骼")
            return {'CANCELLED'}
        
        # 收集骨骼信息
        bones_info = []
        for bone in selected_bones:
            # 收集位置、旋转、缩放
            bone_info = {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "location": list(bone.head_local),
                "rotation": list(bone.matrix.to_euler()),
                "scale": list(bone.matrix.to_scale()),
                "is_weight_bone": False
            }
            
            # 检查是否为权重骨骼
            # 检查是否有对应的顶点组
            for vg in obj.vertex_groups:
                # 不区分大小写比较骨骼名称和顶点组名称
                if vg.name.lower() == bone.name.lower():
                    bone_info["is_weight_bone"] = True
                    break
            # 如果还没有找到，检查顶点组名称是否包含骨骼名称
            if not bone_info["is_weight_bone"]:
                for vg in obj.vertex_groups:
                    if bone.name.lower() in vg.name.lower():
                        bone_info["is_weight_bone"] = True
                        break
            # 最后，检查是否有顶点使用了与骨骼相关的权重组
            if not bone_info["is_weight_bone"] and hasattr(obj.data, 'vertices'):
                for v in obj.data.vertices:
                    for g in v.groups:
                        vg = obj.vertex_groups[g.group]
                        if (vg.name.lower() == bone.name.lower() or 
                            bone.name.lower() in vg.name.lower()) and g.weight > 0.0:
                            bone_info["is_weight_bone"] = True
                            break
                    if bone_info["is_weight_bone"]:
                        break
            
            bones_info.append(bone_info)
        
        # 导出到JSON文件
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(bones_info, f, ensure_ascii=False, indent=2)
            self.report({'INFO'}, f"已成功导出{len(selected_bones)}个骨骼的信息到 {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"导出失败: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

def register():
    bpy.utils.register_class(OBJECT_OT_export_selected_bones_info)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_export_selected_bones_info)

if __name__ == "__main__":
    register()