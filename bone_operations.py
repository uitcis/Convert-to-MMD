import bpy
from mathutils import Vector
from math import radians
from . import bone_mapping
from . import bone_utils

class OBJECT_OT_rename_to_mmd(bpy.types.Operator):
    """将选定的骨骼重命名为 MMD 格式"""
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
                    # 检查骨骼是否已经重命名为 MMD 格式名称
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
    """补充缺失的 MMD 格式骨骼"""
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
        upper_body_tail = upper_body_bone.tail.copy()

        # 定义基本骨骼的属性
        bone_properties = {

            "全ての親": {"head": Vector((0, 0, 0)), "tail": Vector((0, 0, 0.3)), "parent": None, "use_deform": False, "use_connect": False},
            "センター": {"head": Vector((0, 0, 0.3)), "tail": Vector((0, 0, 0.6)), "parent": "全ての親", "use_deform": False, "use_connect": False},
            "グルーブ": {"head": Vector((0, 0, 0.8)), "tail": Vector((0, 0, 0.7)), "parent": "センター", "use_deform": False, "use_connect": False},
            "腰": {"head": Vector((0, upper_body_head.y + 0.1, upper_body_head.z - 0.12)), "tail": Vector((0, upper_body_head.y, upper_body_head.z)), 
                "parent": "グルーブ", "use_deform": False, "use_connect": False},
            "上半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)), "tail": Vector((0, upper_body_tail.y, upper_body_head.z+0.15)), "parent": "腰", "use_connect": False},
            "上半身2": {"head": Vector((0, edit_bones["上半身2"].head.y, edit_bones["上半身2"].head.z)), "tail": Vector((0, edit_bones["上半身2"].head.y, edit_bones["上半身2"].head.z+0.15)),
                "parent": "上半身", "use_connect": False},
            # 上肢骨骼链
            "左肩": {
                "head": Vector((0, edit_bones["左肩"].head.y , edit_bones["左腕"].head.z)),
                "tail": edit_bones["左腕"].head,
                "parent": edit_bones["左肩"].parent.name if edit_bones["左肩"].parent else None,
                "use_connect": False
            },
            "左腕": {
                "head": edit_bones["左腕"].head,
                "tail": edit_bones["左ひじ"].head,
                "parent": "左肩",
                "use_connect": True
            },
            "左ひじ": {
                "head": edit_bones["左ひじ"].head,
                "tail": edit_bones["左手首"].head if edit_bones["左手首"]else edit_bones["左ひじ"].tail,
                "parent": "左腕",
                "use_connect": True
            },
       
            "右肩": {
                "head": Vector((0, edit_bones["右肩"].head.y , edit_bones["右腕"].head.z)),
                "tail": edit_bones["右腕"].head,
                "parent": edit_bones["右肩"].parent.name if edit_bones["右肩"].parent else None,
                "use_connect": False
            },
            "右腕": {
                "head": edit_bones["右腕"].head,
                "tail": edit_bones["右ひじ"].head,
                "parent": "右肩",
                "use_connect": True
            },
            "右ひじ": {
                "head": edit_bones["右ひじ"].head,
                "tail": edit_bones["右手首"].head if edit_bones["右手首"]else edit_bones["右ひじ"].tail,
                "parent": "右腕",
                "use_connect": True
            }, 
            
            "下半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)), "tail": Vector((0, upper_body_head.y, upper_body_head.z - 0.15)), "parent": "腰", "use_connect": False},
            "左足": {
                "head": edit_bones["左足"].head,
                "tail": edit_bones["左ひざ"].head,
                "parent": "下半身",
                "use_connect": False
            },
            "右足": {
                "head": edit_bones["右足"].head,
                "tail": edit_bones["右ひざ"].head,
                "parent": "下半身",
                "use_connect": False
            },
            "左ひざ": {
                "head": edit_bones["左ひざ"].head,
                "tail": edit_bones["左足首"].head,
                "parent": "左足",
                "use_connect": False
            },
            "右ひざ": {
                "head": edit_bones["右ひざ"].head,
                "tail": edit_bones["右足首"].head,
                "parent": "右足",
                "use_connect": False
            },
            "左足首": {
                "head": edit_bones["左足首"].head,
                "tail": Vector((edit_bones["左足首"].head.x, edit_bones["左足首"].head.y - 0.1, 0)),
                "parent": "左ひざ",
                "use_connect": False
            },
            "右足首": {
                "head": edit_bones["右足首"].head,
                "tail": Vector((edit_bones["右足首"].head.x, edit_bones["右足首"].head.y - 0.1, 0)),
                "parent": "右ひざ",
                "use_connect": False
            }
        }

        # 按顺序检查并创建或更新骨骼
        for bone_name, properties in bone_properties.items():
                bone_utils.create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties.get("use_connect", False), properties["parent"], properties.get("use_deform", True))


        # 调用函数设置 roll 値
        bone_utils.set_roll_values(edit_bones, bone_utils.DEFAULT_ROLL_VALUES)               

        return {'FINISHED'}