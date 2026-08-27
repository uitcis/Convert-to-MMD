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
    'left_toe_bone', 'right_toe_bone',
    'left_chest_bone', 'right_chest_bone'  # 胸部物理骨骼
]

_chest_physics_props = [
    'left_chest_bone', 'right_chest_bone', 'breast_parent_bone'
]


def get_chest_physics_props():
    """获取胸部物理相关属性列表"""
    return _chest_physics_props.copy()


def register_properties(properties_dict):
    """使用字典动态注册属性，带有完整的错误处理。

    对于手指的第一节指骨和其他对称骨骼，会自动添加 update 回调以支持自动填充功能。

    Args:
        properties_dict: 属性名到默认值的映射字典

    Raises:
        RuntimeError: 如果部分或全部属性注册失败

    Note:
        - 属性注册失败会抛出 RuntimeError，防止插件在不完整状态下运行
        - update 回调中的异常会被捕获并打印，不会传播到 Blender 主线程
        - 使用闭包捕获 p_name 变量，避免循环中的闭包陷阱
    """
    global _registered_props
    failed_props = []

    for prop_name, prop_value in properties_dict.items():
        try:
            _registered_props.append(prop_name)

            if prop_name in _finger_first_bones:
                def make_update_callback(p_name):
                    """创建手指骨骼的 update 回调

                    Args:
                        p_name: 属性名称（闭包捕获）
                    """
                    def callback(self, context):
                        """手指骨骼自动填充回调"""
                        global _current_updating_prop
                        _current_updating_prop = p_name
                        try:
                            from .operators.preset_operator import auto_fill_finger_bones
                            obj = context.active_object
                            if obj and obj.type == 'ARMATURE':
                                auto_fill_finger_bones(context.scene, obj, p_name)
                        except Exception as e:
                            print(f"[Convert-to-MMD] 自动填充手指骨骼失败 ({p_name}): {e}")
                    return callback

                setattr(bpy.types.Scene, prop_name,
                       bpy.props.StringProperty(default=prop_value,
                                              update=make_update_callback(prop_name)))

            elif prop_name in _symmetric_bone_props:
                def make_symmetric_update_callback(p_name):
                    """创建对称骨骼的 update 回调

                    Args:
                        p_name: 属性名称（闭包捕获）
                    """
                    def callback(self, context):
                        """对称骨骼自动填充回调"""
                        global _current_updating_prop
                        _current_updating_prop = p_name
                        try:
                            from .operators.preset_operator import try_fill_symmetric_bones
                            obj = context.active_object
                            if obj and obj.type == 'ARMATURE':
                                try_fill_symmetric_bones(context.scene, obj, p_name, context.mode)
                        except Exception as e:
                            print(f"[Convert-to-MMD] 自动填充对称骨骼失败 ({p_name}): {e}")
                    return callback

                setattr(bpy.types.Scene, prop_name,
                       bpy.props.StringProperty(default=prop_value,
                                              update=make_symmetric_update_callback(prop_name)))
            else:
                setattr(bpy.types.Scene, prop_name,
                       bpy.props.StringProperty(default=prop_value))

        except Exception as e:
            failed_props.append((prop_name, str(e)))
            print(f"[Convert-to-MMD] ❌ 属性注册失败: {prop_name} - {e}")

    if failed_props:
        raise RuntimeError(
            f"[Convert-to-MMD] 部分属性注册失败（共 {len(failed_props)} 个）：\n" +
            "\n".join(f"  - {name}: {err}" for name, err in failed_props)
        )


def unregister_properties(properties_list):
    """使用属性名列表动态注销属性。"""
    for prop_name in properties_list:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)


def get_registered_props():
    """获取所有已注册的属性名称列表。"""
    return _registered_props.copy()
