import bpy
import json

from .. import bone_utils

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
# 对称字典
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
    (' L', ' R')
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
    # 胸部物理骨骼
    'left_chest_bone': 'right_chest_bone',
    'right_chest_bone': 'left_chest_bone',
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
    
    symmetric_bone = None
    if mode == 'EDIT_ARMATURE':
        if symmetric_bone_name not in armature.data.edit_bones:
            return False
        symmetric_bone = armature.data.edit_bones.get(symmetric_bone_name)
    elif mode == 'POSE':
        if symmetric_bone_name not in armature.pose.bones:
            return False
        symmetric_bone = armature.pose.bones.get(symmetric_bone_name)
    else:
        # 非编辑/姿态模式下不进行对称填充
        return False

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
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        mode = context.mode

        if mode == 'POSE':
            selected_bones = [bone.name for bone in context.selected_pose_bones] if context.selected_pose_bones else []
        elif mode == 'EDIT_ARMATURE':
            selected_bones = [bone.name for bone in obj.data.edit_bones if bone.select]
        else:
            self.report({'ERROR'}, "请在姿态模式或编辑模式下选择骨骼")
            return {'CANCELLED'}

        if not selected_bones:
            self.report({'ERROR'}, "未选择骨骼")
            return {'CANCELLED'}

        # 将第一个选定的骨骼名称先记下来，位置校验通过后才写入字段
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
                self.report({'ERROR'}, f"{error_msg}，请重新选择")
                print(f"已拒绝写入：{error_msg}")
                return {'CANCELLED'}

        setattr(scene, self.bone_property, current_bone_name)
        
        # 如果是指骨的第一节，自动填充后续指节
        if auto_fill_finger_bones(scene, obj, self.bone_property):
            # 检查是否填充了对称侧
            symmetric_prop = _left_right_mapping.get(self.bone_property)
            if symmetric_prop and getattr(scene, symmetric_prop, ""):
                self.report({'INFO'}, f"已自动填充指骨链及其对称侧")
            else:
                self.report({'INFO'}, f"已自动填充指骨链")
        
        # 填充上半身或首骨骼时，自动检测上半身骨骼链
        if self.bone_property in ('upper_body_bone', 'neck_bone'):
            auto_detect_upper_body_chain(scene, obj)
        
        return {'FINISHED'}


class OBJECT_OT_export_preset(bpy.types.Operator):
    """导出当前骨骼配置为预设"""
    bl_idname = "object.export_preset"
    bl_label = "Export Preset"
    filepath : bpy.props.StringProperty(subtype="FILE_PATH")# type: ignore
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})  # type: ignore[assignment]

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
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})  # type: ignore[assignment]

    def execute(self, context):
        scene = context.scene
        try:
            with open(self.filepath, 'r') as file:
                preset = json.load(file)
        except Exception as e:
            self.report({'ERROR'}, f"加载预设失败：{str(e)}")
            return {'CANCELLED'}

        if not isinstance(preset, dict):
            self.report({'ERROR'}, "预设文件格式错误：顶层必须是 JSON 对象")
            return {'CANCELLED'}

        known_props = set(get_bones_list())
        imported = 0
        unknown_props = []
        invalid_values = []

        for prop_name, value in preset.items():
            if prop_name not in known_props:
                unknown_props.append(prop_name)
                continue
            if not isinstance(value, str):
                invalid_values.append(prop_name)
                continue
            setattr(scene, prop_name, value)
            imported += 1

        message = f"已从 {self.filepath} 导入 {imported} 项骨骼配置"
        if unknown_props:
            message += f"；忽略 {len(unknown_props)} 个未知字段"
        if invalid_values:
            message += (f"；忽略 {len(invalid_values)} 个非字符串值: "
                        f"{', '.join(invalid_values[:5])}")
        self.report({'WARNING'} if (unknown_props or invalid_values) else {'INFO'}, message)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
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
    # 添加胸部物理相关属性
    bone_list['breast_parent_bone'] = ""
    return bone_list


def get_upper_body_chain_props():
    """获取上半身骨骼链属性名称列表（从上半身2开始）"""
    return ['upper_body2_bone', 'upper_body3_bone', 'upper_body4_bone', 'upper_body5_bone']


def auto_detect_upper_body_chain(scene, armature):
    """根据上半身骨骼和首骨骼自动检测中间的骨骼链
    
    从首骨骼开始沿 parent 链向上查找，直到找到上半身骨骼，
    将中间的所有骨骼依次设置为 upper_body2_bone, upper_body3_bone, ...
    """
    upper_body_name = getattr(scene, "upper_body_bone", "")
    neck_name = getattr(scene, "neck_bone", "")
    
    if not upper_body_name or not neck_name:
        return False
    
    if armature.type != 'ARMATURE':
        return False
    
    bones = armature.data.bones
    upper_body = bones.get(upper_body_name)
    neck = bones.get(neck_name)
    
    if not upper_body or not neck:
        return False
    
    chain = []
    current = neck.parent
    while current:
        if current.name == upper_body_name:
            break
        chain.append(current.name)
        current = current.parent
    
    if not current or current.name != upper_body_name:
        return False
    
    chain.reverse()
    
    prop_names = get_upper_body_chain_props()
    for i, bone_name in enumerate(chain):
        if i < len(prop_names):
            setattr(scene, prop_names[i], bone_name)
    
    for i in range(len(chain), len(prop_names)):
        setattr(scene, prop_names[i], "")
    
    return len(chain) > 0


class OBJECT_OT_use_mmd_tools_convert(bpy.types.Operator):
    """调用mmdtools进行格式转换"""
    bl_idname = "object.use_mmd_tools_convert"
    bl_label = "Convert to MMD Model"
    bl_description = "使用mmd_tools插件转换模型格式（需要先安装mmd_tools插件）"

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        # mmd_tools 转换需要在物体模式下执行
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # “保留原材质”无法通过 convert_material_nodes=False 实现：mmd_tools 仍会
        # 删除 EMISSION/BSDF 节点，却不建立 mmd_shader，结果材质全黑。
        # 因此这里在转换前整体备份材质，转换完成后再换回，只保留模型结构转换。
        preserve = bool(getattr(context.scene, "preserve_original_materials", False))
        backups = self._backup_materials(obj) if preserve else []

        try:
            # 必须转换材质节点：mmd_tools 会把原有的 EMISSION/BSDF 节点替换成 mmd_shader，
            # 关掉该选项时旧材质节点已被移除、新的 mmd_shader 又不会建立，
            # 输出材质 Surface 无连接，渲染结果全黑。
            bpy.ops.mmd_tools.convert_to_mmd_model(
                convert_material_nodes=True
            )
        except (TypeError, AttributeError):
            try:
                bpy.ops.mmd_tools.convert_to_mmd_model()
            except (TypeError, AttributeError):
                self._discard_material_backups(backups)
                bpy.context.window_manager.popup_menu(
                    self.draw_error_menu,
                    title="MMD Tools 未安装",
                    icon='ERROR'
                )
                return {'CANCELLED'}

        if backups:
            self._restore_materials(backups)

        # 恢复原始选择状态
        context.view_layer.objects.active = obj
        obj.select_set(True)
        return {'FINISHED'}

    @staticmethod
    def _model_meshes(armature):
        """遍历绑定到该骨架的网格对象（转换会把网格挂到骨架下）。"""
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type != 'MESH':
                continue
            if any(mod.type == 'ARMATURE' and mod.object == armature
                   for mod in mesh_obj.modifiers):
                yield mesh_obj

    @classmethod
    def _backup_materials(cls, armature):
        """转换前备份模型网格上的材质（含节点树副本）。

        Returns:
            list: [(转换前材质, 原名, 材质副本)]
        """
        backups = []
        for mesh_obj in cls._model_meshes(armature):
            for slot in mesh_obj.material_slots:
                mat = slot.material
                if mat is None or any(item[0] == mat for item in backups):
                    continue
                backups.append((mat, mat.name, mat.copy()))
        return backups

    @classmethod
    def _restore_materials(cls, backups):
        """转换后把备份材质换回所有使用它的网格，并清理转换产生的材质。

        注意：不能把转换后的 mmd_material 参数复制回备份材质——mmd_tools 的
        参数 setter 会触发节点更新回调，把 mmd_shader 节点重新建到备份节点树里。
        因此备份材质的 MMD 参数保持转换前的值（从 PMX 导入的模型本来就是正确的）。
        """
        # 先让转换后的材质让出原名，再把备份材质改回原名，保证材质名不变
        for mat, name, _ in backups:
            if mat.name == name:
                mat.name = name + "_mmd_converted"
        for _, name, saved in backups:
            saved.name = name

        # 所有网格槽位都换回备份副本：材质可能被模型之外的网格共享，
        # 只换模型网格会留下已转换的材质，观感也不一致。
        saved_by_mat = {mat: saved for mat, _, saved in backups}
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type != 'MESH':
                continue
            for slot in mesh_obj.material_slots:
                saved = saved_by_mat.get(slot.material)
                if saved is not None:
                    slot.material = saved

        # 转换后的材质若已无人使用（或只剩 fake user），直接移除，避免留下废弃数据
        for mat, _, _ in backups:
            if mat.users == 0 or (mat.use_fake_user and mat.users == 1):
                bpy.data.materials.remove(mat)

    @staticmethod
    def _discard_material_backups(backups):
        """转换失败时清理未被使用的材质副本。"""
        for _, _, saved in backups:
            if saved.users == 0:
                bpy.data.materials.remove(saved)

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


class OBJECT_OT_clear_bone_selection(bpy.types.Operator):
    """清空所有骨骼选择框中的内容"""
    bl_idname = "object.clear_bone_selection"
    bl_label = "清空骨骼选择"
    bl_description = "清空所有骨骼选择框中的内容"

    def execute(self, context):
        scene = context.scene
        bone_props = get_bones_list()
        for prop_name in bone_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, "")
        self.report({'INFO'}, "已清空所有骨骼选择")
        return {'FINISHED'}