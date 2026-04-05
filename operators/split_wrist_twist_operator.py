import bpy
from bpy.props import StringProperty

class OBJECT_OT_split_wrist_twist(bpy.types.Operator):
    """从腕部拆分出三段腕捩骨骼并设置权重"""
    bl_idname = "object.split_wrist_twist"
    bl_label = "拆分腕捩骨骼"
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

        # 定义腕捩骨骼的名称
        wrist_bones = [
            ("左腕", ["左腕捩1", "左腕捩2", "左腕捩3"]),
            ("右腕", ["右腕捩1", "右腕捩2", "右腕捩3"])
        ]

        for wrist_name, twist_names in wrist_bones:
            if wrist_name not in edit_bones:
                continue

            # 获取腕部骨骼
            wrist_bone = edit_bones[wrist_name]
            parent_bone = wrist_bone.parent
            children_bones = [child for child in edit_bones if child.parent == wrist_bone]

            # 计算腕部骨骼的长度
            wrist_length = (wrist_bone.tail - wrist_bone.head).length
            segment_length = wrist_length / 4  # 四段，包括原腕部骨骼

            # 保存原腕部骨骼的位置和方向
            wrist_direction = (wrist_bone.tail - wrist_bone.head).normalized()
            wrist_matrix = wrist_bone.matrix

            # 创建三段腕捩骨骼
            twist_bones = []
            for i, twist_name in enumerate(twist_names):
                # 创建新骨骼
                twist_bone = edit_bones.new(twist_name)
                
                # 设置骨骼位置
                start = wrist_bone.head + wrist_direction * (segment_length * (i + 1))
                end = wrist_bone.head + wrist_direction * (segment_length * (i + 2))
                twist_bone.head = start
                twist_bone.tail = end
                
                # 设置骨骼方向（复制原腕部骨骼的方向）
                twist_bone.roll = wrist_bone.roll
                
                twist_bones.append(twist_bone)

            # 设置骨骼层级
            if parent_bone:
                twist_bones[0].parent = parent_bone
            for i in range(len(twist_bones) - 1):
                twist_bones[i + 1].parent = twist_bones[i]
            
            # 将原腕部骨骼的子骨骼移到最后一段腕捩骨骼下
            for child in children_bones:
                child.parent = twist_bones[-1]

            # 调整原腕部骨骼的长度（作为第一段）
            wrist_bone.tail = twist_bones[0].head
            
            # 设置原腕部骨骼的父级和子级
            if parent_bone:
                wrist_bone.parent = parent_bone
            twist_bones[0].parent = wrist_bone

        # 切换到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 处理权重
        self.setup_weights(obj)

        self.report({'INFO'}, "成功拆分腕捩骨骼并设置权重")
        return {'FINISHED'}

    def setup_weights(self, obj):
        """设置腕捩骨骼的权重"""
        # 切换到权重绘制模式
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

        # 获取所有网格对象
        mesh_objects = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == obj]

        for mesh in mesh_objects:
            # 获取顶点组
            vertex_groups = mesh.vertex_groups

            # 处理左右腕捩骨骼
            for side in ["左", "右"]:
                wrist_name = f"{side}腕"
                twist_names = [f"{side}腕捩1", f"{side}腕捩2", f"{side}腕捩3"]

                # 检查顶点组是否存在
                if wrist_name not in vertex_groups:
                    continue

                # 获取原腕部权重
                wrist_group = vertex_groups[wrist_name]
                twist_groups = []

                # 创建腕捩骨骼的顶点组
                for twist_name in twist_names:
                    if twist_name not in vertex_groups:
                        twist_group = vertex_groups.new(name=twist_name)
                    else:
                        twist_group = vertex_groups[twist_name]
                    twist_groups.append(twist_group)

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

                        # 分配权重到腕捩骨骼
                        # 权重分配比例：腕部:25%, 捩1:25%, 捩2:25%, 捩3:25%
                        weights = [0.25, 0.25, 0.25, 0.25]
                        
                        # 应用权重
                        wrist_group.add([v.index], weights[0] * wrist_weight, 'REPLACE')
                        for i, twist_group in enumerate(twist_groups):
                            twist_group.add([v.index], weights[i + 1] * wrist_weight, 'REPLACE')

        # 切换回对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

def register():
    bpy.utils.register_class(OBJECT_OT_split_wrist_twist)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_split_wrist_twist)

if __name__ == "__main__":
    register()