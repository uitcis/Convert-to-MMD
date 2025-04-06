import bpy
from mathutils import Vector
from math import radians
from . import bone_utils

# IK约束相关函数
def add_ik_constraint(bone, target, subtarget, chain_count, iterations, ik_min_x=None, ik_max_x=None, use_ik_limit_x=False, ik_min_y=0, ik_max_y=0, use_ik_limit_y=False, ik_min_z=0, ik_max_z=0, use_ik_limit_z=False):
    ik_constraint = bone.constraints.new(type='IK')
    ik_constraint.name = "IK"
    ik_constraint.target = target
    ik_constraint.subtarget = subtarget
    ik_constraint.chain_count = chain_count
    ik_constraint.iterations = iterations
    
    # 设置X轴限制
    if ik_min_x is not None:
        bone.ik_min_x = ik_min_x
    if ik_max_x is not None:
        bone.ik_max_x = ik_max_x
    bone.use_ik_limit_x = use_ik_limit_x
    
    # 设置Y轴限制
    if ik_min_y is not None:
        bone.ik_min_y = ik_min_y
    if ik_max_y is not None:
        bone.ik_max_y = ik_max_y
    bone.use_ik_limit_y = use_ik_limit_y
    
    # 设置Z轴限制
    if ik_min_z is not None:
        bone.ik_min_z = ik_min_z
    if ik_max_z is not None:
        bone.ik_max_z = ik_max_z
    bone.use_ik_limit_z = use_ik_limit_z

def add_limit_rotation_constraint(bone, influence=1, use_limit_x=False, min_x=None, max_x=None, owner_space='LOCAL'):
    limit_constraint = bone.constraints.new(type='LIMIT_ROTATION')
    limit_constraint.name = "mmd_ik_limit_override"
    limit_constraint.influence = influence
    limit_constraint.use_limit_x = use_limit_x
    limit_constraint.owner_space = owner_space
    
    if min_x is not None:
        limit_constraint.min_x = min_x
    if max_x is not None:
        limit_constraint.max_x = max_x

def add_damped_track_constraint(bone, target, subtarget, influence=0):
    damped_track_constraint = bone.constraints.new(type='DAMPED_TRACK')
    damped_track_constraint.name = "mmd_ik_target_override"
    damped_track_constraint.target = target
    damped_track_constraint.subtarget = subtarget
    damped_track_constraint.influence = influence

# IK操作类
class OBJECT_OT_add_ik(bpy.types.Operator):
    """为骨架添加MMD IK"""
    bl_idname = "object.add_mmd_ik"
    bl_label = "Add MMD IK"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones
        required_bones = ['左ひざ', '右ひざ', '左足首', '右足首', '全ての親']
        missing_bones = [name for name in required_bones if name not in edit_bones]
        if missing_bones:
            self.report({'ERROR'}, f"缺失基础骨骼: {', '.join(missing_bones)}，请先补全骨骼")
            return {'CANCELLED'}

        # IK骨骼属性定义
        IKbone_properties = {
            "左足IK親": {"head": Vector((edit_bones["左ひざ"].tail.x, edit_bones["左ひざ"].tail.y, 0)),
                       "tail": edit_bones["左ひざ"].tail, "parent": "全ての親", "use_connect": False},
            "左足ＩＫ": {"head": edit_bones["左ひざ"].tail,
                      "tail": edit_bones["左ひざ"].tail + Vector((0, 0.1, 0)), "parent": "左足IK親", "use_connect": False},
            "左つま先ＩＫ": {"head": edit_bones["左足首"].tail,
                         "tail": edit_bones["左足首"].tail + Vector((0, 0, -0.05)), "parent": "左足ＩＫ", "use_connect": False},
            "右足IK親": {"head": Vector((edit_bones["右ひざ"].tail.x, edit_bones["右ひざ"].tail.y, 0)),
                       "tail": edit_bones["右ひざ"].tail, "parent": "全ての親", "use_connect": False},
            "右足ＩＫ": {"head": edit_bones["右ひざ"].tail,
                      "tail": edit_bones["右ひざ"].tail + Vector((0, 0.1, 0)), "parent": "右足IK親", "use_connect": False},
            "右つま先ＩＫ": {"head": edit_bones["右足首"].tail,
                         "tail": edit_bones["右足首"].tail + Vector((0, 0, -0.05)), "parent": "右足ＩＫ", "use_connect": False}
        }

        # 创建IK骨骼
        for bone_name, properties in IKbone_properties.items():
            bone_utils.create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], use_connect=False, parent_name=properties["parent"], use_deform=False)
        # 切换到姿态模式
        bpy.ops.object.mode_set(mode='POSE')

        # 获取骨骼对象并添加约束
        left_hiza = obj.pose.bones["左ひざ"]
        left_kutu = obj.pose.bones["左足首"]
        right_hiza = obj.pose.bones["右ひざ"]
        right_kutu = obj.pose.bones["右足首"]

        # 为左ひざ添加 IK 和旋转限制约束
        add_ik_constraint(left_hiza, obj, "左足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True,use_ik_limit_y=True,use_ik_limit_z=True)
        add_limit_rotation_constraint(left_hiza, use_limit_x=True, min_x=radians(0.5), max_x=radians(180))
        
        add_ik_constraint(right_hiza, obj, "右足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True,use_ik_limit_y=True,use_ik_limit_z=True)
        add_limit_rotation_constraint(right_hiza, use_limit_x=True, min_x=radians(0.5), max_x=radians(180))
        
        add_ik_constraint(left_kutu, obj, "左つま先ＩＫ", 1, 200)
        add_damped_track_constraint(left_kutu, obj, "左ひざ")
        
        add_ik_constraint(right_kutu, obj, "右つま先ＩＫ", 1, 200)
        add_damped_track_constraint(right_kutu, obj, "右ひざ")

        return {'FINISHED'}