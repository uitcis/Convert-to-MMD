import bpy
from mathutils import Vector
from .. import bone_utils


class OBJECT_OT_complete_missing_bones(bpy.types.Operator):
    """补充缺失的 MMD 格式骨骼"""
    bl_idname = "object.complete_missing_bones"
    bl_label = "Complete Missing Bones"

    def connect_finger_bones(self, edit_bones):
        """连接手指骨骼的头尾"""
        # 定义手指骨骼链
        finger_chains = [
            # 左手手指
            ["左親指０", "左親指１", "左親指２"],
            ["左人指１", "左人指２", "左人指３"],
            ["左中指１", "左中指２", "左中指３"],
            ["左薬指１", "左薬指２", "左薬指３"],
            ["左小指１", "左小指２", "左小指３"],
            # 右手手指
            ["右親指０", "右親指１", "右親指２"],
            ["右人指１", "右人指２", "右人指３"],
            ["右中指１", "右中指２", "右中指３"],
            ["右薬指１", "右薬指２", "右薬指３"],
            ["右小指１", "右小指２", "右小指３"]
        ]
        
        # 连接每个手指骨骼链
        for chain in finger_chains:
            # 检查链中的所有骨骼是否都存在
            if all(bone in edit_bones for bone in chain):
                # 依次连接手指骨骼的头尾
                for i in range(len(chain) - 1):
                    current_bone = edit_bones[chain[i]]
                    next_bone = edit_bones[chain[i + 1]]
                    # 将当前骨骼的尾部设置为下一个骨骼的头部
                    current_bone.tail = next_bone.head

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
        
        # 计算骨架高度和bone_length
        bone_length = bone_utils.calculate_bone_length(edit_bones) 

        # 定义基本骨骼的属性
        bone_properties = {

            "全ての親": {"head": Vector((0, 0, 0)), "tail": Vector((0, 0, bone_length)), "parent": None, "use_deform": False, "use_connect": False},
            "センター": {"head": Vector((0, 0, bone_length * 2)), "tail": Vector((0, 0, bone_length*1.1)), "parent": "全ての親", "use_deform": False, "use_connect": False},
            "グルーブ": {"head": Vector((0, 0, bone_length * 3.2)), "tail": Vector((0, 0, bone_length * 4)), "parent": "センター", "use_deform": False, "use_connect": False},
            "腰": {"head": Vector((0, upper_body_head.y + bone_length * 0.5, upper_body_head.z - bone_length * 0.5)), "tail": Vector((0, upper_body_head.y, upper_body_head.z)), 
                "parent": "グルーブ", "use_deform": False, "use_connect": False},
            "上半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)),
                "tail": Vector((0, upper_body_tail.y, upper_body_head.z+bone_length)), 
                "parent": "腰", "use_connect": False},
            "首": {
                "head": edit_bones["首"].head,
                "tail": edit_bones["頭"].head,
                "parent": "上半身2" if edit_bones.get("上半身2") else "上半身",
                "use_connect": False
            },
            "頭": {
                "head": edit_bones["頭"].head,
                "tail": Vector((0, edit_bones["頭"].head.y, edit_bones["頭"].head.z+bone_length * 0.25)),
                "parent": "首",
                "use_connect": False
            },                                  
            # 上肢骨骼链
            "左肩": {
                "head": edit_bones["左肩"].head,
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
                "head": edit_bones["右肩"].head,
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
            
            "下半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)), "tail": Vector((0, upper_body_head.y, upper_body_head.z - bone_length)), "parent": "腰", "use_connect": False},
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
                "tail": Vector((edit_bones["左足首"].head.x, edit_bones["左足首"].head.y - bone_length*0.3, 0)),
                "parent": "左ひざ",
                "use_connect": False
            },
            "右足首": {
                "head": edit_bones["右足首"].head,
                "tail": Vector((edit_bones["右足首"].head.x, edit_bones["右足首"].head.y - bone_length*0.3, 0)),
                "parent": "右ひざ",
                "use_connect": False
            },
            "左足先EX": {
                "head": edit_bones["左足首"].tail,
                "tail": Vector((edit_bones["左足首"].tail.x, edit_bones["左足首"].tail.y - bone_length*0.5, 0)),
                "parent": "左足首",
                "use_connect": False
            },
            "右足先EX": {
                "head": edit_bones["右足首"].tail,
                "tail": Vector((edit_bones["右足首"].tail.x, edit_bones["右足首"].tail.y - bone_length*0.5, 0)),
                "parent": "右足首",
                "use_connect": False
            }            
        }

        # 检查上半身2骨骼是否存在，如果存在则添加到属性字典
        if edit_bones.get("上半身2"):
            bone_properties["上半身2"] = {
                "head": Vector((0, edit_bones["上半身2"].head.y, edit_bones["上半身2"].head.z)), 
                "tail": Vector((0, edit_bones["首"].head.y, edit_bones["首"].head.z)),
                "parent": "上半身", "use_connect": False
            }

        # 按顺序检查并创建或更新骨骼
        for bone_name, properties in bone_properties.items():
            # 如果是足先EX且已经存在，保持其头位置不变
            if bone_name in ["左足先EX", "右足先EX"] and bone_name in edit_bones:
                # 保持原有的头位置，只更新尾部和其他属性
                original_head = edit_bones[bone_name].head.copy()
                bone_utils.create_or_update_bone(edit_bones, bone_name, original_head, properties["tail"], properties.get("use_connect", False), properties["parent"], properties.get("use_deform", True))
            else:
                # 正常创建或更新骨骼
                bone_utils.create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties.get("use_connect", False), properties["parent"], properties.get("use_deform", True))
        
        # 如果存在足先EX骨骼，将足首的尾部指向足先EX的头部
        if "左足先EX" in edit_bones:
            # 更新左足首的尾部到左足先EX的头部
            edit_bones["左足首"].tail = edit_bones["左足先EX"].head
        if "右足先EX" in edit_bones:
            # 更新右足首的尾部到右足先EX的头部
            edit_bones["右足首"].tail = edit_bones["右足先EX"].head


        # 调用函数设置 roll 値
        bone_utils.set_roll_values(edit_bones, bone_utils.DEFAULT_ROLL_VALUES)               

        # 连接手指骨骼的头尾
        self.connect_finger_bones(edit_bones)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_complete_missing_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_complete_missing_bones)


if __name__ == "__main__":
    register()
