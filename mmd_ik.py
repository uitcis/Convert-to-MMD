import bpy
from mathutils import Vector
from math import radians

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

        # Create IK bones for left leg
        left_ik_parent = self.add_bone(edit_bones, "左足IK親", Vector((edit_bones["左ひざ"].tail.x, edit_bones["左ひざ"].tail.y, 0)), edit_bones["左ひざ"].tail, "全ての親")
        left_ik = self.add_bone(edit_bones, "左足IK", edit_bones["左ひざ"].tail, edit_bones["左ひざ"].tail + Vector((0, 0.1, 0)), "左足IK親")
        left_toe_ik = self.add_bone(edit_bones, "左つま先IK", edit_bones["左足首"].tail, edit_bones["左足首"].tail + Vector((0, 0, -0.05)), "左足IK")

        # Create IK bones for right leg
        right_ik_parent = self.add_bone(edit_bones, "右足IK親", Vector((edit_bones["右ひざ"].tail.x, edit_bones["右ひざ"].tail.y, 0)), edit_bones["右ひざ"].tail, "全ての親")
        right_ik = self.add_bone(edit_bones, "右足IK", edit_bones["右ひざ"].tail, edit_bones["右ひざ"].tail + Vector((0, 0.1, 0)), "右足IK親")
        right_toe_ik = self.add_bone(edit_bones, "右つま先IK", edit_bones["右足首"].tail, edit_bones["右足首"].tail + Vector((0, 0, -0.05)), "右足IK")

        # Switch to POSE mode
        bpy.ops.object.mode_set(mode='POSE')

        # Add IK constraint to left knee
        left_knee_ik_constraint = obj.pose.bones["左ひざ"].constraints.new(type='IK')
        left_knee_ik_constraint.name = "IK"
        left_knee_ik_constraint.target = obj
        left_knee_ik_constraint.subtarget = "左足IK"
        left_knee_ik_constraint.chain_count = 2
        left_knee_ik_constraint.iterations = 200

        # Add rotation limit constraint to left knee
        left_knee_rotation_limit_constraint = obj.pose.bones["左ひざ"].constraints.new(type='LIMIT_ROTATION')
        left_knee_rotation_limit_constraint.name = "mmd_ik_limit_override"
        left_knee_rotation_limit_constraint.use_limit_x = True
        left_knee_rotation_limit_constraint.min_x = radians(0.5)
        left_knee_rotation_limit_constraint.max_x = radians(180)
        left_knee_rotation_limit_constraint.owner_space = 'LOCAL'
        # Add Inverse Kinematics Limit X
        obj.pose.bones["左ひざ"].ik_min_x = radians(0)
        obj.pose.bones["左ひざ"].ik_max_x = radians(180)
        obj.pose.bones["左ひざ"].use_ik_limit_x = True

        # Add damped track constraint to left foot
        left_foot_damped_track_constraint = obj.pose.bones["左足首"].constraints.new(type='DAMPED_TRACK')
        left_foot_damped_track_constraint.name = "Damped Track"
        left_foot_damped_track_constraint.target = obj
        left_foot_damped_track_constraint.subtarget = "左ひざ"

        # Add IK constraint to left foot
        left_foot_ik_constraint = obj.pose.bones["左足首"].constraints.new(type='IK')
        left_foot_ik_constraint.name = "IK"
        left_foot_ik_constraint.target = obj
        left_foot_ik_constraint.subtarget = "左つま先IK"
        left_foot_ik_constraint.chain_count = 1
        left_foot_ik_constraint.iterations = 200

        # Add IK constraint to right knee
        right_knee_ik_constraint = obj.pose.bones["右ひざ"].constraints.new(type='IK')
        right_knee_ik_constraint.name = "IK"
        right_knee_ik_constraint.target = obj
        right_knee_ik_constraint.subtarget = "右足IK"
        right_knee_ik_constraint.chain_count = 2
        right_knee_ik_constraint.iterations = 200

        # Add rotation limit constraint to right knee
        right_knee_rotation_limit_constraint = obj.pose.bones["右ひざ"].constraints.new(type='LIMIT_ROTATION')
        right_knee_rotation_limit_constraint.name = "mmd_ik_limit_override"
        right_knee_rotation_limit_constraint.use_limit_x = True
        right_knee_rotation_limit_constraint.min_x = radians(0.5)
        right_knee_rotation_limit_constraint.max_x = radians(180)
        right_knee_rotation_limit_constraint.owner_space = 'LOCAL'
        # Add Inverse Kinematics Limit X
        obj.pose.bones["右ひざ"].ik_min_x = radians(0)
        obj.pose.bones["右ひざ"].ik_max_x = radians(180)
        obj.pose.bones["右ひざ"].use_ik_limit_x = True

        # Add damped track constraint to right foot
        right_foot_damped_track_constraint = obj.pose.bones["右足首"].constraints.new(type='DAMPED_TRACK')
        right_foot_damped_track_constraint.name = "Damped Track"
        right_foot_damped_track_constraint.target = obj
        right_foot_damped_track_constraint.subtarget = "右ひざ"

        # Add IK constraint to right foot
        right_foot_ik_constraint = obj.pose.bones["右足首"].constraints.new(type='IK')
        right_foot_ik_constraint.name = "IK"
        right_foot_ik_constraint.target = obj
        right_foot_ik_constraint.subtarget = "右つま先IK"
        right_foot_ik_constraint.chain_count = 1
        right_foot_ik_constraint.iterations = 200
        return {'FINISHED'}

    def add_bone(self, edit_bones, name, head_position, tail_position, parent_name):
        bone = edit_bones.new(name)
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = False
        if parent_name:
            bone.parent = edit_bones.get(parent_name)
        return bone