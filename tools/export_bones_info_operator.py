import bpy
import json
from bpy_extras.io_utils import ExportHelper

def round_float(value, decimals=4):
    """将浮点数四舍五入到指定小数位数"""
    return round(value, decimals)

def round_vector(vec, decimals=4):
    """将向量的每个分量四舍五入到指定小数位数"""
    return [round(v, decimals) for v in vec]

def get_bone_collections(bone):
    """获取骨骼所属的集合/层信息"""
    # Blender 4.0+ 使用 bone.collections
    if hasattr(bone, 'collections') and bone.collections:
        collections = [coll.name for coll in bone.collections]
        return {"type": "collections", "data": collections}
    # 旧版本 Blender 使用 bone.layers
    elif hasattr(bone, 'layers'):
        layers = []
        for i, layer_enabled in enumerate(bone.layers):
            if layer_enabled:
                layers.append(i + 1)  # 转换为1-based索引
        return {"type": "layers", "data": layers}
    return {"type": "unknown", "data": []}

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
        
        # 获取选中的骨骼和对应的edit_bones（用于获取roll值）
        selected_bones = []
        edit_bones_roll = {}  # 存储骨骼名称到roll值的映射
        mode = obj.mode
        
        if mode == 'EDIT':
            # 在编辑模式下，收集edit_bones的roll值并获取对应的Bone对象
            for edit_bone in obj.data.edit_bones:
                if edit_bone.select:
                    edit_bones_roll[edit_bone.name] = edit_bone.roll
                    selected_bones.append(obj.data.bones[edit_bone.name])
        elif mode == 'POSE':
            # 在姿态模式下，从pose_bones获取
            selected_bones = [p_bone.bone for p_bone in obj.pose.bones if p_bone.select]
        else:
            # 在对象模式下，检查是否选中了整个骨架
            if obj.select_get():
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
            # 收集位置、旋转、缩放（保留四位小数）
            roll_value = edit_bones_roll.get(bone.name, None)
            bone_info = {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "collections": get_bone_collections(bone),
                "head_local": round_vector(bone.head_local),
                "tail_local": round_vector(bone.tail_local),
                "use_connect": bone.use_connect,
                "roll": round_float(roll_value) if roll_value is not None else None,
                "rotation": round_vector(bone.matrix.to_euler()),
                "scale": round_vector(bone.matrix.to_scale()),
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