import bpy
import json
import math
from bpy_extras.io_utils import ExportHelper


class OBJECT_OT_export_selected_bones_constraints(bpy.types.Operator, ExportHelper):
    """导出所选骨骼约束关系"""
    bl_idname = "object.export_selected_bones_constraints"
    bl_label = "导出所选骨骼约束关系"
    bl_options = {'REGISTER', 'UNDO'}
    
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})
    
    def invoke(self, context, event):
        # 设置默认文件名为活动对象的名称
        if context.active_object:
            self.filepath = f"{context.active_object.name}_constraints.json"
        return super().invoke(context, event)

    def execute(self, context):
        obj = context.active_object
        
        # 1. 基础检查
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选中一个骨架物体 (Armature)。")
            return {'CANCELLED'}

        # 切换到姿态模式
        if original_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        constraints_data = {}

        # 2. 定义需要转换为度数的属性白名单
        angle_properties = {
            "min_x", "max_x", "min_y", "max_y", "min_z", "max_z", # 限制约束
            "angle", # 铰链/锁定追踪
            "offset_x", "offset_y", "offset_z", # 变换/复制旋转
            "map_from_min", "map_from_max", "map_to_min", "map_to_max", # 变换映射
            "reference_position"
        }

        for p_bone in obj.pose.bones:
            # 只处理选中的骨骼
            if p_bone.select:
                if p_bone.constraints:
                    bone_name = p_bone.name
                    constraints_data[bone_name] = []
                    
                    for const in p_bone.constraints:
                        const_dict = {
                            "type": const.type,
                            "name": const.name,
                            "mute": const.mute,
                            "influence": const.influence
                        }

                        # --- 修复部分：安全地获取 target ---
                        # 使用 hasattr 检查是否存在 'target' 属性
                        if hasattr(const, 'target'):
                            if const.target:
                                const_dict["target"] = const.target.name
                            else:
                                const_dict["target"] = None
                        # --- 修复结束 ---

                        # 遍历属性
                        for prop in const.bl_rna.properties:
                            prop_id = prop.identifier
                            
                            # 跳过系统属性
                            if prop_id in ["rna_type", "name", "type", "is_valid", "id_data", "constraints", "bl_rna", "target", "use_offset"]:
                                continue
                                
                            try:
                                # 再次检查属性是否存在（双重保险）
                                if hasattr(const, prop_id):
                                    value = getattr(const, prop_id)
                                    
                                    # --- 核心修改：安全的角度转换逻辑 ---
                                    if isinstance(value, (int, float)):
                                        # 只有当属性名在白名单中，且数值不为0时，才进行转换
                                        if prop_id in angle_properties and value != 0:
                                            value = math.degrees(value)
                                            value = round(value, 2) # 保留2位小数
                                        
                                        const_dict[prop_id] = value
                                    
                                    elif prop_id == "subtarget":
                                        const_dict[prop_id] = value
                            except Exception as e:
                                # 忽略无法读取的属性
                                pass

                        constraints_data[bone_name].append(const_dict)

        if not constraints_data:
            self.report({'INFO'}, "选中的骨骼中没有约束。")
            return {'CANCELLED'}

        # 输出 JSON
        json_output = json.dumps(constraints_data, indent=4, ensure_ascii=False)

        # 保存文件
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(json_output)
            self.report({'INFO'}, f"导出成功！文件已保存至: {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"导出失败: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_export_selected_bones_constraints)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_export_selected_bones_constraints)


if __name__ == "__main__":
    register()
