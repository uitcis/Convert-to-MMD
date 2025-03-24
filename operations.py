import bpy
import json
import math

from mathutils import Vector, Matrix, Euler

class OBJECT_OT_fill_from_selection_specific(bpy.types.Operator):
    """从当前选定的骨骼填充特定的骨骼属性"""
    bl_idname = "object.fill_from_selection_specific"
    bl_label = "Fill from Selection Specific"
    
    bone_property : bpy.props.StringProperty(name="Bone Property")# type: ignore

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        mode = context.mode

        if mode == 'POSE':
            selected_bones = [bone.name for bone in obj.pose.bones if bone.bone.select]
        elif mode == 'EDIT_ARMATURE':
            selected_bones = [bone.name for bone in obj.data.edit_bones if bone.select]
        else:
            self.report({'ERROR'}, "请在姿态模式或编辑模式下选择骨骼")
            return {'CANCELLED'}

        if not selected_bones:
            self.report({'ERROR'}, "未选择骨骼")
            return {'CANCELLED'}

        # 将第一个选定的骨骼填充到指定属性中
        setattr(scene, self.bone_property, selected_bones[0])

        return {'FINISHED'}

class OBJECT_OT_export_preset(bpy.types.Operator):
    """导出当前骨骼配置为预设"""
    bl_idname = "object.export_preset"
    bl_label = "Export Preset"
    filepath : bpy.props.StringProperty(subtype="FILE_PATH")# type: ignore

    def execute(self, context):
        scene = context.scene
        preset = {}
        for prop_name in get_bones_list():  # 确保 get_bones_list 在当前作用域中
            preset[prop_name] = getattr(scene, prop_name, "")

        with open(self.filepath, 'w') as file:
            json.dump(preset, file, indent=4)

        self.report({'INFO'}, f"预设已导出到 {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        # 设置默认文件名为 CTMMD.json
        self.filepath = bpy.path.ensure_ext("CTMMD", ".json")
        return {'RUNNING_MODAL'}

class OBJECT_OT_import_preset(bpy.types.Operator):
    """导入骨骼配置预设"""
    bl_idname = "object.import_preset"
    bl_label = "Import Preset"
    filepath : bpy.props.StringProperty(subtype="FILE_PATH")# type: ignore

    def execute(self, context):
        scene = context.scene
        try:
            with open(self.filepath, 'r') as file:
                preset = json.load(file)
        except Exception as e:
            self.report({'ERROR'}, f"加载预设失败：{str(e)}")
            return {'CANCELLED'}

        for prop_name, value in preset.items():
            if prop_name in get_bones_list():
                setattr(scene, prop_name, value)

        self.report({'INFO'}, f"已从 {self.filepath} 导入预设")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        # 设置文件过滤器仅显示 JSON 文件
        self.filter_glob = "*.json"
        return {'RUNNING_MODAL'}

def get_bones_list():
    """生成骨骼属性名称列表"""
    fingers = ["thumb", "index", "middle", "ring", "pinky"]
    finger_segments = {
        "thumb": ["0", "1", "2"],
        "index": ["1", "2", "3"],
        "middle": ["1", "2", "3"],
        "ring": ["1", "2", "3"],
        "pinky": ["1", "2", "3"]
    }
    
    bone_list = {
        "all_parents_bone": "",
        "center_bone": "",
        "groove_bone": "",
        "hip_bone": "",
        "upper_body_bone": "",
        "upper_body2_bone": "",
        "neck_bone": "",
        "head_bone": "",
        "left_shoulder_bone": "",
        "right_shoulder_bone": "",  
        "left_upper_arm_bone": "",
        "right_upper_arm_bone": "",
        "left_lower_arm_bone": "",
        "right_lower_arm_bone": "",
        "left_hand_bone": "",
        "right_hand_bone": "",
        "lower_body_bone": "",  
        "left_thigh_bone": "",
        "right_thigh_bone": "",
        "left_calf_bone": "",
        "right_calf_bone": "",
        "left_foot_bone": "",
        "right_foot_bone": "",
        "left_toe_bone": "",
        "right_toe_bone": "",
        "control_center_bone": "",
        "left_eye_bone": "",
        "right_eye_bone": ""
    }
    
    for finger_base, segments in finger_segments.items():
        for side in ["left", "right"]:
            for i, segment in enumerate(segments):
                bone_list[f"{side}_{finger_base}_{segment}"] = ""
    
    return bone_list

# 新增的T-Pose到A-Pose转换操作符
class OBJECT_OT_convert_to_apose(bpy.types.Operator):
    """将骨架转换为 A-Pose 并应用为新的静置姿态"""
    bl_idname = "object.convert_to_apose" 
    bl_label = "Convert to A-Pose"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        
        # 获取骨骼名称
        arm_bones = {
            "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
            "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
        }

        # 检查是否有设置骨骼
        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置要转换的骨骼")
            return {'CANCELLED'}

        # 1. 确保在对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 2. 找到所有使用这个骨骼的网格对象，并检查形态键
        meshes_with_armature = []
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type == 'MESH':
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj:
                        # 检查是否有形态键
                        if not mesh_obj.data.shape_keys:
                            meshes_with_armature.append(mesh_obj)
                        break

        # 检查是否找到可用的网格
        if not meshes_with_armature:
            self.report({'ERROR'}, "没有找到可用的网格。请分离身体网格并清除形态键后再试")
            return {'CANCELLED'}

        # 3. 为每个网格复制骨骼修改器，但保留原始修改器
        for mesh_obj in meshes_with_armature:
            for modifier in mesh_obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object == obj:
                    # 复制修改器
                    new_modifier = mesh_obj.modifiers.new(name=modifier.name + "_copy", type='ARMATURE')
                    new_modifier.object = modifier.object
                    new_modifier.use_vertex_groups = modifier.use_vertex_groups
                    new_modifier.use_bone_envelopes = modifier.use_bone_envelopes
                    break

        # 4. 切换到姿态模式设置A-Pose
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 5. 清除所有现有姿态
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')

        # 6. 为骨骼设置A-Pose旋转
        pose_bones = obj.pose.bones
        converted_bones = []

        for bone_type, bone_name in arm_bones.items():
            if bone_name and bone_name in pose_bones:
                bone = pose_bones[bone_name]
                bone.rotation_mode = 'XYZ'
                
                # 根据骨骼类型设置不同的旋转角度
                if bone_type == "left_upper_arm":
                    rotation_matrix = Matrix.Rotation(math.radians(37), 4, 'Y')
                elif bone_type == "right_upper_arm":
                    rotation_matrix = Matrix.Rotation(math.radians(-37), 4, 'Y')
                
                # 应用旋转矩阵
                bone.matrix = rotation_matrix @ bone.matrix
                
                converted_bones.append(bone_name)

        if not converted_bones:
            self.report({'WARNING'}, "没有找到匹配的骨骼可以转换")
            return {'CANCELLED'}

        # 7. 更新视图以确保姿态已应用
        context.view_layer.update()

        # 8. 应用第二个修改器（复制的修改器）来调整网格姿态
        try:
            for mesh_obj in meshes_with_armature:
                context.view_layer.objects.active = mesh_obj
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj and "_copy" in modifier.name:
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
                        break
        except RuntimeError as e:
            self.report({'ERROR'}, f"应用修改器时出错：{str(e)}")
            return {'CANCELLED'}

        # 9. 切换回骨骼对象
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 10. 应用当前姿态为新的静置姿态
        bpy.ops.pose.armature_apply()

        self.report({'INFO'}, f"已完成A-Pose转换并应用为新的静置姿态")
        return {'FINISHED'}
