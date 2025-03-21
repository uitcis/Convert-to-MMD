import bpy
from mathutils import Vector
from math import radians
from . import bone_mapping  # 新增导入语句

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
    
    # Set X axis limits
    if ik_min_x is not None:
        bone.ik_min_x = ik_min_x
    if ik_max_x is not None:
        bone.ik_max_x = ik_max_x
    bone.use_ik_limit_x = use_ik_limit_x
    
    # Set Y axis limits to 0
    bone.ik_min_y = 0
    bone.ik_max_y = 0
    bone.use_ik_limit_y = True
    
    # Set Z axis limits to 0
    bone.ik_min_z = 0
    bone.ik_max_z = 0
    bone.use_ik_limit_z = True

def add_limit_rotation_constraint(bone, use_limit_x=False, min_x=None, max_x=None, owner_space='LOCAL'):
    limit_constraint = bone.constraints.new(type='LIMIT_ROTATION')
    limit_constraint.name = "mmd_ik_limit_override"
    limit_constraint.use_limit_x = use_limit_x
    limit_constraint.owner_space = owner_space
    if min_x is not None:
        limit_constraint.min_x = min_x
    if max_x is not None:
        limit_constraint.max_x = max_x

def add_damped_track_constraint(bone, target, subtarget):
    damped_track_constraint = bone.constraints.new(type='DAMPED_TRACK')
    damped_track_constraint.name = "Damped Track"
    damped_track_constraint.target = target
    damped_track_constraint.subtarget = subtarget

def add_ik_and_limit_rotation_constraints(bone, target, subtarget, chain_count, iterations, ik_min_x=None, ik_max_x=None, use_ik_limit_x=False, min_x=None, max_x=None):
    add_ik_constraint(bone, target, subtarget, chain_count, iterations, ik_min_x, ik_max_x, use_ik_limit_x)
    add_limit_rotation_constraint(bone, use_ik_limit_x, min_x, max_x)  # 修改 use_limit_x 为 use_ik_limit_x

def add_ik_and_damped_track_constraints(bone, target, subtarget, chain_count, iterations, ik_min_x=None, ik_max_x=None, use_ik_limit_x=False, min_x=None, max_x=None, damped_track_subtarget=None):
    add_ik_and_limit_rotation_constraints(bone, target, subtarget, chain_count, iterations, ik_min_x, ik_max_x, use_ik_limit_x, min_x, max_x)
    if damped_track_subtarget:
        add_damped_track_constraint(bone, target, damped_track_subtarget)

class OBJECT_OT_rename_to_mmd(bpy.types.Operator):
    """Operator which renames selected bones to MMD format"""
    bl_idname = "object.rename_to_mmd"
    bl_label = "Rename to MMD"

    mmd_bone_mapping = bone_mapping.mmd_bone_mapping  # 使用导入的bone_mapping模块

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        for prop_name, new_name in self.mmd_bone_mapping.items():
            bone_name = getattr(scene, prop_name, None)
            if bone_name:
                bone = obj.pose.bones.get(bone_name)
                if bone:
                    # 检查骨骼是否已经重命名为MMD格式名称
                    if bone.name != new_name:
                        bone.name = new_name
                        # 更新场景中的骨骼属性值
                        setattr(scene, prop_name, new_name)
                    else:
                        self.report({'INFO'}, f"骨骼 '{bone_name}' 已经重命名为 {new_name}")
                else:
                    self.report({'WARNING'}, f"未找到骨骼 '{bone_name}' 以重命名为 {new_name}")

        # 打开骨骼名称显示
        bpy.context.object.data.show_names = True

        return {'FINISHED'}

    def rename_finger_bone(self, context, obj, scene, base_finger_name, segment):
        for side in ["left", "right"]:
            prop_name = f"{side}_{base_finger_name}_{segment}"
            if prop_name in self.mmd_bone_mapping:
                new_name = self.mmd_bone_mapping.get(prop_name)
                bone_name = getattr(scene, prop_name, None)
                if bone_name:
                    bone = obj.pose.bones.get(bone_name)
                    if bone:
                        # Check if the bone has already been renamed to the MMD format name
                        if bone.name != new_name:
                            bone.name = new_name
                            # Update the bone property value in the scene
                            setattr(scene, prop_name, new_name)
                        else:
                            self.report({'INFO'}, f"Bone '{bone_name}' is already renamed to {new_name}")
                    else:
                        self.report({'WARNING'}, f"Bone '{bone_name}' not found for renaming to {new_name}")

class OBJECT_OT_complete_missing_bones(bpy.types.Operator):
    """Operator which completes missing bones for MMD format"""
    bl_idname = "object.complete_missing_bones"
    bl_label = "Complete Missing Bones"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架")
            return {'CANCELLED'}

        # 确保当前处于编辑模式 (EDIT mode)
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = obj.data.edit_bones
        # 获取需要修改的骨骼
        left_foot_bone = edit_bones.get("左足")
        right_foot_bone = edit_bones.get("右足")
        upper_body_bone = edit_bones.get("上半身")
        lower_body_bone = edit_bones.get("下半身")
        # 清除 左足 和 右足 骨骼的父级
        if left_foot_bone:
            left_foot_bone.use_connect = False
            left_foot_bone.parent = None
        if right_foot_bone:
            right_foot_bone.use_connect = False
            right_foot_bone.parent = None
        # 清除 上半身 骨骼的父级
        if upper_body_bone and upper_body_bone.parent:
            upper_body_bone.use_connect = False
            upper_body_bone.parent = None
        # 清除 下半身 骨骼的父级
        if lower_body_bone and lower_body_bone.parent:
            lower_body_bone.use_connect = False
            lower_body_bone.parent = None
        # 确认上半身骨骼存在
        if not upper_body_bone:
            self.report({'ERROR'}, "上半身骨骼不存在")
            return {'CANCELLED'}
        # 获取 上半身 骨骼的坐标
        upper_body_head = upper_body_bone.head.copy()

        # 定义基本骨骼的属性
        bone_properties = {
            "全ての親": {"head": Vector((0, 0, 0)), "tail": Vector((0, 0, 0.3)), "parent": None},
            "センター": {"head": Vector((0, 0, 0.3)), "tail": Vector((0, 0, 0.6)), "parent": "全ての親"},
            "グルーブ": {"head": Vector((0, 0, 0.8)), "tail": Vector((0, 0, 0.7)), "parent": "センター"},
            "腰": {"head": upper_body_head + Vector((0, 0.1, -0.12)), "tail": upper_body_head, "parent": "グルーブ"},
            "下半身": {"head": upper_body_head, "tail": upper_body_head + Vector((0, 0, -0.15)), "parent": "腰"}
        }

        # 按顺序检查并创建或更新骨骼
        for bone_name, properties in bone_properties.items():
            if bone_name == "下半身":
                create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=True)
            else:
                create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=False)
        
        # 将 上半身 骨骼の父骨骼设置为 腰
        if "上半身" in edit_bones:
            upper_body_bone.parent = edit_bones.get("腰")
            upper_body_bone.use_connect = False
            

        # 将 左足 和 右足 骨骼の父级设置为 下半身
        if left_foot_bone:
            left_foot_bone.parent = edit_bones.get("下半身")
            left_foot_bone.use_connect = False
        if right_foot_bone:
            right_foot_bone.parent = edit_bones.get("下半身")
            right_foot_bone.use_connect = False

        def set_roll_values(edit_bones, bone_roll_mapping):
            """
            根据骨骼名称和对应的 roll 値设置骨骼的 roll 属性。
            
            :param edit_bones: 骨骼字典，键为骨骼名称，値为骨骼对象。
            :param bone_roll_mapping: 字典，键为骨骼名称，値为对应的 roll 値（度数）。
            """
            for bone_name, roll_value in bone_roll_mapping.items():
                if bone_name in edit_bones:
                    edit_bones[bone_name].roll = radians(roll_value)  # 将度数转换为弧度
                else:
                    print(f"警告: 骨骼 '{bone_name}' 未在 edit_bones 中找到。")
    
        # 定义骨骼名称和对应的 roll 値
        bone_roll_mapping = {
            "全ての親": 0.0, "センター": 0.0, "グルーブ": 0.0, "腰": 0.0, 
            "上半身": 0.0,"上半身2": 0.0, "首": 0.0, "頭": 0.0,
            "下半身": 0.0, "左足": 0.0, "右足": 0.0,"左ひざ": 0.0, "右ひざ": 0.0, "左足首": 0.0, "右足首": 0.0, "左足先EX": 0.0,"右足先EX": 0.0, 
            "左腕": 45.0, "左ひじ": 45.0, "左手首": 45.0,
            "右腕": 135.0, "右ひじ": 135.0, "右手首": 135.0,
            "左肩": 0.0, "右肩": 180.0
        }
    
        # 调用函数设置 roll 値
        set_roll_values(edit_bones, bone_roll_mapping)               
        # 编辑完成后切换回 POSE 模式
        bpy.ops.object.mode_set(mode='POSE')

        # 检查并调用 mmd_tools.convert_to_mmd_model()
        try:
            bpy.ops.mmd_tools.convert_to_mmd_model()
        except AttributeError:
            self.report({'ERROR'}, "请安装或启用 mmdtools 插件。")
            return {'CANCELLED'}

        # 自动选择之前的骨架
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        return {'FINISHED'}

class OBJECT_OT_add_ik(bpy.types.Operator):
    """Operator which adds MMD IK to the armature"""
    bl_idname = "object.add_mmd_ik"
    bl_label = "Add MMD IK"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        # 确保当前处于编辑模式 (EDIT mode)
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones

        # 定义 IK 骨骼的属性
        IKbone_properties = {
            "左足IK親": {"head": Vector((edit_bones["左ひざ"].tail.x, edit_bones["左ひざ"].tail.y, 0)), "tail": edit_bones["左ひざ"].tail, "parent": "全ての親"},
            "左足ＩＫ": {"head": edit_bones["左ひざ"].tail, "tail": edit_bones["左ひざ"].tail + Vector((0, 0.1, 0)), "parent": "左足IK親"},
            "左つま先IK": {"head": edit_bones["左足首"].tail, "tail": edit_bones["左足首"].tail + Vector((0, 0, -0.05)), "parent": "左足ＩＫ"},
            "右足IK親": {"head": Vector((edit_bones["右ひざ"].tail.x, edit_bones["右ひざ"].tail.y, 0)), "tail": edit_bones["右ひざ"].tail, "parent": "全ての親"},
            "右足ＩＫ": {"head": edit_bones["右ひざ"].tail, "tail": edit_bones["右ひざ"].tail + Vector((0, 0.1, 0)), "parent": "右足IK親"},
            "右つま先IK": {"head": edit_bones["右足首"].tail, "tail": edit_bones["右足首"].tail + Vector((0, 0, -0.05)), "parent": "右足ＩＫ"}
        }

        # 创建或更新骨骼使用定义的属性
        for bone_name, properties in IKbone_properties.items():
            create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties["parent"], use_deform=False)

        # 切换到 POSE 模式
        bpy.ops.object.mode_set(mode='POSE')

        # 获取骨骼对象
        left_hiza = obj.pose.bones["左ひざ"]
        left_kutu = obj.pose.bones["左足首"]
        right_hiza = obj.pose.bones["右ひざ"]
        right_kutu = obj.pose.bones["右足首"]

        # 为左ひざ添加 IK 和旋转限制约束
        add_ik_and_limit_rotation_constraints(left_hiza, obj, "左足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        # 为左足首添加阻尼跟踪和 IK 约束
        add_ik_and_damped_track_constraints(left_kutu, obj, "左つま先IK", 1, 200, damped_track_subtarget="左ひざ")

        # 为右ひざ添加 IK 和旋转限制约束
        add_ik_and_limit_rotation_constraints(right_hiza, obj, "右足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        # 为右足首添加阻尼跟踪和 IK 约束
        add_ik_and_damped_track_constraints(right_kutu, obj, "右つま先IK", 1, 200, damped_track_subtarget="右ひざ")

        return {'FINISHED'}