import bpy
import json

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

class OBJECT_OT_export_preset(bpy.types.Operator):
    """Operator which exports the current bone configuration as a preset"""
    bl_idname = "object.export_preset"
    bl_label = "Export Preset"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        scene = context.scene
        preset = {}
        for prop_name in get_bones_list():  # Ensure get_bones_list is in the current scope
            preset[prop_name] = getattr(scene, prop_name, "")

        with open(self.filepath, 'w') as file:
            json.dump(preset, file, indent=4)

        self.report({'INFO'}, f"Preset exported to {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        # Set default file name to CTMMD.json
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
        # Set file filter to only show JSON files
        self.filter_glob = "*.json"
        return {'RUNNING_MODAL'}

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