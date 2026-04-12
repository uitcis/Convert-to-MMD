import bpy

_registered_props = []
_current_updating_prop = None

_finger_first_bones = [
    'left_thumb_0', 'left_index_1', 'left_middle_1', 'left_ring_1', 'left_pinky_1',
    'right_thumb_0', 'right_index_1', 'right_middle_1', 'right_ring_1', 'right_pinky_1'
]

_symmetric_bone_props = [
    'left_eye_bone', 'right_eye_bone',
    'left_shoulder_bone', 'right_shoulder_bone',
    'left_upper_arm_bone', 'right_upper_arm_bone',
    'left_lower_arm_bone', 'right_lower_arm_bone',
    'left_hand_bone', 'right_hand_bone',
    'left_thigh_bone', 'right_thigh_bone',
    'left_calf_bone', 'right_calf_bone',
    'left_foot_bone', 'right_foot_bone',
    'left_toe_bone', 'right_toe_bone'
]


def register_properties(properties_dict):
    """使用字典动态注册属性。
    
    对于手指的第一节指骨和其他对称骨骼，会自动添加 update 回调以支持自动填充功能。
    """
    global _registered_props
    for prop_name, prop_value in properties_dict.items():
        _registered_props.append(prop_name)
        if prop_name in _finger_first_bones:
            def make_update_callback(p_name):
                def callback(self, context):
                    global _current_updating_prop
                    _current_updating_prop = p_name
                    from .operators.preset_operator import auto_fill_finger_bones
                    obj = context.active_object
                    if obj and obj.type == 'ARMATURE':
                        auto_fill_finger_bones(context.scene, obj, p_name)
                return callback
            setattr(bpy.types.Scene, prop_name, bpy.props.StringProperty(default=prop_value, update=make_update_callback(prop_name)))
        elif prop_name in _symmetric_bone_props:
            def make_symmetric_update_callback(p_name):
                def callback(self, context):
                    global _current_updating_prop
                    _current_updating_prop = p_name
                    from .operators.preset_operator import try_fill_symmetric_bones
                    obj = context.active_object
                    if obj and obj.type == 'ARMATURE':
                        try_fill_symmetric_bones(context.scene, obj, p_name, context.mode)
                return callback
            setattr(bpy.types.Scene, prop_name, bpy.props.StringProperty(default=prop_value, update=make_symmetric_update_callback(prop_name)))
        else:
            setattr(bpy.types.Scene, prop_name, bpy.props.StringProperty(default=prop_value))


def unregister_properties(properties_list):
    """使用属性名列表动态注销属性。"""
    for prop_name in properties_list:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)


def get_registered_props():
    """获取所有已注册的属性名称列表。"""
    return _registered_props.copy()
