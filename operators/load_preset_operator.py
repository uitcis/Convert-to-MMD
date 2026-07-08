import bpy
import os
import json


class OBJECT_OT_load_preset(bpy.types.Operator):
    bl_idname = "object.load_preset"
    bl_label = "Load Preset"

    preset_name: bpy.props.StringProperty()

    def execute(self, context):
        script_dir = os.path.dirname(os.path.realpath(__file__))
        # 从项目根目录的 presets/ 读取（operators 在子目录中）
        project_root = os.path.dirname(os.path.dirname(script_dir))
        presets_dir = os.path.join(project_root, "presets")
        preset_path = os.path.join(presets_dir, f"{self.preset_name}.json")

        if os.path.exists(preset_path):
            with open(preset_path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)

            for prop_name, bone_name in preset_data.items():
                if hasattr(context.scene, prop_name):
                    setattr(context.scene, prop_name, bone_name)

        # 自动检测上半身骨骼链
        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            from .preset_operator import auto_detect_upper_body_chain
            auto_detect_upper_body_chain(context.scene, obj)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_load_preset)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_load_preset)


if __name__ == "__main__":
    register()
