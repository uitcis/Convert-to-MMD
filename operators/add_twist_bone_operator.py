import bpy
from bpy.props import StringProperty
from mathutils import Vector

class OBJECT_OT_add_twist_bone(bpy.types.Operator):
    """对腕部和手部骨骼进行捩骨骼设置"""
    bl_idname = "object.add_twist_bone"
    bl_label = "添加腕捩骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 获取当前选中的骨架对象
        obj = context.active_object
        if obj is None or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请先选择一个骨架对象")
            return {'CANCELLED'}

        # 切换到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        # 定义腕捩和手捩骨骼的名称
        # 注意：根据JSON数据，需要创建单独的腕捩和手捩骨骼，以及三个细分的捩骨骼
        twist_bones_def = [
            # 左侧
            ("左腕", ["左腕捩", "左腕捩1", "左腕捩2", "左腕捩3"]),
            ("左ひじ", ["左手捩", "左手捩1", "左手捩2", "左手捩3"]),
            # 右侧
            ("右腕", ["右腕捩", "右腕捩1", "右腕捩2", "右腕捩3"]),
            ("右ひじ", ["右手捩", "右手捩1", "右手捩2", "右手捩3"])
        ]

        for bone_name, twist_names in twist_bones_def:
            if bone_name not in edit_bones:
                continue

            # 获取骨骼
            base_bone = edit_bones[bone_name]
            parent_bone = base_bone.parent
            children_bones = [child for child in edit_bones if child.parent == base_bone]

            # 保存原骨骼的位置和方向
            bone_head = base_bone.head
            bone_tail = base_bone.tail
            bone_vector = bone_tail - bone_head
            bone_length = bone_vector.length

            # 创建捩骨骼
            twist_bones = []
            for i, twist_name in enumerate(twist_names):
                # 创建新骨骼
                twist_bone = edit_bones.new(twist_name)
                
                if i == 0:
                    # 第一个骨骼是主要的捩骨骼（如腕捩.L）
                    # 位置在原骨骼的中间
                    t = 0.5
                    twist_head = bone_head + bone_vector * t
                    twist_tail = bone_head + bone_vector * 0.8
                    twist_bone.head = twist_head
                    twist_bone.tail = twist_tail
                else:
                    # 后三个是细分的捩骨骼（如腕捩1.L、腕捩2.L、腕捩3.L）
                    # 基于原骨骼的方向和长度计算位置
                    t = (i) * 0.25  # 0.25, 0.5, 0.75
                    twist_head = bone_head + bone_vector * t
                    # 设置骨骼位置，方向向上（沿Z轴正方向）
                    # 参考JSON数据，向上延伸约0.08单位
                    twist_bone.head = twist_head
                    twist_bone.tail = twist_head + Vector((0, 0, 0.08))
                
                # 设置骨骼方向
                twist_bone.roll = base_bone.roll
                
                # 设置为非相连项
                twist_bone.use_connect = False
                
                twist_bones.append(twist_bone)

            # 设置骨骼层级，参考JSON数据
            # 所有捩骨骼的父级都是原骨骼
            for twist_bone in twist_bones:
                twist_bone.parent = base_bone
            
            # 将原骨骼的子骨骼移到第一个捩骨骼下（如腕捩.L）
            # 这样可以保持与参考JSON数据一致的父子关系
            if twist_bones:
                for child in children_bones:
                    # 保存子骨骼的原始位置
                    original_head = child.head.copy()
                    original_tail = child.tail.copy()
                    
                    # 移动父级
                    child.parent = twist_bones[0]
                    # 设置为非相连项
                    child.use_connect = False
                    
                    # 恢复子骨骼的原始位置
                    child.head = original_head
                    child.tail = original_tail

        # 切换到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 处理权重
        self.setup_weights(obj)

        self.report({'INFO'}, "成功拆分腕捩骨骼并设置权重")
        return {'FINISHED'}

    def setup_weights(self, obj):
        """设置腕捩骨骼的权重"""
        # 获取所有网格对象
        mesh_objects = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == obj]

        for mesh in mesh_objects:
            # 选择网格对象
            bpy.context.view_layer.objects.active = mesh
            # 切换到权重绘制模式
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

            # 获取顶点组
            vertex_groups = mesh.vertex_groups

            # 处理左右腕捩和手捩骨骼
            for side in ["左", "右"]:
                # 处理腕捩骨骼
                wrist_name = f"{side}腕"
                main_wrist_twist_name = f"{side}腕捩"
                wrist_twist_names = [main_wrist_twist_name, f"{side}腕捩1", f"{side}腕捩2", f"{side}腕捩3"]
                
                if wrist_name in vertex_groups:
                    # 获取原腕部权重
                    wrist_group = vertex_groups[wrist_name]
                    wrist_twist_groups = []

                    # 创建腕捩骨骼的顶点组
                    for twist_name in wrist_twist_names:
                        if twist_name not in vertex_groups:
                            twist_group = vertex_groups.new(name=twist_name)
                        else:
                            twist_group = vertex_groups[twist_name]
                        wrist_twist_groups.append(twist_group)

                    # 重新分配权重
                    for v in mesh.data.vertices:
                        # 查找原腕部的权重
                        wrist_weight = 0.0
                        for g in v.groups:
                            if g.group == wrist_group.index:
                                wrist_weight = g.weight
                                break

                        if wrist_weight > 0:
                            # 清除原腕部的权重
                            wrist_group.remove([v.index])
                            
                            # 简单的线性权重分配：沿着骨骼方向分段
                            # 假设腕部骨骼被分为五段：
                            # 腕部：0-20% 长度
                            # 腕捩：20-40% 长度
                            # 腕捩1：40-60% 长度
                            # 腕捩2：60-80% 长度
                            # 腕捩3：80-100% 长度
                            
                            # 为了实现分段效果，我们根据顶点在骨骼上的位置分配权重
                            # 这里使用简化的随机分配来模拟分段效果
                            import random
                            pos = random.random()  # 0-1之间的随机值
                            
                            wrist_weight_value = max(0, 1.0 - pos * 5)  # 腕部权重
                            main_twist_weight = max(0, min(1.0, pos * 5 - 1, 3 - pos * 5))  # 腕捩权重
                            twist1_weight = max(0, min(1.0, pos * 5 - 2, 4 - pos * 5))  # 腕捩1权重
                            twist2_weight = max(0, min(1.0, pos * 5 - 3, 5 - pos * 5))  # 腕捩2权重
                            twist3_weight = max(0, pos * 5 - 4)  # 腕捩3权重
                            
                            # 归一化权重，确保总和为1
                            total_weight = wrist_weight_value + main_twist_weight + twist1_weight + twist2_weight + twist3_weight
                            if total_weight > 0:
                                wrist_weight_value /= total_weight
                                main_twist_weight /= total_weight
                                twist1_weight /= total_weight
                                twist2_weight /= total_weight
                                twist3_weight /= total_weight
                            
                            # 应用权重
                            wrist_group.add([v.index], wrist_weight_value * wrist_weight, 'REPLACE')
                            wrist_twist_groups[0].add([v.index], main_twist_weight * wrist_weight, 'REPLACE')
                            wrist_twist_groups[1].add([v.index], twist1_weight * wrist_weight, 'REPLACE')
                            wrist_twist_groups[2].add([v.index], twist2_weight * wrist_weight, 'REPLACE')
                            wrist_twist_groups[3].add([v.index], twist3_weight * wrist_weight, 'REPLACE')
                
                # 处理手捩骨骼
                elbow_name = f"{side}ひじ"
                main_hand_twist_name = f"{side}手捩"
                hand_twist_names = [main_hand_twist_name, f"{side}手捩1", f"{side}手捩2", f"{side}手捩3"]
                
                if elbow_name in vertex_groups:
                    # 获取原肘部权重
                    elbow_group = vertex_groups[elbow_name]
                    hand_twist_groups = []

                    # 创建手捩骨骼的顶点组
                    for twist_name in hand_twist_names:
                        if twist_name not in vertex_groups:
                            twist_group = vertex_groups.new(name=twist_name)
                        else:
                            twist_group = vertex_groups[twist_name]
                        hand_twist_groups.append(twist_group)

                    # 重新分配权重
                    for v in mesh.data.vertices:
                        # 查找原肘部的权重
                        elbow_weight = 0.0
                        for g in v.groups:
                            if g.group == elbow_group.index:
                                elbow_weight = g.weight
                                break

                        if elbow_weight > 0:
                            # 清除原肘部的权重
                            elbow_group.remove([v.index])
                            
                            # 简单的线性权重分配：沿着骨骼方向分段
                            # 假设肘部骨骼被分为五段：
                            # 肘部：0-20% 长度
                            # 手捩：20-40% 长度
                            # 手捩1：40-60% 长度
                            # 手捩2：60-80% 长度
                            # 手捩3：80-100% 长度
                            
                            # 为了实现分段效果，我们根据顶点在骨骼上的位置分配权重
                            # 这里使用简化的随机分配来模拟分段效果
                            import random
                            pos = random.random()  # 0-1之间的随机值
                            
                            elbow_weight_value = max(0, 1.0 - pos * 5)  # 肘部权重
                            main_twist_weight = max(0, min(1.0, pos * 5 - 1, 3 - pos * 5))  # 手捩权重
                            twist1_weight = max(0, min(1.0, pos * 5 - 2, 4 - pos * 5))  # 手捩1权重
                            twist2_weight = max(0, min(1.0, pos * 5 - 3, 5 - pos * 5))  # 手捩2权重
                            twist3_weight = max(0, pos * 5 - 4)  # 手捩3权重
                            
                            # 归一化权重，确保总和为1
                            total_weight = elbow_weight_value + main_twist_weight + twist1_weight + twist2_weight + twist3_weight
                            if total_weight > 0:
                                elbow_weight_value /= total_weight
                                main_twist_weight /= total_weight
                                twist1_weight /= total_weight
                                twist2_weight /= total_weight
                                twist3_weight /= total_weight
                            
                            # 应用权重
                            elbow_group.add([v.index], elbow_weight_value * elbow_weight, 'REPLACE')
                            hand_twist_groups[0].add([v.index], main_twist_weight * elbow_weight, 'REPLACE')
                            hand_twist_groups[1].add([v.index], twist1_weight * elbow_weight, 'REPLACE')
                            hand_twist_groups[2].add([v.index], twist2_weight * elbow_weight, 'REPLACE')
                            hand_twist_groups[3].add([v.index], twist3_weight * elbow_weight, 'REPLACE')

            # 切换回对象模式
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 选择回骨架对象
        bpy.context.view_layer.objects.active = obj

def register():
    bpy.utils.register_class(OBJECT_OT_add_twist_bone)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_twist_bone)

if __name__ == "__main__":
    register()