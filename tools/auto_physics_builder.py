"""
自动物理构建器
包含乳房物理和身体刚体构建功能

代码结构：
    1. 乳房物理系统
       1-1. 乳房专用工具函数
       1-2. 乳房刚体创建代码

    2. 身体刚体系统（简易模式）
       2-1. 简易身体刚体参数计算（基于骨骼权重）
       2-2. 身体刚体创建操作符

    3. 高级身体刚体系统（开发中）
       3-1. 网格分析模块 - 权重收集、PCA分析
       3-2. 参数计算模块 - 位置、半径、旋转
       3-3. 高级刚体生成算法
       3-4. 向后兼容函数

    4. 通用横截面分析模块

    5. 注册/反注册函数
"""
import bpy
import math
from mathutils import Vector, Euler, Matrix
from .. import bone_utils

try:
    from bl_ext.blender_org.mmd_tools.core.rigid_body import FnRigidBody
    from bl_ext.blender_org.mmd_tools.core.model import FnModel
except ImportError:
    try:
        from mmd_tools.core.rigid_body import FnRigidBody
        from mmd_tools.core.model import FnModel
    except ImportError as e:
        print(f"导入 mmd_tools 错误 {e}")
        print("请在 Blender 扩展仓库中安装 mmd_tools 扩展")
        raise


# ===========================================================================
# =                        1. 乳房专用工具函数                                =
# ===========================================================================

def calculate_breast_sphere_fit(armature, bone_name, weight_threshold=0.001):
    """
    计算乳房近似球形的半径和中心（加权平均质心算法）

    Args:
        armature: 骨架对象
        bone_name: 乳房骨骼名称
        weight_threshold: 权重阈值

    Returns:
        dict: {
            'center': Vector - 球心位置（世界坐标）,
            'radius': float - 球半径,
            'vertex_count': int - 顶点数,
            'total_weight': float - 总权重
        } 或 None
    """
    #print(f"[DEBUG 1/6] 开始球形拟合: bone_name={bone_name}")
    
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    #print(f"[DEBUG 2/6] 找到网格对象: {[obj.name for obj in mesh_objs]}")
    if not mesh_objs:
        #print(f"[DEBUG 2/6] 未找到网格对象，返回 None")
        return None

    vertices_world = []
    weights = []
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(bone_name)
        #print(f"[DEBUG 3/6] 检查网格 {mesh_obj.name}, 顶点组 {bone_name} 存在: {vg is not None}")
        if not vg:
            continue
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > weight_threshold:
                    vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    weights.append(group.weight)
                    break

    bone_exists = bone_name in armature.data.bones or (hasattr(armature.data, 'edit_bones') and bone_name in armature.data.edit_bones)
    #print(f"[DEBUG 4/6] 收集到顶点数: {len(vertices_world)}, 骨骼存在(数据模式): {bone_name in armature.data.bones}, 骨骼存在(编辑模式): {hasattr(armature.data, 'edit_bones') and bone_name in armature.data.edit_bones}")
    if not vertices_world or not bone_exists:
        #print(f"[DEBUG 4/6] 顶点为空或骨骼不存在，返回 None")
        return None

    total_weight = sum(weights)
    #print(f"[DEBUG 5/6] 总权重: {total_weight}")
    if total_weight == 0:
        #print(f"[DEBUG 5/6] 总权重为 0，返回 None")
        return None

    center_x = sum(v.x * w for v, w in zip(vertices_world, weights)) / total_weight
    center_y = sum(v.y * w for v, w in zip(vertices_world, weights)) / total_weight
    center_z = sum(v.z * w for v, w in zip(vertices_world, weights)) / total_weight
    center = Vector((center_x, center_y, center_z))

    total_distance = sum((v - center).length * w for v, w in zip(vertices_world, weights))
    radius = total_distance / total_weight

    #print(f"[DEBUG 6/6] 球形拟合完成: {bone_name}, 球心=({center_x:.4f}, {center_y:.4f}, {center_z:.4f}), 半径={radius:.4f}")

    return {
        'center': center,
        'radius': radius,
        'vertex_count': len(vertices_world),
        'total_weight': total_weight
    }


# ===========================================================================
# =                        2. 乳房刚体构建代码                                =
# ===========================================================================

DEG5 = 0.0872665
DEG10 = 0.174533
DEG20 = 0.349066

COLLISION_GROUP_MASK_0 = [True] * 16
COLLISION_GROUP_MASK_2 = [True] * 16
# mass 质量 friction 摩擦系数 linear_damping 线性阻尼
# angular_damping 角度阻尼 is_kinematic 动画 collision_group 碰撞组
CHEST_RIGID_BODIES = {
    "左胸上": {"shape": "CAPSULE", "mass": 0.05, "friction": 0.0, "linear_damping": 0.8,
               "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
               "size_x": 0.01, "size_y": 0.02, "size_z": 0.0},
    "右胸上": {"shape": "CAPSULE", "mass": 0.05, "friction": 0.0, "linear_damping": 0.8,
               "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
               "size_x": 0.01, "size_y": 0.02, "size_z": 0.0},
    "左胸上 2": {"shape": "SPHERE", "mass": 0.20, "friction": 0.0, "linear_damping": 0.8,
                 "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
                 "size_x": 0.5, "size_y": 1, "size_z": 0.0},
    "右胸上 2": {"shape": "SPHERE", "mass": 0.20, "friction": 0.0, "linear_damping": 0.8,
                 "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
                 "size_x": 0.5, "size_y": 1, "size_z": 0.0},
    "左胸下": {"shape": "CAPSULE", "mass": 0.05, "friction": 0.0, "linear_damping": 0.8,
               "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
               "size_x": 0.01, "size_y": 0.02, "size_z": 0.0},
    "右胸下": {"shape": "CAPSULE", "mass": 0.05, "friction": 0.0, "linear_damping": 0.8,
               "angular_damping": 0.8, "is_kinematic": False, "collision_group": 2,
               "size_x": 0.01, "size_y": 0.02, "size_z": 0.0},
    "胸親": {"shape": "CAPSULE", "mass": 1.0, "friction": 0.5, "linear_damping": 0.5,
             "angular_damping": 0.5, "is_kinematic": True, "collision_group": 0,
             "size_x":0.5, "size_y": 1, "size_z": 0.0},
}

class OBJECT_OT_auto_physics_builder(bpy.types.Operator):
    """自动构建乳房物理系统"""
    bl_idname = "object.auto_physics_builder"
    bl_label = "Auto Build Breast Physics"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = context.active_object
            if not armature or armature.type != 'ARMATURE':
                self.report({'ERROR'}, "请选择骨架对象")
                return {'CANCELLED'}

            bpy.ops.object.use_mmd_tools_convert()

            context.scene.frame_set(context.scene.frame_start)

            left_bone = context.scene.left_chest_bone if hasattr(context.scene, "left_chest_bone") else ""
            right_bone = context.scene.right_chest_bone if hasattr(context.scene, "right_chest_bone") else ""

            if not left_bone or not right_bone:
                self.report({'ERROR'}, "请先选择左/右胸部骨骼")
                return {'CANCELLED'}

            breast_data = self._build_breast_bone_chain(context, armature, left_bone, right_bone)
            if breast_data == {'CANCELLED'}:
                return {'CANCELLED'}
            rb_objects = self._create_rigid_bodies(context, armature, breast_data)
            if rb_objects is None:
                return {'CANCELLED'}
            self._create_spring_joints(context, armature, rb_objects)

            bpy.ops.object.mode_set(mode='OBJECT')
            armature.select_set(True)
            context.view_layer.objects.active = armature

            self.report({'INFO'}, "乳房物理系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}
    #乳房骨骼链构建
    def _build_breast_bone_chain(self, context, armature, left_bone, right_bone):
        scene = context.scene
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones
        #胸親骨骼
        breast_parent_name = scene.breast_parent_bone if scene.breast_parent_bone else None
        if breast_parent_name and breast_parent_name not in eb:

            reference_bone = eb.get(left_bone) if left_bone else None
            reference_y = reference_bone.head.y
            reference_z = reference_bone.head.z
        else:
            reference_y = eb[breast_parent_name].head.y
            reference_z = eb[breast_parent_name].head.z

        BrP_head = Vector((0, reference_y, reference_z))
        BrP_tail = BrP_head + Vector((0, 0, 0.08))

        BrP = bone_utils.create_or_update_bone(
            edit_bones=eb, name="胸親",
            head_position=BrP_head, tail_position=BrP_tail,
            use_connect=False, parent_name=breast_parent_name, use_deform=True
        )
        #作用：胸上2骨骼
        breast_data = {}
        for prefix, user_bone in (("左", left_bone), ("右", right_bone)):
            if user_bone not in eb:
                raise ValueError(f"骨骼 '{user_bone}' 不存在")

            BrUp2_name = f"{prefix}胸上 2"
            if user_bone != BrUp2_name:
                eb[user_bone].name = BrUp2_name

            BrUp2 = eb[BrUp2_name]
            sphere_fit = calculate_breast_sphere_fit(armature, BrUp2_name, weight_threshold=0)

            if sphere_fit is None:
                self.report({'ERROR'}, f"无法计算{prefix}侧乳房球形拟合，请检查顶点权重")
                bpy.ops.object.mode_set(mode='OBJECT')
                return {'CANCELLED'}

            breast_data[prefix] = {
                'center': sphere_fit['center'],
                'radius': sphere_fit['radius'],
                'bone': BrUp2
            }

        if '左' in breast_data and '右' in breast_data:
            left_data = breast_data['左']
            right_data = breast_data['右']

            avg_y = (left_data['center'].y + right_data['center'].y) / 2
            avg_z = (left_data['center'].z + right_data['center'].z) / 2
            avg_radius = (left_data['radius'] + right_data['radius']) / 2
            abs_x = max(abs(left_data['center'].x), abs(right_data['center'].x))

            for prefix, sign in (("左", 1), ("右", -1)):
                data = breast_data[prefix]
                data['center'].x = sign * abs_x
                data['center'].y = avg_y
                data['center'].z = avg_z
                data['radius'] = avg_radius

        for prefix, user_bone in (("左", left_bone), ("右", right_bone)):
            data = breast_data[prefix]
            BrUp2 = data['bone']
            breast_center = data['center']
            breast_radius = data['radius']
            self.report({'INFO'}, f"{prefix}侧使用球心: {breast_center}, 半径: {breast_radius}")
            
            BrUp_name = f"{prefix}胸上"
            BrDown_name = f"{prefix}胸下"
            
            # 保存原始骨骼坐标（用于胸上/胸下头部位置）
            original_bone_x = BrUp2.head.x
            original_bone_y = BrUp2.head.y
            
            br_up2_head_z = breast_center.z + breast_radius
            br_up2_tail_z = breast_center.z - breast_radius
            # 胸上2骨骼：头部尾部X、Y与球心相同，Z为球心位置加减半径
            BrUp2.head = Vector((breast_center.x, breast_center.y, br_up2_head_z))
            BrUp2.tail = Vector((breast_center.x, breast_center.y, br_up2_tail_z))
            # 胸上骨骼：头部X、Y与原始骨骼相同，Z为球心位置加半径；尾部X、Y与球心相同，Z为球心位置加半径
            BrUp_head = Vector((original_bone_x, original_bone_y, br_up2_head_z))
            bone_utils.create_or_update_bone(edit_bones=eb, name=BrUp_name,
                                            head_position=BrUp_head, tail_position=BrUp2.head,
                                            use_connect=False, parent_name=None, use_deform=True)
            BrUp2.parent = eb[BrUp_name]

            # 胸下骨骼：头部X、Y与原始骨骼相同，Z为球心位置减半径；尾部X、Y与球心相同，Z为球心位置减半径
            BrDown_head = Vector((original_bone_x, original_bone_y, br_up2_tail_z))
            BrDown_tail = BrUp2.tail
            bone_utils.create_or_update_bone(edit_bones=eb, name=BrDown_name,
                head_position=BrDown_head, tail_position=BrDown_tail,
                use_connect=False, parent_name=None, use_deform=True)

        for prefix in ("左", "右"):
            eb[f"{prefix}胸上"].parent = BrP
            eb[f"{prefix}胸下"].parent = BrP

        scene.left_chest_bone = "左胸上 2"
        scene.right_chest_bone = "右胸上 2"

        bpy.ops.object.mode_set(mode='OBJECT')
        return breast_data
    #乳房刚体构建
    def _create_rigid_bodies(self, context, armature, breast_data):
        root = FnModel.find_root_object(armature)
        if not root:
            self.report({'ERROR'}, "未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
            return None

        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        rb_objects = {}

        for bone_name, params in CHEST_RIGID_BODIES.items():
            if bone_name not in armature.data.bones:
                continue

            if bone_name in bpy.data.objects:
                rb_objects[bone_name] = bpy.data.objects[bone_name]
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            pbone = armature.pose.bones.get(bone_name)
            if not pbone:
                continue

            bone = pbone.bone

            if params["shape"] == "SPHERE" and bone_name in ("左胸上 2", "右胸上 2"):
                prefix = "左" if "左" in bone_name else "右"
                sphere_radius = breast_data[prefix]['radius']
                size = Vector((sphere_radius, sphere_radius, sphere_radius))
            else:
                size = Vector((params["size_x"], params["size_y"], params["size_z"]))

            bone_loc = (bone.head_local + bone.tail_local) / 2
            bone_rot = bone.matrix_local.to_euler("YXZ")
            bone_rot.rotate_axis("X", math.pi / 2)

            rb_obj.location = bone_loc
            rb_obj.rotation_euler = bone_rot
            rb_obj.mmd_rigid.shape = params["shape"]
            rb_obj.mmd_rigid.size = size
            rb_obj.mmd_rigid.type = "0" if params["is_kinematic"] else "1"
            rb_obj.mmd_rigid.collision_group_number = params["collision_group"]
            rb_obj.mmd_rigid.collision_group_mask = COLLISION_GROUP_MASK_0 if params["collision_group"] == 0 else COLLISION_GROUP_MASK_2
            rb_obj.name = bone_name
            rb_obj.mmd_rigid.name_j = bone_name
            rb_obj.mmd_rigid.name_e = bone_name
            rb_obj.data.name = bone_name
            rb_obj.mmd_rigid.bone = bone_name

            rb = rb_obj.rigid_body
            rb.friction = params["friction"]
            rb.mass = params["mass"]
            rb.angular_damping = params["angular_damping"]
            rb.linear_damping = params["linear_damping"]
            rb.restitution = 0.0

            rb_objects[bone_name] = rb_obj

        rb_parent = rb_objects.get("胸親")
        if rb_parent:
            left_rb = rb_objects.get("左胸上 2")
            right_rb = rb_objects.get("右胸上 2")
            if not left_rb or not right_rb:
                self.report({'ERROR'}, "无法找到左/右胸刚体，胸親刚体位置无法设置")
                return None
            rb_parent.location = (left_rb.location + right_rb.location) / 2
            rb_parent.rotation_euler = Euler((0, -math.pi/2, 0), 'YXZ')
            
            left_radius = breast_data["左"]['radius']
            right_radius = breast_data["右"]['radius']
            avg_radius = (left_radius + right_radius) / 2
            x_distance = abs(left_rb.location.x - right_rb.location.x)
            rb_parent.mmd_rigid.size = Vector((avg_radius, x_distance, 0.0))

        return rb_objects
    #乳房弹簧构建
    def _create_spring_joints(self, context, armature, rb_objects):
        root = FnModel.find_root_object(armature)
        joint_grp_obj = FnModel.ensure_joint_group_object(context, root)

        for sd in self._get_spring_definitions():
            rb1 = rb_objects.get(sd["rb1"])
            rb2 = rb_objects.get(sd["rb2"])
            if not rb1 or not rb2:
                continue

            if rb2.name in bpy.data.objects and bpy.data.objects[rb2.name].mmd_type == "JOINT":
                continue

            joint_obj = FnRigidBody.new_joint_object(context, joint_grp_obj, FnModel.get_empty_display_size(root))
            mid = (rb1.location + rb2.location) / 2

            joint_obj = FnRigidBody.setup_joint_object(
                obj=joint_obj, name=rb2.name, name_e=rb2.name, location=Vector(mid),
                rotation=Euler((0, 0, 0)), rigid_a=rb1, rigid_b=rb2,
                maximum_location=Vector((sd.get("lin_x_hi", 0), sd.get("lin_y_hi", 0), sd.get("lin_z_hi", 0))),
                minimum_location=Vector((sd.get("lin_x_lo", 0), sd.get("lin_y_lo", 0), sd.get("lin_z_lo", 0))),
                maximum_rotation=Vector((sd.get("ang_x_hi", 0), sd.get("ang_y_hi", 0), sd.get("ang_z_hi", 0))),
                minimum_rotation=Vector((sd.get("ang_x_lo", 0), sd.get("ang_y_lo", 0), sd.get("ang_z_lo", 0))),
                spring_linear=Vector((sd.get("k_lin_x", 0), sd.get("k_lin_y", 0), sd.get("k_lin_z", 0))),
                spring_angular=Vector((sd.get("k_ang_x", 0), sd.get("k_ang_y", 0), sd.get("k_ang_z", 0))),
            )
            joint_obj.rigid_body_constraint.disable_collisions = True
    #乳房弹簧定义
    def _get_spring_definitions(self):
        def s(joint, rb1, rb2, **kw):
            for ax in 'xyz':
                for pre in (f'lin_{ax}', f'ang_{ax}'):
                    if pre not in kw:
                        kw[pre] = 0
            kw.update({"joint": joint, "rb1": rb1, "rb2": rb2})
            return kw

        defs = []
        for prefix in ('左', '右'):
            defs.append(s(f"J.{prefix}胸上", "胸親", f"{prefix}胸上", ang_z_lo=-DEG5, ang_z_hi=DEG5, k_ang_z=100))
            defs.append(s(f"J.{prefix}胸上 2", f"{prefix}胸上", f"{prefix}胸上 2"))
            defs.append(s(f"J.{prefix}胸下", "胸親", f"{prefix}胸下",
                         ang_x_lo=-DEG10, ang_x_hi=DEG10, ang_z_lo=-DEG5, ang_z_hi=DEG5, k_ang_x=100, k_ang_z=100))
        return defs


# ===========================================================================
# =                        2. 身体刚体系统（简易模式）                          =
# ===========================================================================

# ---------------------------------------------------------------------------
# 2-1. 简易身体刚体生成（基于骨骼权重）
# ---------------------------------------------------------------------------



def calculate_simple_body_rigid_params(armature, bone_names=None):
    """
    简易身体刚体参数计算（基于骨骼权重）
    
    流程：
    1. 遍历每个骨骼
    2. 获取骨骼对应顶点组权重顶点
    3. 依据顶点计算半径（顶点到骨骼中心的最大距离）
    4. 创建刚体，刚体位置使用骨骼中心，长度使用骨骼长度
    
    Args:
        armature: 骨架对象
        bone_names: 骨骼名称列表，None表示使用所有变形骨骼
    
    Returns:
        list: 刚体参数列表
    """
    if bone_names is None:
        bone_names = [bone.name for bone in armature.data.bones if bone.use_deform]
    
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return []
    
    rigid_params = []
    
    for bone_name in bone_names:
        if bone_name not in armature.data.bones:
            continue
        
        bone = armature.data.bones[bone_name]
        
        # 2-1. 获取骨骼对应顶点组权重顶点
        vertices_world = []
        
        for mesh_obj in mesh_objs:
            vg = mesh_obj.vertex_groups.get(bone_name)
            if not vg:
                continue
            
            for vertex in mesh_obj.data.vertices:
                for group in vertex.groups:
                    if group.group == vg.index and group.weight > 0.5:
                        vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                        break
        
        if not vertices_world:
            continue
        
        # 2-2. 依据顶点计算半径
        # 使用骨骼中心作为刚体位置
        bone_head_world = armature.matrix_world @ bone.head_local
        bone_tail_world = armature.matrix_world @ bone.tail_local
        center = (bone_head_world + bone_tail_world) / 2
        
        # 计算顶点到骨骼轴线的垂直距离，使用95%分位数作为半径（去除离群点）
        bone_length = (bone_tail_world - bone_head_world).length
        bone_axis_dir = (bone_tail_world - bone_head_world).normalized()
        
        perp_distances = []
        for v in vertices_world:
            v_rel = v - bone_head_world
            t = v_rel.dot(bone_axis_dir)
            t = max(0.0, min(bone_length, t))
            closest = bone_head_world + t * bone_axis_dir
            perp_distance = (v - closest).length
            perp_distances.append(perp_distance)
        
        # 排序后取95%分位数，去除离群点的影响
        if perp_distances:
            perp_distances.sort()
            idx = int(len(perp_distances) * 0.95)
            idx = max(idx, len(perp_distances) - 1)  # 确保至少取最后一个
            radius = perp_distances[idx]
        else:
            radius = 0.1  # 默认半径
        
        # 2-3. 创建刚体，刚体位置使用骨骼中心，长度使用骨骼长度
        # 通过骨骼的世界方向向量计算旋转矩阵
        rotation_matrix = _build_rotation_matrix(bone_axis_dir).inverted()
        
        rigid_params.append({
            'index': len(rigid_params),
            'center': center,
            'length': bone_length,
            'outer_radius': radius,
            'rotation_matrix': rotation_matrix,
            'nearest_bone': bone_name,
            'vertex_count': len(vertices_world)
        })
    
    return rigid_params


# ---------------------------------------------------------------------------
# 2-2. 简易身体刚体创建操作符
# ---------------------------------------------------------------------------

class OBJECT_OT_build_simple_body_rigid(bpy.types.Operator):
    """构建简易身体刚体（基于骨骼权重）"""
    bl_idname = "object.build_simple_body_rigid"
    bl_label = "构建简易身体刚体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = context.active_object
            if not armature or armature.type != 'ARMATURE':
                self.report({'ERROR'}, "请选择骨架对象")
                return {'CANCELLED'}

            bpy.ops.object.use_mmd_tools_convert()

            root = FnModel.find_root_object(armature)
            if not root:
                self.report({'ERROR'}, "未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
                return {'CANCELLED'}

            self._create_simple_body_rigid_bodies(context, armature, root)
            self.report({'INFO'}, "简易身体刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _create_simple_body_rigid_bodies(self, context, armature, root):
        """使用简易模式创建身体刚体（基于骨骼权重）"""
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)

        # 获取所有变形骨骼
        deform_bones = [bone.name for bone in armature.data.bones if bone.use_deform]
        
        # 使用简易算法计算刚体参数
        rigid_params_list = calculate_simple_body_rigid_params(
            armature, 
            bone_names=deform_bones
        )

        if not rigid_params_list:
            self.report({'WARNING'}, "未找到足够的顶点数据来生成刚体")
            return

        # 创建每个刚体
        for params in rigid_params_list:
            # 生成刚体名称
            bone_name = params['nearest_bone']
            rb_name = f"{bone_name}"
            
            # 如果已存在则跳过
            if rb_name in bpy.data.objects:
                continue

            # 创建刚体对象
            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)

            # 转换世界坐标和旋转到刚体组对象的本地坐标
            local_center = rigid_grp_obj.matrix_world.inverted() @ params['center']
            rb_obj.location = local_center

            parent_rot_inv = rigid_grp_obj.matrix_world.inverted().to_3x3()
            local_rotation = parent_rot_inv @ params['rotation_matrix']
            rb_obj.rotation_euler = local_rotation.to_euler('YXZ')
            
            # 设置胶囊体尺寸（MMD胶囊体格式：X=半径, Y=长度, Z=0）
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((params['outer_radius'], params['length'], 0.0))
            
            # 设置刚体属性
            rb_obj.mmd_rigid.type = "0"  # 运动学刚体
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            # 设置名称
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            
            # 设置关联骨骼
            if params['nearest_bone']:
                rb_obj.mmd_rigid.bone = params['nearest_bone']
            
            # 设置物理属性
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 1.0 / len(rigid_params_list)
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            print(f"[简易身体刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=(半径:{params['outer_radius']:.4f}, 长度:{params['length']:.4f}), 关联骨骼={params['nearest_bone']}")


# ===========================================================================
# =                        3. 高级身体刚体系统（开发中）                        =
# ===========================================================================

# ---------------------------------------------------------------------------
# 3-1. 网格分析模块 - 权重收集、PCA分析、曲率分析
# ---------------------------------------------------------------------------

def analyze_mesh_curvature(mesh_obj, vertex_group_name, sample_step=5):
    """
    分析网格曲率变化
    
    流程：
    1. 获取骨骼权重顶点
    2. 沿骨骼方向采样顶点
    3. 计算各采样点的截面和曲率
    
    Args:
        mesh_obj: 网格对象
        vertex_group_name: 顶点组名称
        sample_step: 采样步长
    
    Returns:
        dict: 包含采样点、曲率、截面半径等信息
    """
    vg = mesh_obj.vertex_groups.get(vertex_group_name)
    if not vg:
        return None
    
    # 收集顶点组中的顶点
    vertices = []
    weights = []
    for vertex in mesh_obj.data.vertices:
        for group in vertex.groups:
            if group.group == vg.index and group.weight > 0.001:
                vertices.append(mesh_obj.matrix_world @ Vector(vertex.co))
                weights.append(group.weight)
                break
    
    if not vertices:
        return None
    
    # PCA分析获取主方向（骨骼方向）
    # 计算质心
    centroid = sum(vertices, Vector((0, 0, 0))) / len(vertices)
    
    # 构建协方差矩阵
    cov_matrix = Matrix(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
    for v in vertices:
        diff = v - centroid
        for i in range(3):
            for j in range(3):
                cov_matrix[i][j] += diff[i] * diff[j]
    cov_matrix /= len(vertices)
    
    # 特征值分解获取主方向
    eigenvalues, eigenvectors = cov_matrix.svd()
    bone_direction = eigenvectors[0].normalized()
    
    # 沿骨骼方向投影并排序
    projected = []
    for v in vertices:
        proj = (v - centroid).dot(bone_direction)
        projected.append((proj, v))
    
    projected.sort(key=lambda x: x[0])
    
    # 计算采样点和曲率
    samples = []
    min_proj = projected[0][0]
    max_proj = projected[-1][0]
    total_length = max_proj - min_proj
    
    num_samples = max(5, int(total_length / 0.05))  # 至少5个采样点
    step = total_length / (num_samples - 1)
    
    for i in range(num_samples):
        proj_pos = min_proj + i * step
        
        # 收集该位置附近的顶点
        nearby_vertices = []
        for proj, v in projected:
            if abs(proj - proj_pos) < step * 1.5:
                nearby_vertices.append(v)
        
        if nearby_vertices:
            # 计算垂直于骨骼方向的截面
            # 将顶点投影到垂直平面
            plane_pts = []
            for v in nearby_vertices:
                proj_vec = (v - centroid).dot(bone_direction) * bone_direction
                plane_pt = (v - centroid) - proj_vec
                plane_pts.append(plane_pt)
            
            # 计算截面半径（最大距离）
            max_radius = max(p.length for p in plane_pts)
            
            # 计算截面中心
            center_offset = sum(plane_pts, Vector((0, 0, 0))) / len(plane_pts)
            world_center = centroid + proj_pos * bone_direction + center_offset
            
            samples.append({
                'position': world_center,
                'radius': max_radius,
                'projected_position': proj_pos,
                'vertex_count': len(nearby_vertices)
            })
    
    # 计算曲率
    curvature_values = []
    for i in range(1, len(samples) - 1):
        prev = samples[i - 1]
        curr = samples[i]
        next_s = samples[i + 1]
        
        # 计算相邻向量
        v1 = curr['position'] - prev['position']
        v2 = next_s['position'] - curr['position']
        
        # 计算角度变化（曲率近似）
        if v1.length > 0 and v2.length > 0:
            angle = math.acos(min(1.0, max(-1.0, v1.normalized().dot(v2.normalized()))))
            curvature_values.append(angle)
    
    avg_curvature = sum(curvature_values) / len(curvature_values) if curvature_values else 0.0
    max_curvature = max(curvature_values) if curvature_values else 0.0
    
    return {
        'samples': samples,
        'bone_direction': bone_direction,
        'total_length': total_length,
        'avg_curvature': avg_curvature,
        'max_curvature': max_curvature,
        'centroid': centroid
    }


# ---------------------------------------------------------------------------
# 3-2. 参数计算模块 - 位置、半径、旋转、分段计算
# ---------------------------------------------------------------------------
def _build_rotation_matrix(axis):
    """构建将向量对齐到Z轴的旋转矩阵"""
    z_axis = Vector((0, 0, 1))
    
    if axis.dot(z_axis) > 0.9999:
        return Matrix.Identity(3)
    if axis.dot(z_axis) < -0.9999:
        return Matrix.Rotation(math.pi, 3, 'X')
    
    # 关键：cross积顺序必须是 axis.cross(z_axis)，才能得到正确的旋转轴
    # 这样旋转后 axis 会转到 z_axis 方向
    cross = axis.cross(z_axis)
    cross.normalize()
    angle = math.acos(axis.dot(z_axis))
    
    return Matrix.Rotation(angle, 3, cross)

def calculate_segmentation_params(curvature_data, min_segment_length=0.1, max_segment_length=0.2):
    """
    计算分段数量和长度，切分网格，做到曲率变化平缓
    
    Args:
        curvature_data: 曲率分析数据
        min_segment_length: 最小段长度
        max_segment_length: 最大段长度
    
    Returns:
        list: 分段参数列表
    """
    samples = curvature_data['samples']
    if not samples:
        return []
    
    segments = []
    total_length = curvature_data['total_length']
    
    # 根据曲率调整分段密度
    # 曲率大的地方分段更细
    avg_curvature = curvature_data['avg_curvature']
    
    i = 0
    segment_index = 0
    
    while i < len(samples):
        # 根据局部曲率决定分段长度
        if i + 2 < len(samples):
            # 计算局部曲率
            v1 = samples[i + 1]['position'] - samples[i]['position']
            v2 = samples[i + 2]['position'] - samples[i + 1]['position']
            if v1.length > 0 and v2.length > 0:
                local_curvature = math.acos(min(1.0, max(-1.0, v1.normalized().dot(v2.normalized()))))
            else:
                local_curvature = avg_curvature
        else:
            local_curvature = avg_curvature
        
        # 曲率越大，分段越短
        curvature_factor = min(1.0, max(0.3, 1.0 - (local_curvature - avg_curvature) * 10))
        target_length = max_segment_length * curvature_factor
        target_length = max(min_segment_length, min(max_segment_length, target_length))
        
        # 找到合适的结束点
        start_sample = samples[i]
        end_idx = i + 1
        accumulated_length = 0.0
        
        while end_idx < len(samples):
            length = (samples[end_idx]['position'] - samples[end_idx - 1]['position']).length
            if accumulated_length + length > target_length and end_idx > i + 1:
                break
            accumulated_length += length
            end_idx += 1
        
        end_idx = min(end_idx, len(samples) - 1)
        end_sample = samples[end_idx]
        
        # 计算分段中心
        center = (start_sample['position'] + end_sample['position']) / 2
        
        # 计算分段长度
        segment_length = accumulated_length if accumulated_length > 0 else (end_sample['position'] - start_sample['position']).length
        
        # 计算分段方向
        direction = (end_sample['position'] - start_sample['position']).normalized()
        
        # 计算平均半径
        avg_radius = sum(s['radius'] for s in samples[i:end_idx + 1]) / (end_idx - i + 1)
        
        segments.append({
            'index': segment_index,
            'start_sample': i,
            'end_sample': end_idx,
            'center': center,
            'length': segment_length,
            'radius': avg_radius,
            'direction': direction,
            'start_position': start_sample['position'],
            'end_position': end_sample['position']
        })
        
        segment_index += 1
        i = end_idx
    
    return segments


def calculate_body_rigid_params(armature, bone_names=None, min_segment_length=0.1, max_segment_length=0.2):
    """
    高级身体刚体参数计算
    
    流程：
    1. 网格曲率变化分析
    2. 计算分段数量和长度，切分网格，做到曲率变化平缓
    3. 通过曲率和分段计算刚体角度和位置中心，网格截面半径
    4. 使用分段长度作为刚体长度，网格截面半径作为刚体半径创建刚体
    
    Args:
        armature: 骨架对象
        bone_names: 骨骼名称列表，None表示使用所有变形骨骼
        min_segment_length: 最小段长度
        max_segment_length: 最大段长度
    
    Returns:
        list: 刚体参数列表
    """
    if bone_names is None:
        bone_names = [bone.name for bone in armature.data.bones if bone.use_deform]
    
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return []
    
    rigid_params = []
    
    for bone_name in bone_names:
        if bone_name not in armature.data.bones:
            continue
        
        bone = armature.data.bones[bone_name]
        
        # 3-1. 网格曲率变化分析
        curvature_data = None
        for mesh_obj in mesh_objs:
            curvature_data = analyze_mesh_curvature(mesh_obj, bone_name)
            if curvature_data:
                break
        
        if not curvature_data or not curvature_data['samples']:
            continue
        
        # 3-2. 计算分段数量和长度，切分网格，做到曲率变化平缓
        segments = calculate_segmentation_params(
            curvature_data,
            min_segment_length,
            max_segment_length
        )
        
        # 3-3. 通过曲率和分段计算刚体角度和位置中心，网格截面半径
        for segment in segments:
            # 构建旋转矩阵（将胶囊体Y轴方向旋转到分段方向）
            rotation_matrix = _build_rotation_matrix(segment['direction']).inverted()
            
            rigid_params.append({
                'index': len(rigid_params),
                'center': segment['center'],
                'length': segment['length'],
                'outer_radius': segment['radius'],
                'rotation_matrix': rotation_matrix,
                'nearest_bone': bone_name,
                'vertex_count': segment.get('vertex_count', 0),
                'segment_index': segment['index']
            })
    
    return rigid_params


# ---------------------------------------------------------------------------
# 3-3. 高级刚体创建操作符
# ---------------------------------------------------------------------------

class OBJECT_OT_build_advanced_body_rigid(bpy.types.Operator):
    """构建高级身体刚体（基于网格曲率分段）"""
    bl_idname = "object.build_advanced_body_rigid"
    bl_label = "构建高级身体刚体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = context.active_object
            if not armature or armature.type != 'ARMATURE':
                self.report({'ERROR'}, "请选择骨架对象")
                return {'CANCELLED'}

            bpy.ops.object.use_mmd_tools_convert()

            root = FnModel.find_root_object(armature)
            if not root:
                self.report({'ERROR'}, "未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
                return {'CANCELLED'}

            min_segment_length = context.scene.body_rigid_min_segment_length
            max_segment_length = context.scene.body_rigid_max_segment_length

            self.report({'WARNING'}, "高级模式为开发中功能，可能不稳定")
            self._create_advanced_body_rigid_bodies(context, armature, root, min_segment_length, max_segment_length)
            self.report({'INFO'}, "高级身体刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _create_advanced_body_rigid_bodies(self, context, armature, root, min_segment_length=0.1, max_segment_length=0.2):
        """使用高级算法创建身体刚体（开发中）"""
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)

        # 获取所有变形骨骼
        deform_bones = [bone.name for bone in armature.data.bones if bone.use_deform]
        
        # 使用新算法计算刚体参数（网格分析 + 参数计算）
        rigid_params_list = calculate_body_rigid_params(
            armature, 
            bone_names=deform_bones,
            min_segment_length=min_segment_length,
            max_segment_length=max_segment_length
        )

        if not rigid_params_list:
            self.report({'WARNING'}, "未找到足够的顶点数据来生成刚体")
            return

        # 创建每个刚体
        for params in rigid_params_list:
            # 生成刚体名称
            bone_name = params['nearest_bone'] if params['nearest_bone'] else "Body"
            rb_name = f"{bone_name}_{params['index'] + 1}"
            
            # 如果已存在则跳过
            if rb_name in bpy.data.objects:
                continue

            # 创建刚体对象
            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)

            # 转换世界坐标和旋转到刚体组对象的本地坐标（刚体是rigid_grp_obj的子对象）
            local_center = rigid_grp_obj.matrix_world.inverted() @ params['center']
            rb_obj.location = local_center

            parent_rot_inv = rigid_grp_obj.matrix_world.inverted().to_3x3()
            local_rotation = parent_rot_inv @ params['rotation_matrix']
            rb_obj.rotation_euler = local_rotation.to_euler('YXZ')
            
            # 设置胶囊体尺寸（MMD胶囊体格式：X=半径, Y=长度, Z=0）
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((params['outer_radius'], params['length'], 0.0))
            
            # 设置刚体属性
            rb_obj.mmd_rigid.type = "0"  # 运动学刚体
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            # 设置名称
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            
            # 设置关联骨骼（使用最近的骨骼）
            if params['nearest_bone']:
                rb_obj.mmd_rigid.bone = params['nearest_bone']
            
            # 设置物理属性
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 1.0 / len(rigid_params_list)
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            print(f"[高级身体刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=(外半径:{params['outer_radius']:.4f}, 长度:{params['length']:.4f}), 关联骨骼={params['nearest_bone']}")


# ===========================================================================
# =                        4. 注册/反注册函数                                 =
# ===========================================================================

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(OBJECT_OT_build_simple_body_rigid)
    bpy.utils.register_class(OBJECT_OT_build_advanced_body_rigid)

    
    # 乳房物理属性
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(name="左胸部骨骼", default="")
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(name="右胸部骨骼", default="")
 
def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(OBJECT_OT_build_simple_body_rigid)
    bpy.utils.unregister_class(OBJECT_OT_build_advanced_body_rigid)


if __name__ == "__main__":
    register()
