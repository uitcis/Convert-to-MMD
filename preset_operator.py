import bpy
import json

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

class OBJECT_OT_use_mmd_tools_convert(bpy.types.Operator):
    """调用mmdtools进行格式转换"""
    bl_idname = "object.use_mmd_tools_convert"
    bl_label = "Convert to MMD Model"
    bl_description = "使用mmd_tools插件转换模型格式（需要先安装mmd_tools插件）"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        # 保存当前模式并切换到OBJECT模式
        current_mode = context.mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            # 调用mmd_tools的转换功能
            bpy.ops.mmd_tools.convert_to_mmd_model()
        except AttributeError as e:
            # 弹出错误提示窗口
            self.report({'ERROR'}, "mmd_tools插件未安装")
            bpy.context.window_manager.popup_menu(
                self.draw_error_menu,
                title="MMD Tools未安装",
                icon='ERROR'
            )
            return {'CANCELLED'}

        # 恢复原始选择状态
        context.view_layer.objects.active = obj
        obj.select_set(True)
        return {'FINISHED'}

    def draw_error_menu(self, menu, context):
        layout = menu.layout
        layout.label(text="mmd_tools 插件未安装", icon='ERROR')
        layout.separator()
        layout.operator(
            "wm.url_open",
            text="前往下载页面",
            icon='URL'
        ).url = "https://extensions.blender.org/add-ons/mmd-tools/"
        layout.operator(
            "wm.url_open",
            text="查看使用文档",
            icon='HELP'
        ).url = "https://mmd-blender.fandom.com/wiki/MMD_Tools_Documentation"
        obj.select_set(True)