import bpy
import json

# 定义手指骨骼的属性列表
_finger_bone_props = [
    ('left_thumb_0', 'left_thumb_1', 'left_thumb_2'),
    ('left_index_1', 'left_index_2', 'left_index_3'),
    ('left_middle_1', 'left_middle_2', 'left_middle_3'),
    ('left_ring_1', 'left_ring_2', 'left_ring_3'),
    ('left_pinky_1', 'left_pinky_2', 'left_pinky_3'),
    ('right_thumb_0', 'right_thumb_1', 'right_thumb_2'),
    ('right_index_1', 'right_index_2', 'right_index_3'),
    ('right_middle_1', 'right_middle_2', 'right_middle_3'),
    ('right_ring_1', 'right_ring_2', 'right_ring_3'),
    ('right_pinky_1', 'right_pinky_2', 'right_pinky_3'),
]

# 定义左右对称手指的映射关系
_left_right_mapping = {
    'left_thumb_0': 'right_thumb_0',
    'left_index_1': 'right_index_1',
    'left_middle_1': 'right_middle_1',
    'left_ring_1': 'right_ring_1',
    'left_pinky_1': 'right_pinky_1',
    'right_thumb_0': 'left_thumb_0',
    'right_index_1': 'left_index_1',
    'right_middle_1': 'left_middle_1',
    'right_ring_1': 'left_ring_1',
    'right_pinky_1': 'left_pinky_1',
}


def auto_fill_finger_bones(scene, armature, first_prop):
    """自动填充手指骨骼链（包括对称侧）"""
    # 查找这个属性是否是指骨的第一节
    for fp, second_prop, third_prop in _finger_bone_props:
        if fp == first_prop:
            # 找到对应的手指，尝试自动填充
            mode = bpy.context.mode
            first_bone_value = getattr(scene, first_prop, "")
            
            if mode == 'EDIT_ARMATURE':
                edit_bone = armature.data.edit_bones.get(first_bone_value)
                if edit_bone and len(edit_bone.children) > 0:
                    second_bone = edit_bone.children[0].name
                    setattr(scene, second_prop, second_bone)
                    second_edit_bone = armature.data.edit_bones.get(second_bone)
                    if second_edit_bone and len(second_edit_bone.children) > 0:
                        third_bone = second_edit_bone.children[0].name
                        setattr(scene, third_prop, third_bone)
                        # 尝试填充对称侧
                        try_fill_symmetric_finger(scene, armature, first_prop, mode)
                        return True
            elif mode == 'POSE':
                pose_bone = armature.pose.bones.get(first_bone_value)
                if pose_bone and len(pose_bone.children) > 0:
                    second_bone = pose_bone.children[0].name
                    setattr(scene, second_prop, second_bone)
                    second_pose_bone = armature.pose.bones.get(second_bone)
                    if second_pose_bone and len(second_pose_bone.children) > 0:
                        third_bone = second_pose_bone.children[0].name
                        setattr(scene, third_prop, third_bone)
                        # 尝试填充对称侧
                        try_fill_symmetric_finger(scene, armature, first_prop, mode)
                        return True
            return False
    return False


def try_fill_symmetric_finger(scene, armature, first_prop, mode):
    """尝试填充对称侧的手指骨骼"""
    # 获取对称侧的第一指节属性名
    symmetric_prop = _left_right_mapping.get(first_prop)
    if not symmetric_prop:
        return False
    
    # 检查对称侧是否已经填充
    if getattr(scene, symmetric_prop, ""):
        return False  # 已经填充，跳过
    
    # 获取当前填充的第一指节骨骼名称
    first_bone_value = getattr(scene, first_prop, "")
    if not first_bone_value:
        return False
    
    # 尝试通过对称命名规则找到对称骨骼
    # 将 "左" 替换为 "右"，或将 "右" 替换为 "左"
    symmetric_bone_name = None
    if "左" in first_bone_value:
        symmetric_bone_name = first_bone_value.replace("左", "右")
    elif "右" in first_bone_value:
        symmetric_bone_name = first_bone_value.replace("右", "左")
    elif "Left" in first_bone_value or "L_" in first_bone_value:
        symmetric_bone_name = first_bone_value.replace("Left", "Right").replace("L_", "R_")
    elif "Right" in first_bone_value or "R_" in first_bone_value:
        symmetric_bone_name = first_bone_value.replace("Right", "Left").replace("R_", "L_")
    
    if not symmetric_bone_name:
        return False
    
    # 获取对称侧的第二、三节属性名
    symmetric_second_prop = symmetric_prop.replace('_0', '_1') if '_0' in symmetric_prop else symmetric_prop
    symmetric_third_prop = symmetric_prop.replace('_0', '_2') if '_0' in symmetric_prop else symmetric_prop
    
    # 检查对称骨骼是否存在于骨架中
    if mode == 'EDIT_ARMATURE':
        if symmetric_bone_name in armature.data.edit_bones:
            # 获取对称骨骼的三节指骨
            symmetric_first_bone = armature.data.edit_bones.get(symmetric_bone_name)
            if symmetric_first_bone and len(symmetric_first_bone.children) > 0:
                # 填充第一指节
                setattr(scene, symmetric_prop, symmetric_bone_name)
                # 填充第二指节
                symmetric_second_bone = symmetric_first_bone.children[0].name
                setattr(scene, symmetric_second_prop, symmetric_second_bone)
                # 填充第三指节
                symmetric_second_edit_bone = armature.data.edit_bones.get(symmetric_second_bone)
                if symmetric_second_edit_bone and len(symmetric_second_edit_bone.children) > 0:
                    symmetric_third_bone = symmetric_second_edit_bone.children[0].name
                    setattr(scene, symmetric_third_prop, symmetric_third_bone)
                    return True
    elif mode == 'POSE':
        if symmetric_bone_name in armature.pose.bones:
            # 获取对称骨骼的三节指骨
            symmetric_first_bone = armature.pose.bones.get(symmetric_bone_name)
            if symmetric_first_bone and len(symmetric_first_bone.children) > 0:
                # 填充第一指节
                setattr(scene, symmetric_prop, symmetric_bone_name)
                # 填充第二指节
                symmetric_second_bone = symmetric_first_bone.children[0].name
                setattr(scene, symmetric_second_prop, symmetric_second_bone)
                # 填充第三指节
                symmetric_second_pose_bone = armature.pose.bones.get(symmetric_second_bone)
                if symmetric_second_pose_bone and len(symmetric_second_pose_bone.children) > 0:
                    symmetric_third_bone = symmetric_second_pose_bone.children[0].name
                    setattr(scene, symmetric_third_prop, symmetric_third_bone)
                    return True
    
    return False


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
        
        # 如果是指骨的第一节，自动填充后续指节
        if auto_fill_finger_bones(scene, obj, self.bone_property):
            # 检查是否填充了对称侧
            symmetric_prop = _left_right_mapping.get(self.bone_property)
            if symmetric_prop and getattr(scene, symmetric_prop, ""):
                self.report({'INFO'}, f"已自动填充指骨链及其对称侧")
            else:
                self.report({'INFO'}, f"已自动填充指骨链")
        
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
    from ..bone_map_and_group import mmd_bone_map
    bone_list = {k: "" for k in mmd_bone_map.keys()}
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
            # 弹出错误提示窗口（包含下载按钮）
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