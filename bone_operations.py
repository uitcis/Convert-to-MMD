import bpy
from mathutils import Vector
from math import radians

from mathutils import Vector

def create_or_update_bone(edit_bones, name, head_position, tail_position, parent_name=None, use_deform=True):
    bone = edit_bones.get(name)
    if bone:
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = False
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform  # Set the use_deform property
    else:
        bone = edit_bones.new(name)
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = False
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform  # Set the use_deform property
    return bone

def add_ik_constraint(bone, target, subtarget, chain_count, iterations, ik_min_x=None, ik_max_x=None, use_ik_limit_x=False):
    ik_constraint = bone.constraints.new(type='IK')
    ik_constraint.name = "IK"
    ik_constraint.target = target
    ik_constraint.subtarget = subtarget
    ik_constraint.chain_count = chain_count
    ik_constraint.iterations = iterations
    if ik_min_x is not None:
        bone.ik_min_x = ik_min_x
    if ik_max_x is not None:
        bone.ik_max_x = ik_max_x
    bone.use_ik_limit_x = use_ik_limit_x

def add_limit_rotation_constraint(bone, use_limit_x=False, min_x=None, max_x=None, owner_space='LOCAL'):
    limit_constraint = bone.constraints.new(type='LIMIT_ROTATION')
    limit_constraint.name = "mmd_ik_limit_override"
    limit_constraint.use_limit_x = use_limit_x
    limit_constraint.owner_space = owner_space
    
class OBJECT_OT_complete_missing_bones(bpy.types.Operator):
    """Operator which completes missing bones for MMD format"""
    bl_idname = "object.complete_missing_bones"
    bl_label = "Complete Missing Bones"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected")
            return {'CANCELLED'}

        existing_bones = obj.pose.bones

        # Ensure we are in EDIT mode
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = obj.data.edit_bones

        # Check 上半身 bone exists and get its head position
        upper_body_bone = existing_bones.get("上半身")
        if not upper_body_bone:
            self.report({'ERROR'}, "上半身 bone does not exist")
            return {'CANCELLED'}
        
        # Disconnect 上半身 from its current parent
        if upper_body_bone.parent:
            upper_body_edit_bone = edit_bones[upper_body_bone.name]
            upper_body_edit_bone.use_connect = False
            upper_body_edit_bone.parent = None

        # Get 上半身 bone's coordinates
        upper_body_head = upper_body_bone.head.copy()

        # 基本骨のプロパティ定義
        bone_properties = {
            "全ての親": {"head": Vector((0, 0, 0)), "tail": Vector((0, 0, 0.3)), "parent": None},
            "センター": {"head": Vector((0, 0, 0.3)), "tail": Vector((0, 0, 0.6)), "parent": "全ての親"},
            "グルーブ": {"head": Vector((0, 0, 0.8)), "tail": Vector((0, 0, 0.7)), "parent": "センター"},
            "腰": {"head": upper_body_head + Vector((0, 0.1, -0.12)), "tail": upper_body_head, "parent": "グルーブ"},
            "下半身": {"head": upper_body_head, "tail": upper_body_head + Vector((0, 0, -0.15)), "parent": "腰"}
        }

        # Check and create or update bones in order
        for bone_name, properties in bone_properties.items():
            if bone_name == "下半身":
                create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=True)
            else:
                create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=False)

        # Set 上半身's parent to 腰
        if "上半身" in existing_bones:
            upper_body_edit_bone = edit_bones["上半身"]
            upper_body_edit_bone.parent = edit_bones.get("腰")
            upper_body_edit_bone.use_connect = False
            upper_body_edit_bone.roll = 0.0

        # Switch back to POSE mode after editing
        bpy.ops.object.mode_set(mode='POSE')

        # Check and call mmd_tools.convert_to_mmd_model()
        try:
            bpy.ops.mmd_tools.convert_to_mmd_model()
        except AttributeError:
            self.report({'ERROR'}, "Please install or enable the mmdtools add-on.")
            return {'CANCELLED'}

        return {'FINISHED'}
class OBJECT_OT_add_ik(bpy.types.Operator):
    """Operator which adds MMD IK to the armature"""
    bl_idname = "object.add_mmd_ik"
    bl_label = "Add MMD IK"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature object selected")
            return {'CANCELLED'}

        # Ensure we are in EDIT mode
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones

        # IK骨のプロパティ定義
        IKbone_properties = {
            "左足IK親": {"head": Vector((edit_bones["左ひざ"].tail.x, edit_bones["左ひざ"].tail.y, 0)), "tail": edit_bones["左ひざ"].tail, "parent": "全ての親"},
            "左足IK": {"head": edit_bones["左ひざ"].tail, "tail": edit_bones["左ひざ"].tail + Vector((0, 0.1, 0)), "parent": "左足IK親"},
            "左つま先IK": {"head": edit_bones["左足首"].tail, "tail": edit_bones["左足首"].tail + Vector((0, 0, -0.05)), "parent": "左足ＩＫ"},
            "右足IK親": {"head": Vector((edit_bones["右ひざ"].tail.x, edit_bones["右ひざ"].tail.y, 0)), "tail": edit_bones["右ひざ"].tail, "parent": "全ての親"},
            "右足IK": {"head": edit_bones["右ひざ"].tail, "tail": edit_bones["右ひざ"].tail + Vector((0, 0.1, 0)), "parent": "右足IK親"},
            "右つま先IK": {"head": edit_bones["右足首"].tail, "tail": edit_bones["右足首"].tail + Vector((0, 0, -0.05)), "parent": "右足ＩＫ"}
        }

        # Create or update bones using the defined properties
        for bone_name, properties in IKbone_properties.items():
            create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=False)

        # Switch to POSE mode
        bpy.ops.object.mode_set(mode='POSE')

        # Add IK constraint to left knee
        add_ik_constraint(obj.pose.bones["左ひざ"], obj, "左足IK", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True)

        # Add rotation limit constraint to left knee
        add_limit_rotation_constraint(obj.pose.bones["左ひざ"], use_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        # Add damped track constraint to left foot
        left_foot_damped_track_constraint = obj.pose.bones["左足首"].constraints.new(type='DAMPED_TRACK')
        left_foot_damped_track_constraint.name = "Damped Track"
        left_foot_damped_track_constraint.target = obj
        left_foot_damped_track_constraint.subtarget = "左ひざ"

        # Add IK constraint to left foot
        add_ik_constraint(obj.pose.bones["左足首"], obj, "左つま先IK", 1, 200)

        # Add IK constraint to right knee
        add_ik_constraint(obj.pose.bones["右ひざ"], obj, "右足IK", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True)

        # Add rotation limit constraint to right knee
        add_limit_rotation_constraint(obj.pose.bones["右ひざ"], use_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        # Add damped track constraint to right foot
        right_foot_damped_track_constraint = obj.pose.bones["右足首"].constraints.new(type='DAMPED_TRACK')
        right_foot_damped_track_constraint.name = "Damped Track"
        right_foot_damped_track_constraint.target = obj
        right_foot_damped_track_constraint.subtarget = "右ひざ"

        # Add IK constraint to right foot
        add_ik_constraint(obj.pose.bones["右足首"], obj, "右つま先IK", 1, 200)
        return {'FINISHED'}

