import bpy
import math
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
            # 先创建所有捩骨骼
            for i, twist_name in enumerate(twist_names):
                # 创建新骨骼
                twist_bone = edit_bones.new(twist_name)
                
                if i == 0:
                    # 第一个骨骼是主要的捩骨骼（如左腕捩）
                    # 位置在原骨骼的中间到尾部之间，参考JSON数据
                    t = 0.6
                    twist_head = bone_head + bone_vector * t
                    twist_tail = bone_head + bone_vector * 1.0
                    twist_bone.head = twist_head
                    twist_bone.tail = twist_tail
                else:
                    # 后三个是细分的捩骨骼（如腕捩1.L、腕捩2.L、腕捩3.L）
                    # 基于原骨骼的方向和长度计算位置，参考JSON数据
                    t = (i) * 0.2  # 0.2, 0.4, 0.6
                    twist_head = bone_head + bone_vector * t
                    # 设置骨骼位置，方向向上（沿Z轴正方向）
                    # 参考JSON数据，向上延伸约0.08单位
                    twist_bone.head = twist_head
                    twist_bone.tail = twist_head + Vector((0, 0, 0.08))
                
                # 设置骨骼方向
                if i == 0:
                    # 主要的捩骨骼（如左腕捩、左手捩）保持原始roll
                    twist_bone.roll = base_bone.roll
                else:
                    # 只有1、2、3对应的捩骨骼需要设置扭转为0
                    twist_bone.roll = 0.0
                
                # 设置为非相连项
                twist_bone.use_connect = False
                
                twist_bones.append(twist_bone)
            
            # 然后创建shadow和dummy骨骼，放到捩2和3之间
            for i, twist_bone in enumerate(twist_bones):
                if i > 0:  # 跳过主要的捩骨骼（如左腕捩）
                    # 计算捩2和3之间的位置，所有shadow和dummy骨骼都放在这里
                    if len(twist_bones) > 3:
                        # 计算捩2和捩3之间的中点
                        twist2_head = twist_bones[2].head
                        twist3_head = twist_bones[3].head
                        shadow_head = (twist2_head + twist3_head) / 2
                    else:
                        # 如果没有捩3，就放在捩2的位置
                        if len(twist_bones) > 2:
                            shadow_head = twist_bones[2].head
                        else:
                            shadow_head = twist_bone.head
                    
                    # 创建shadow骨骼
                    shadow_bone_name = f"_shadow_{twist_bone.name}"
                    shadow_bone = edit_bones.new(shadow_bone_name)
                    shadow_bone.head = shadow_head
                    shadow_bone.tail = shadow_head + Vector((0, 0, 0.08))  # 尾部在头部上方
                    shadow_bone.parent = base_bone
                    shadow_bone.use_connect = False
                    # 只有1、2、3对应的shadow骨骼需要设置扭转为0
                    shadow_bone.roll = 0.0
                    
                    # 创建dummy骨骼，与shadow骨骼位置相同
                    dummy_bone_name = f"_dummy_{twist_bone.name}"
                    dummy_bone = edit_bones.new(dummy_bone_name)
                    dummy_bone.head = shadow_bone.head  # 与shadow骨骼位置相同
                    dummy_bone.tail = shadow_bone.tail  # 与shadow骨骼位置相同
                    # 只有1、2、3对应的dummy骨骼需要设置扭转为0
                    dummy_bone.roll = 0.0
                    
                    # 根据骨骼类型设置正确的父级
                    if "腕捩" in twist_bone.name:
                        # 查找腕捩骨骼作为dummy骨骼的父级
                        main_twist_name = twist_bone.name.replace("1", "").replace("2", "").replace("3", "")
                        if main_twist_name in edit_bones:
                            dummy_bone.parent = edit_bones[main_twist_name]
                        else:
                            dummy_bone.parent = base_bone
                    elif "手捩" in twist_bone.name:
                        # 查找手捩骨骼作为dummy骨骼的父级
                        main_twist_name = twist_bone.name.replace("1", "").replace("2", "").replace("3", "")
                        if main_twist_name in edit_bones:
                            dummy_bone.parent = edit_bones[main_twist_name]
                        else:
                            dummy_bone.parent = base_bone
                    else:
                        dummy_bone.parent = base_bone
                    
                    dummy_bone.use_connect = False

            # 设置骨骼层级，参考JSON数据
            # 所有捩骨骼的父级都是原骨骼
            for twist_bone in twist_bones:
                twist_bone.parent = base_bone
            
            # 将原骨骼的子骨骼移到第一个捩骨骼下（如左腕捩）
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

        # 添加约束
        self.setup_constraints(obj)#处在姿态模式

        # 处理权重
        self.setup_weights(obj)#处在网格权重模式
        # 切换回对象模式
        bpy.ops.object.mode_set(mode='OBJECT')
        #仅选择骨架对象
        bpy.context.view_layer.objects.active = obj
        # 对创建的骨骼进行分组，直接调用collection_operator中的操作符
        bpy.ops.object.create_bone_group()
        self.report({'INFO'}, "成功拆分腕捩骨骼并设置权重和约束")
        return {'FINISHED'}
    def setup_constraints(self, obj):
        """为腕捩和手捩骨骼添加约束"""
        # 切换到姿态模式
        bpy.ops.object.mode_set(mode='POSE')
        
        pose_bones = obj.pose.bones
        
        # 锁定腕捩和手捩骨骼的移动以及X和Z轴的旋转
        for bone in pose_bones:
            if "腕捩" in bone.name or "手捩" in bone.name:
                # 锁定移动
                bone.lock_location[0] = True
                bone.lock_location[1] = True
                bone.lock_location[2] = True
                # 锁定X和Z轴的旋转，只允许Y轴旋转
                bone.lock_rotation[0] = True
                bone.lock_rotation[1] = False
                bone.lock_rotation[2] = True
        
        # 为腕捩骨骼添加约束
        for side in ['左', '右']:
            # 腕捩骨骼约束
            for i in range(1, 4):  # 腕捩1, 腕捩2, 腕捩3
                twist_bone_name = f"{side}腕捩{i}"
                if twist_bone_name in pose_bones:
                    twist_bone = pose_bones[twist_bone_name]
                    
                    # 清除现有约束
                    for constraint in twist_bone.constraints:
                        twist_bone.constraints.remove(constraint)
                    
                    # 添加TRANSFORM约束
                    transform_constraint = twist_bone.constraints.new('TRANSFORM')
                    transform_constraint.name = "mmd_additional_rotation"
                    transform_constraint.target = obj
                    transform_constraint.subtarget = f"_shadow_{side}腕捩{i}"
                    transform_constraint.influence = 1.0
                    transform_constraint.use_motion_extrapolate = True
                    # 设置所有者空间为局部空间
                    transform_constraint.owner_space = 'LOCAL'
                    # 设置目标空间为局部空间
                    transform_constraint.target_space = 'LOCAL'
                    # 设置从旋转映射到旋转
                    transform_constraint.map_from = 'ROTATION'
                    transform_constraint.map_to = 'ROTATION'
                    # 设置映射自的模式为XYZ欧拉
                    transform_constraint.from_rotation_mode = 'XYZ'
                    # 设置映射模式为XYZ欧拉
                    transform_constraint.to_euler_order = 'XYZ'
                    # 设置混合选项为初始后
                    transform_constraint.mix_mode_rot = 'AFTER'
                    
                    # 设置旋转范围（将角度转换为弧度）
                    transform_constraint.from_min_x_rot = math.radians(-180.0)
                    transform_constraint.from_min_y_rot = math.radians(-180.0)
                    transform_constraint.from_min_z_rot = math.radians(-180.0)
                    transform_constraint.from_max_x_rot = math.radians(180.0)
                    transform_constraint.from_max_y_rot = math.radians(180.0)
                    transform_constraint.from_max_z_rot = math.radians(180.0)
                    
                    # 根据骨骼索引设置不同的旋转限制（将角度转换为弧度）
                    if i == 1:
                        transform_constraint.to_min_x_rot = math.radians(-45.0)
                        transform_constraint.to_min_y_rot = math.radians(-45.0)
                        transform_constraint.to_min_z_rot = math.radians(-45.0)
                        transform_constraint.to_max_x_rot = math.radians(45.0)
                        transform_constraint.to_max_y_rot = math.radians(45.0)
                        transform_constraint.to_max_z_rot = math.radians(45.0)
                    elif i == 2:
                        transform_constraint.to_min_x_rot = math.radians(-90.0)
                        transform_constraint.to_min_y_rot = math.radians(-90.0)
                        transform_constraint.to_min_z_rot = math.radians(-90.0)
                        transform_constraint.to_max_x_rot = math.radians(90.0)
                        transform_constraint.to_max_y_rot = math.radians(90.0)
                        transform_constraint.to_max_z_rot = math.radians(90.0)
                    elif i == 3:
                        transform_constraint.to_min_x_rot = math.radians(-135.0)
                        transform_constraint.to_min_y_rot = math.radians(-135.0)
                        transform_constraint.to_min_z_rot = math.radians(-135.0)
                        transform_constraint.to_max_x_rot = math.radians(135.0)
                        transform_constraint.to_max_y_rot = math.radians(135.0)
                        transform_constraint.to_max_z_rot = math.radians(135.0)
            
            # 为手捩骨骼添加约束
            for i in range(1, 4):  # 手捩1, 手捩2, 手捩3
                twist_bone_name = f"{side}手捩{i}"
                if twist_bone_name in pose_bones:
                    twist_bone = pose_bones[twist_bone_name]
                    
                    # 清除现有约束
                    for constraint in twist_bone.constraints:
                        twist_bone.constraints.remove(constraint)
                    
                    # 添加TRANSFORM约束
                    transform_constraint = twist_bone.constraints.new('TRANSFORM')
                    transform_constraint.name = "mmd_additional_rotation"
                    transform_constraint.target = obj
                    transform_constraint.subtarget = f"_shadow_{side}手捩{i}"
                    transform_constraint.influence = 1.0
                    transform_constraint.use_motion_extrapolate = True
                    # 设置所有者空间为局部空间
                    transform_constraint.owner_space = 'LOCAL'
                    # 设置目标空间为局部空间
                    transform_constraint.target_space = 'LOCAL'
                    # 设置从旋转映射到旋转
                    transform_constraint.map_from = 'ROTATION'
                    transform_constraint.map_to = 'ROTATION'
                    # 设置映射自的模式为XYZ欧拉
                    transform_constraint.from_rotation_mode = 'XYZ'
                    # 设置映射模式为XYZ欧拉
                    transform_constraint.to_euler_order = 'XYZ'
                    # 设置混合选项为初始后
                    transform_constraint.mix_mode_rot = 'AFTER'
                    
                    # 设置旋转范围（将角度转换为弧度）
                    transform_constraint.from_min_x_rot = math.radians(-180.0)
                    transform_constraint.from_min_y_rot = math.radians(-180.0)
                    transform_constraint.from_min_z_rot = math.radians(-180.0)
                    transform_constraint.from_max_x_rot = math.radians(180.0)
                    transform_constraint.from_max_y_rot = math.radians(180.0)
                    transform_constraint.from_max_z_rot = math.radians(180.0)
                    
                    # 根据骨骼索引设置不同的旋转限制（将角度转换为弧度）
                    if i == 1:
                        transform_constraint.to_min_x_rot = math.radians(-45.0)
                        transform_constraint.to_min_y_rot = math.radians(-45.0)
                        transform_constraint.to_min_z_rot = math.radians(-45.0)
                        transform_constraint.to_max_x_rot = math.radians(45.0)
                        transform_constraint.to_max_y_rot = math.radians(45.0)
                        transform_constraint.to_max_z_rot = math.radians(45.0)
                    elif i == 2:
                        transform_constraint.to_min_x_rot = math.radians(-90.0)
                        transform_constraint.to_min_y_rot = math.radians(-90.0)
                        transform_constraint.to_min_z_rot = math.radians(-90.0)
                        transform_constraint.to_max_x_rot = math.radians(90.0)
                        transform_constraint.to_max_y_rot = math.radians(90.0)
                        transform_constraint.to_max_z_rot = math.radians(90.0)
                    elif i == 3:
                        transform_constraint.to_min_x_rot = math.radians(-135.0)
                        transform_constraint.to_min_y_rot = math.radians(-135.0)
                        transform_constraint.to_min_z_rot = math.radians(-135.0)
                        transform_constraint.to_max_x_rot = math.radians(135.0)
                        transform_constraint.to_max_y_rot = math.radians(135.0)
                        transform_constraint.to_max_z_rot = math.radians(135.0)
        
        # 为shadow骨骼添加COPY_TRANSFORMS约束
        for side in ['左', '右']:
            # 腕捩shadow骨骼
            for i in range(1, 4):
                shadow_bone_name = f"_shadow_{side}腕捩{i}"
                if shadow_bone_name in pose_bones:
                    shadow_bone = pose_bones[shadow_bone_name]
                    
                    # 清除现有约束
                    for constraint in shadow_bone.constraints:
                        shadow_bone.constraints.remove(constraint)
                    
                    # 添加COPY_TRANSFORMS约束
                    copy_constraint = shadow_bone.constraints.new('COPY_TRANSFORMS')
                    copy_constraint.name = "mmd_tools_at_dummy"
                    copy_constraint.target = obj
                    copy_constraint.subtarget = f"_dummy_{side}腕捩{i}"
                    copy_constraint.influence = 1.0
                    # 设置为姿态空间
                    copy_constraint.owner_space = 'POSE'
                    copy_constraint.target_space = 'POSE'
            
            # 手捩shadow骨骼
            for i in range(1, 4):
                shadow_bone_name = f"_shadow_{side}手捩{i}"
                if shadow_bone_name in pose_bones:
                    shadow_bone = pose_bones[shadow_bone_name]
                    
                    # 清除现有约束
                    for constraint in shadow_bone.constraints:
                        shadow_bone.constraints.remove(constraint)
                    
                    # 添加COPY_TRANSFORMS约束
                    copy_constraint = shadow_bone.constraints.new('COPY_TRANSFORMS')
                    copy_constraint.name = "mmd_tools_at_dummy"
                    copy_constraint.target = obj
                    copy_constraint.subtarget = f"_dummy_{side}手捩{i}"
                    copy_constraint.influence = 1.0
                    # 设置为姿态空间
                    copy_constraint.owner_space = 'POSE'
                    copy_constraint.target_space = 'POSE'

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
                            
                            # 为了实现分段效果，我们根据顶点在骨骼上的实际位置分配权重
                            # 获取原腕部骨骼的起点和终点
                            armature = obj
                            pose_bones = armature.pose.bones
                            if wrist_name in pose_bones:
                                wrist_bone = pose_bones[wrist_name]
                                # 获取骨骼的世界坐标
                                head_world = armature.matrix_world @ wrist_bone.head
                                tail_world = armature.matrix_world @ wrist_bone.tail
                                
                                # 计算骨骼向量
                                bone_vector = tail_world - head_world
                                bone_length = bone_vector.length
                                
                                # 计算顶点的世界坐标
                                vertex_world = mesh.matrix_world @ v.co
                                
                                # 计算顶点在骨骼方向上的投影
                                if bone_length > 0:
                                    # 计算顶点到骨骼起点的向量
                                    vertex_vector = vertex_world - head_world
                                    # 计算投影长度
                                    projection_length = vertex_vector.dot(bone_vector.normalized())
                                    # 归一化到0-1范围
                                    pos = max(0, min(1, projection_length / bone_length))
                                else:
                                    pos = 0.5  # 默认值
                            else:
                                pos = 0.5  # 默认值
                            
                            # 计算基础权重（最大值为1）
                            # 调整分段位置，确保权重顺序为：腕、腕捩1、腕捩2、腕捩3、腕捩
                            base_wrist = max(0, 1.0 - pos * 5)  # 腕部基础权重 (0-20%)
                            base_twist1 = max(0, min(1.0, pos * 5 - 1, 2 - pos * 5))  # 腕捩1基础权重 (20-40%)
                            base_twist2 = max(0, min(1.0, pos * 5 - 2, 3 - pos * 5))  # 腕捩2基础权重 (40-60%)
                            base_twist3 = max(0, min(1.0, pos * 5 - 3, 4 - pos * 5))  # 腕捩3基础权重 (60-80%)
                            base_main = max(0, pos * 5 - 4)  # 腕捩基础权重 (80-100%)
                            
                            # 归一化基础权重
                            total_base = base_wrist + base_twist1 + base_twist2 + base_twist3 + base_main
                            if total_base > 0:
                                # 计算调整后的权重，确保最大值在0.4-0.6之间
                                scale_factor = 0.65  # 调整因子，控制最大权重值
                                wrist_weight_value = (base_wrist / total_base) * scale_factor
                                twist1_weight = (base_twist1 / total_base) * scale_factor
                                twist2_weight = (base_twist2 / total_base) * scale_factor
                                twist3_weight = (base_twist3 / total_base) * scale_factor
                                main_twist_weight = (base_main / total_base) * scale_factor
                            else:
                                # 默认权重
                                wrist_weight_value = 0.1
                                twist1_weight = 0.2
                                twist2_weight = 0.3
                                twist3_weight = 0.2
                                main_twist_weight = 0.2
                            
                            # 应用权重，顺序为：腕、腕捩1、腕捩2、腕捩3、腕捩
                            wrist_group.add([v.index], wrist_weight_value * wrist_weight, 'REPLACE')
                            wrist_twist_groups[1].add([v.index], twist1_weight * wrist_weight, 'REPLACE')  # 腕捩1
                            wrist_twist_groups[2].add([v.index], twist2_weight * wrist_weight, 'REPLACE')  # 腕捩2
                            wrist_twist_groups[3].add([v.index], twist3_weight * wrist_weight, 'REPLACE')  # 腕捩3
                            wrist_twist_groups[0].add([v.index], main_twist_weight * wrist_weight, 'REPLACE')  # 腕捩
                
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
                            
                            # 为了实现分段效果，我们根据顶点在骨骼上的实际位置分配权重
                            # 获取原肘部骨骼的起点和终点
                            armature = obj
                            pose_bones = armature.pose.bones
                            if elbow_name in pose_bones:
                                elbow_bone = pose_bones[elbow_name]
                                # 获取骨骼的世界坐标
                                head_world = armature.matrix_world @ elbow_bone.head
                                tail_world = armature.matrix_world @ elbow_bone.tail
                                
                                # 计算骨骼向量
                                bone_vector = tail_world - head_world
                                bone_length = bone_vector.length
                                
                                # 计算顶点的世界坐标
                                vertex_world = mesh.matrix_world @ v.co
                                
                                # 计算顶点在骨骼方向上的投影
                                if bone_length > 0:
                                    # 计算顶点到骨骼起点的向量
                                    vertex_vector = vertex_world - head_world
                                    # 计算投影长度
                                    projection_length = vertex_vector.dot(bone_vector.normalized())
                                    # 归一化到0-1范围
                                    pos = max(0, min(1, projection_length / bone_length))
                                else:
                                    pos = 0.5  # 默认值
                            else:
                                pos = 0.5  # 默认值
                            
                            # 计算基础权重（最大值为1）
                            # 调整分段位置，确保权重顺序为：肘、手捩1、手捩2、手捩3、手捩
                            base_elbow = max(0, 1.0 - pos * 5)  # 肘部基础权重 (0-20%)
                            base_twist1 = max(0, min(1.0, pos * 5 - 1, 2 - pos * 5))  # 手捩1基础权重 (20-40%)
                            base_twist2 = max(0, min(1.0, pos * 5 - 2, 3 - pos * 5))  # 手捩2基础权重 (40-60%)
                            base_twist3 = max(0, min(1.0, pos * 5 - 3, 4 - pos * 5))  # 手捩3基础权重 (60-80%)
                            base_main = max(0, pos * 5 - 4)  # 手捩基础权重 (80-100%)
                            
                            # 归一化基础权重
                            total_base = base_elbow + base_twist1 + base_twist2 + base_twist3 + base_main
                            if total_base > 0:
                                # 计算调整后的权重，确保最大值在0.4-0.6之间
                                scale_factor = 0.65  # 调整因子，控制最大权重值
                                elbow_weight_value = (base_elbow / total_base) * scale_factor
                                twist1_weight = (base_twist1 / total_base) * scale_factor
                                twist2_weight = (base_twist2 / total_base) * scale_factor
                                twist3_weight = (base_twist3 / total_base) * scale_factor
                                main_twist_weight = (base_main / total_base) * scale_factor
                            else:
                                # 默认权重
                                elbow_weight_value = 0.1
                                twist1_weight = 0.2
                                twist2_weight = 0.3
                                twist3_weight = 0.2
                                main_twist_weight = 0.2
                            
                            # 应用权重，顺序为：肘、手捩1、手捩2、手捩3、手捩
                            elbow_group.add([v.index], elbow_weight_value * elbow_weight, 'REPLACE')
                            hand_twist_groups[1].add([v.index], twist1_weight * elbow_weight, 'REPLACE')  # 手捩1
                            hand_twist_groups[2].add([v.index], twist2_weight * elbow_weight, 'REPLACE')  # 手捩2
                            hand_twist_groups[3].add([v.index], twist3_weight * elbow_weight, 'REPLACE')  # 手捩3
                            hand_twist_groups[0].add([v.index], main_twist_weight * elbow_weight, 'REPLACE')  # 手捩

def register():
    bpy.utils.register_class(OBJECT_OT_add_twist_bone)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_twist_bone)

if __name__ == "__main__":
    register()