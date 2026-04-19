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

# 定义对称骨骼名称替换规则（按顺序匹配，先匹配先替换）
# 格式：(原始字符串, 替换字符串)
_symmetric_bone_rules = [

    ('Left', 'Right'),
    ('Right', 'Left'),
    ('L_', 'R_'),
    ('R_', 'L_'),
    ('-L', '-R'),
    ('-R', '-L'),
    ('.L', '.R'),
    ('.R', '.L'),
    ('_L', '_R'),
    ('_R', '_L'),
    ('左', '右'),
    ('右', '左'),
    # 可以在这里添加更多规则，例如：
    # ('left_', 'right_'),
    # ('right_', 'left_'),
]

# 定义左右对称骨骼的映射关系（包含所有对称骨骼）
_left_right_mapping = {
    # 手指骨骼
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
    # 身体对称骨骼
    'left_eye_bone': 'right_eye_bone',
    'right_eye_bone': 'left_eye_bone',
    'left_shoulder_bone': 'right_shoulder_bone',
    'right_shoulder_bone': 'left_shoulder_bone',
    'left_upper_arm_bone': 'right_upper_arm_bone',
    'right_upper_arm_bone': 'left_upper_arm_bone',
    'left_lower_arm_bone': 'right_lower_arm_bone',
    'right_lower_arm_bone': 'left_lower_arm_bone',
    'left_hand_bone': 'right_hand_bone',
    'right_hand_bone': 'left_hand_bone',
    'left_thigh_bone': 'right_thigh_bone',
    'right_thigh_bone': 'left_thigh_bone',
    'left_calf_bone': 'right_calf_bone',
    'right_calf_bone': 'left_calf_bone',
    'left_foot_bone': 'right_foot_bone',
    'right_foot_bone': 'left_foot_bone',
    'left_toe_bone': 'right_toe_bone',
    'right_toe_bone': 'left_toe_bone',
}


def auto_fill_finger_bones(scene, armature, first_prop):
    """自动填充手指骨骼链（包括对称侧）"""
    for fp, second_prop, third_prop in _finger_bone_props:
        if fp == first_prop:
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
                        try_fill_symmetric_bones(scene, armature, first_prop, mode)
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
                        try_fill_symmetric_bones(scene, armature, first_prop, mode)
                        return True
            return False
    return False


def try_fill_symmetric_bones(scene, armature, first_prop, mode):
    """尝试填充对称侧的骨骼（包括手指和其他对称骨骼）"""
    symmetric_prop = _left_right_mapping.get(first_prop)
    if not symmetric_prop:
        return False
    
    if getattr(scene, symmetric_prop, ""):
        return False
    
    first_bone_value = getattr(scene, first_prop, "")
    if not first_bone_value:
        return False
    
    symmetric_bone_name = None
    for old_str, new_str in _symmetric_bone_rules:
        if old_str in first_bone_value:
            symmetric_bone_name = first_bone_value.replace(old_str, new_str)
            break
    
    if not symmetric_bone_name:
        return False
    
    if mode == 'EDIT_ARMATURE':
        if symmetric_bone_name not in armature.data.edit_bones:
            return False
        symmetric_bone = armature.data.edit_bones.get(symmetric_bone_name)
    elif mode == 'POSE':
        if symmetric_bone_name not in armature.pose.bones:
            return False
        symmetric_bone = armature.pose.bones.get(symmetric_bone_name)
    
    if not symmetric_bone:
        return False
    
    setattr(scene, symmetric_prop, symmetric_bone_name)
    
    if '_0' in first_prop or '_1' in first_prop or '_2' in first_prop:
        fill_symmetric_finger_chain(scene, armature, first_prop, symmetric_prop, symmetric_bone, mode)
    
    return True


def fill_symmetric_finger_chain(scene, armature, first_prop, symmetric_prop, symmetric_bone, mode):
    if '_0' in symmetric_prop:
        symmetric_second_prop = symmetric_prop.replace('_0', '_1')
        symmetric_third_prop = symmetric_prop.replace('_0', '_2')
    elif '_1' in symmetric_prop:
        symmetric_second_prop = symmetric_prop.replace('_1', '_2')
        symmetric_third_prop = symmetric_prop.replace('_1', '_3')
    else:
        symmetric_second_prop = symmetric_prop
        symmetric_third_prop = symmetric_prop
    
    if symmetric_bone and len(symmetric_bone.children) > 0:
        setattr(scene, symmetric_prop, symmetric_bone.name)
        
        symmetric_second_bone = symmetric_bone.children[0].name
        setattr(scene, symmetric_second_prop, symmetric_second_bone)
        
        if mode == 'EDIT_ARMATURE':
            symmetric_second_edit_bone = armature.data.edit_bones.get(symmetric_second_bone)
            if symmetric_second_edit_bone and len(symmetric_second_edit_bone.children) > 0:
                symmetric_third_bone = symmetric_second_edit_bone.children[0].name
                setattr(scene, symmetric_third_prop, symmetric_third_bone)
        elif mode == 'POSE':
            symmetric_second_pose_bone = armature.pose.bones.get(symmetric_second_bone)
            if symmetric_second_pose_bone and len(symmetric_second_pose_bone.children) > 0:
                symmetric_third_bone = symmetric_second_pose_bone.children[0].name
                setattr(scene, symmetric_third_prop, symmetric_third_bone)


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
        current_bone_name = selected_bones[0]
        
        # 检查是否为左右对称骨骼属性，如果是则检测位置
        print(f"\n当前属性：{self.bone_property}")
        print(f"是否在映射中：{self.bone_property in _left_right_mapping}")
        
        if self.bone_property in _left_right_mapping:
            # 检测当前骨骼的位置是否正确
            is_left = self.bone_property.startswith('left_')
            bone_side = "左侧" if is_left else "右侧"
            print(f"骨骼类型：{bone_side}骨骼")
            
            is_correct, error_msg = check_single_bone_position(obj, current_bone_name, is_left, mode)
            print(f"检测结果：is_correct={is_correct}, error_msg={error_msg}")
            if not is_correct:
                self.report({'WARNING'}, error_msg)
                print(f"已发送警告：{error_msg}")
        
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

def check_single_bone_position(armature, bone_name, is_left, mode):
    """检测单个骨骼的位置是否正确（相对于骨架原点，使用局部坐标）
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼名称
        is_left: 是否为左侧骨骼（True=左侧，False=右侧）
        mode: 当前模式（'EDIT_ARMATURE' 或 'POSE'）
    
    Returns:
        tuple: (is_correct, error_message)
            is_correct: 布尔值，表示位置是否正确
            error_message: 错误信息，如果位置正确则为空字符串
    """
    print(f"\n=== 检测单个骨骼位置 ===")
    print(f"模式：{mode}")
    print(f"骨骼名称：{bone_name}")
    print(f"是否为左侧：{is_left}")
    
    if mode == 'EDIT_ARMATURE':
        bone = armature.data.edit_bones.get(bone_name)
    elif mode == 'POSE':
        bone = armature.pose.bones.get(bone_name)
    else:
        return True, ""
    
    if not bone:
        return True, ""
    
    # 获取骨骼的头部位置（局部坐标，相对于骨架原点）
    if hasattr(bone, 'head'):
        bone_pos = bone.head
    else:
        bone_pos = bone.head
    
    # 使用局部坐标的 X 值（骨架原点为 0）
    bone_x = bone_pos[0]
    
    print(f"骨骼局部坐标 X: {bone_x:.2f}")
    
    # 检测位置是否正确
    # 左侧骨骼的 X 坐标应该大于 0，右侧骨骼的 X 坐标应该小于 0
    is_correct = True
    error_msg = ""
    
    if is_left:
        # 左侧骨骼应该在骨架中心右边（X 值为正）
        if bone_x <= 0:
            error_msg = f"警告：你选择的骨骼可能是右侧骨骼（X={bone_x:.2f} 应为正值）"
            is_correct = False
        else:
            print("骨骼位置正确（左侧）")
    else:
        # 右侧骨骼应该在骨架中心左边（X 值为负）
        if bone_x >= 0:
            error_msg = f"警告：你选择的骨骼可能是左侧骨骼（X={bone_x:.2f} 应为负值）"
            is_correct = False
        else:
            print("骨骼位置正确（右侧）")
    
    if not is_correct:
        print(error_msg)
    
    return is_correct, error_msg


def check_bone_position_direction(armature, left_bone_name, right_bone_name, mode):
    """检测左右骨骼的位置是否在正确的方向（相对于骨架中心）
    
    Args:
        armature: 骨架对象
        left_bone_name: 左侧骨骼名称
        right_bone_name: 右侧骨骼名称
        mode: 当前模式（'EDIT_ARMATURE' 或 'POSE'）
    
    Returns:
        tuple: (is_correct, error_message)
            is_correct: 布尔值，表示位置是否正确
            error_message: 错误信息，如果位置正确则为空字符串
    """
    print(f"\n=== 开始检测骨骼位置 ===")
    print(f"模式：{mode}")
    print(f"左侧骨骼：{left_bone_name}")
    print(f"右侧骨骼：{right_bone_name}")
    
    if mode == 'EDIT_ARMATURE':
        left_bone = armature.data.edit_bones.get(left_bone_name)
        right_bone = armature.data.edit_bones.get(right_bone_name)
    elif mode == 'POSE':
        left_bone = armature.pose.bones.get(left_bone_name)
        right_bone = armature.pose.bones.get(right_bone_name)
    else:
        return True, ""
    
    if not left_bone or not right_bone:
        return True, ""
    
    # 获取骨骼的头部位置（局部坐标，相对于骨架）
    if hasattr(left_bone, 'head'):
        left_pos = left_bone.head
        right_pos = right_bone.head
    else:
        left_pos = left_bone.head
        right_pos = right_bone.head
    
    # 获取骨架中心位置（世界坐标）
    armature_center_x = armature.location[0]
    
    # 获取骨骼的世界坐标位置
    if mode == 'EDIT_ARMATURE':
        # 编辑模式下，需要将局部坐标转换到世界坐标
        left_world_pos = armature.matrix_world @ left_pos
        right_world_pos = armature.matrix_world @ right_pos
        left_x = left_world_pos[0]
        right_x = right_world_pos[0]
    else:
        # 姿态模式下，需要将骨骼头部位置转换到世界坐标
        left_world_pos = armature.matrix_world @ left_bone.head
        right_world_pos = armature.matrix_world @ right_bone.head
        left_x = left_world_pos[0]
        right_x = right_world_pos[0]
    
    print(f"骨架中心 X: {armature_center_x:.2f}")
    print(f"骨骼世界坐标：左侧 '{left_bone_name}' X={left_x:.2f}, 右侧 '{right_bone_name}' X={right_x:.2f}")
    
    # 检测左右位置是否正确
    # 左侧骨骼的 X 坐标应该小于骨架中心，右侧骨骼的 X 坐标应该大于骨架中心
    is_correct = True
    errors = []
    
    if left_x >= armature_center_x:
        errors.append(f"左侧骨骼 '{left_bone_name}' X={left_x:.2f}（应小于骨架中心 X={armature_center_x:.2f}）")
        is_correct = False
    
    if right_x <= armature_center_x:
        errors.append(f"右侧骨骼 '{right_bone_name}' X={right_x:.2f}（应大于骨架中心 X={armature_center_x:.2f}）")
        is_correct = False
    
    error_msg = ""
    if not is_correct:
        error_msg = "警告：骨骼位置错误 - " + "，".join(errors)
        print(error_msg)
    else:
        print("骨骼位置正确")
    
    return is_correct, error_msg


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