import bpy

# 存储所有属性的名称，用于后续注销
_registered_props = []

# 存储当前正在被修改的属性名
_current_updating_prop = None

# 手指第一节指骨的属性列表
_finger_first_bones = [
    'left_thumb_0', 'left_index_1', 'left_middle_1', 'left_ring_1', 'left_pinky_1',
    'right_thumb_0', 'right_index_1', 'right_middle_1', 'right_ring_1', 'right_pinky_1'
]


def register_properties(properties_dict):
    """使用字典动态注册属性。
    
    对于手指的第一节指骨，会自动添加 update 回调以支持自动填充功能。
    """
    global _registered_props
    for prop_name, prop_value in properties_dict.items():
        _registered_props.append(prop_name)
        # 对于手指的第一节指骨，添加 update 回调
        if prop_name in _finger_first_bones:
            # 创建一个带 update 回调的属性
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
