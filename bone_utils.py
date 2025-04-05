import bpy
from mathutils import Vector
from math import radians

DEFAULT_ROLL_VALUES = {
    "全ての親": 0.0, "センター": 0.0, "グルーブ": 0.0, "腰": 0.0, 
    "上半身": 0.0,"上半身2": 0.0, "首": 0.0, "頭": 0.0,
    "下半身": 0.0, "左足": 0.0, "右足": 0.0,"左ひざ": 0.0, "右ひざ": 0.0, "左足首": 0.0, "右足首": 0.0, "左足先EX": 0.0,"右足先EX": 0.0, 
    "左腕": 45.0, "左ひじ": 45.0, "左手首": 45.0,
    "右腕": 135.0, "右ひじ": 135.0, "右手首": 135.0,
    "左肩": 0.0, "右肩": 180.0
}

def create_or_update_bone(edit_bones, name, head_position, tail_position, use_connect=False, parent_name=None, use_deform=True):
    bone = edit_bones.get(name)
    if bone:
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = use_connect
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform
    else:
        bone = edit_bones.new(name)
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = use_connect
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform
    return bone


def set_roll_values(edit_bones, bone_roll_mapping):
    for bone_name, roll_value in bone_roll_mapping.items():
        if bone_name in edit_bones:
            edit_bones[bone_name].roll = radians(roll_value)