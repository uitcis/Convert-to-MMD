import bpy
import json
from . import bone_mapping # 新增导入语句
from mathutils import Vector, Matrix, Euler
class OBJECT_OT_fill_from_selection_specific(bpy.types.Operator):
    """Operator which fills a specific bone property from the currently selected bone"""
    bl_idname = "object.fill_from_selection_specific"
    bl_label = "Fill from Selection Specific"
    
    bone_property: bpy.props.StringProperty(name="Bone Property")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature object selected")
            return {'CANCELLED'}

        scene = context.scene
        selected_bones = [bone.name for bone in obj.pose.bones if bone.bone.select]

        if not selected_bones:
            self.report({'ERROR'}, "No bones selected")
            return {'CANCELLED'}

        # Fill the first selected bone into the specified property
        setattr(scene, self.bone_property, selected_bones[0])

        return {'FINISHED'}        
class OBJECT_OT_rename_to_mmd(bpy.types.Operator):
    """Operator which renames selected bones to MMD format"""
    bl_idname = "object.rename_to_mmd"
    bl_label = "Rename to MMD"

    mmd_bone_mapping = bone_mapping.mmd_bone_mapping  # 使用导入的bone_mapping模块

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature object selected")
            return {'CANCELLED'}

        scene = context.scene
        for prop_name, new_name in self.mmd_bone_mapping.items():
            bone_name = getattr(scene, prop_name, None)
            if bone_name:
                bone = obj.pose.bones.get(bone_name)
                if bone:
                    # 检查骨骼是否已经重命名为MMD格式的名称
                    if bone.name != new_name:
                        bone.name = new_name
                        # 更新场景中的骨骼属性值
                        setattr(scene, prop_name, new_name)
                    else:
                        self.report({'INFO'}, f"Bone '{bone_name}' is already renamed to {new_name}")
                else:
                    self.report({'WARNING'}, f"Bone '{bone_name}' not found for renaming to {new_name}")

        return {'FINISHED'}

    def rename_finger_bone(self, context, obj, scene, base_finger_name, segment):
        for side in ["left", "right"]:
            prop_name = f"{side}_{base_finger_name}_{segment}"
            if prop_name in self.mmd_bone_mapping:
                new_name = self.mmd_bone_mapping.get(prop_name)
                bone_name = getattr(scene, prop_name, None)
                if bone_name:
                    bone = obj.pose.bones.get(bone_name)
                    if bone:
                        # 检查骨骼是否已经重命名为MMD格式的名称
                        if bone.name != new_name:
                            bone.name = new_name
                            # 更新场景中的骨骼属性值
                            setattr(scene, prop_name, new_name)
                        else:
                            self.report({'INFO'}, f"Bone '{bone_name}' is already renamed to {new_name}")
                    else:
                        self.report({'WARNING'}, f"Bone '{bone_name}' not found for renaming to {new_name}")

class OBJECT_OT_complete_missing_bones(bpy.types.Operator):
    """Operator which completes missing bones for MMD format"""
    bl_idname = "object.complete_missing_bones"
    bl_label = "Complete Missing Bones"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected")
            return {'CANCELLED'}

        existing_bones = obj.pose.bones

        # 确保我们在EDIT模式
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = obj.data.edit_bones

        # 检查上半身骨骼是否存在并获取其头部位置
        upper_body_bone = existing_bones.get("上半身")
        if not upper_body_bone:
            self.report({'ERROR'}, "上半身 bone does not exist")
            return {'CANCELLED'}
        
        # 断开上半身与其当前父级的连接
        if upper_body_bone.parent:
            upper_body_edit_bone = edit_bones[upper_body_bone.name]
            upper_body_edit_bone.use_connect = False
            upper_body_edit_bone.parent = None

        # 获取上半身骨骼的坐标
        upper_body_head = upper_body_bone.head.copy()

        # 定义骨骼属性
        bone_properties = {
            "全ての親": {"parent": None, "head": Vector((0, 0, 0)), "tail": Vector((0, 0, 0.3))},
            "センター": {"parent": "全ての親", "head": Vector((0, 0, 0.3)), "tail": Vector((0, 0, 0.6))},
            "グルーブ": {"parent": "センター", "head": Vector((0, 0, 0.8)), "tail": Vector((0, 0, 0.7))},
            "腰": {"parent": "グルーブ", "head": upper_body_head + Vector((0, 0.1, -0.15)), "tail": upper_body_head},
            "下半身": {"parent": "腰", "head": upper_body_head, "tail": upper_body_head + Vector((0, 0, -0.3))}
        }

        # 按顺序检查并创建或更新骨骼
        for bone_name in bone_properties:
            bone = existing_bones.get(bone_name)
            if bone:
                # 清空骨骼的父级
                bone_edit = edit_bones[bone_name]
                bone_edit.use_connect = False
                bone_edit.parent = None
            else:
                # 创建骨骼
                bone_edit = edit_bones.new(bone_name)
                bone_edit.use_connect = False

            # 设置骨骼的属性
            bone_edit.parent = edit_bones.get(bone_properties[bone_name]["parent"]) if bone_properties[bone_name]["parent"] else None
            bone_edit.head = bone_properties[bone_name]["head"] if bone_properties[bone_name]["head"] is not None else bone_edit.head
            bone_edit.tail = bone_properties[bone_name]["tail"] if bone_properties[bone_name]["tail"] is not None else bone_edit.tail

            # 设置所有骨骼的扭转为0
            bone_edit.roll = 0.0

        # 设置上半身的父级为腰
        if "上半身" in existing_bones:
            upper_body_edit_bone = edit_bones["上半身"]
            upper_body_edit_bone.parent = edit_bones.get("腰")
            upper_body_edit_bone.use_connect = False
            upper_body_edit_bone.roll = 0.0

        # 编辑后切换回POSE模式
        bpy.ops.object.mode_set(mode='POSE')

        # 检查并调用mmd_tools.convert_to_mmd_model()
        try:
            bpy.ops.mmd_tools.convert_to_mmd_model()
        except AttributeError:
            self.report({'ERROR'}, "Please install or enable the mmdtools add-on.")
            return {'CANCELLED'}

        return {'FINISHED'}
def get_bones_list():
    """Generates the list of bone property names."""
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
        "groove_bone": "",
        "center_bone": "",
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
class OBJECT_OT_export_preset(bpy.types.Operator):
    """Operator which exports the current bone configuration as a preset"""
    bl_idname = "object.export_preset"
    bl_label = "Export Preset"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        scene = context.scene
        preset = {}
        for prop_name in get_bones_list():  # 确保get_bones_list在当前作用域内被引用
            preset[prop_name] = getattr(scene, prop_name, "")

        with open(self.filepath, 'w') as file:
            json.dump(preset, file, indent=4)

        self.report({'INFO'}, f"Preset exported to {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        # 设置默认文件名为CTMMD.json
        self.filepath = bpy.path.ensure_ext("CTMMD", ".json")
        return {'RUNNING_MODAL'}

class OBJECT_OT_import_preset(bpy.types.Operator):
    """Operator which imports a bone configuration preset"""
    bl_idname = "object.import_preset"
    bl_label = "Import Preset"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        scene = context.scene
        try:
            with open(self.filepath, 'r') as file:
                preset = json.load(file)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load preset: {str(e)}")
            return {'CANCELLED'}

        for prop_name, value in preset.items():
            if prop_name in get_bones_list():
                setattr(scene, prop_name, value)

        self.report({'INFO'}, f"Preset imported from {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        # 设置文件过滤器为仅显示JSON文件
        self.filter_glob = "*.json"
        return {'RUNNING_MODAL'}

