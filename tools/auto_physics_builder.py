"""
自动物理构建器
包含乳房物理和身体刚体构建功能

代码结构：
    1. 乳房物理系统
       1-1. 乳房专用工具函数
       1-2. 乳房刚体创建代码

    2. 身体刚体系统（重写版本）
       2-1. 网格分析模块 - 权重、截面、曲率变化
       2-2. 刚体参数计算模块 - 位置、数量、长度、角度
       2-3. 身体刚体创建代码

    3. 注册/反注册函数
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
# =                        2. 身体刚体系统（重写版本）                          =
# ===========================================================================

# ---------------------------------------------------------------------------
# 2-1. 网格分析模块 - 权重、截面、曲率变化
# ---------------------------------------------------------------------------

def _collect_mesh_vertices(armature, bone_names):
    """
    收集所有受目标骨骼影响的顶点及其权重
    
    Args:
        armature: 骨架对象
        bone_names: 目标骨骼名称列表
    
    Returns:
        tuple: (顶点列表, 权重列表, 骨骼名称列表)
    """
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return [], [], []
    
    all_vertices = []
    all_weights = []
    all_bone_names = []
    
    for mesh_obj in mesh_objs:
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                # 使用整数索引访问顶点组
                try:
                    vg = mesh_obj.vertex_groups[group.group]
                except (IndexError, KeyError):
                    continue
                if vg and vg.name in bone_names and group.weight > 0.001:
                    all_vertices.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    all_weights.append(group.weight)
                    all_bone_names.append(vg.name)
                    break
    
    return all_vertices, all_weights, all_bone_names


def _compute_pca(vertices, weights):
    """
    计算PCA主成分分析，确定顶点分布的主轴方向
    
    Args:
        vertices: 顶点列表（世界坐标）
        weights: 顶点权重列表
    
    Returns:
        dict: {'principal_axis': 主成分轴, 'secondary_axis': 次成分轴, 'center': 加权质心}
    """
    if len(vertices) < 3:
        return {'principal_axis': Vector((0, 1, 0)), 'secondary_axis': Vector((1, 0, 0)), 'center': Vector((0, 0, 0))}
    
    total_weight = sum(weights)
    if total_weight < 0.001:
        return {'principal_axis': Vector((0, 1, 0)), 'secondary_axis': Vector((1, 0, 0)), 'center': Vector((0, 0, 0))}
    
    # 计算加权质心
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    
    # 计算协方差矩阵
    centered_vertices = [v - center for v in vertices]
    cov_matrix = [[0.0]*3 for _ in range(3)]
    for cv, w in zip(centered_vertices, weights):
        for i in range(3):
            for j in range(3):
                cov_matrix[i][j] += w * cv[i] * cv[j]
    for i in range(3):
        for j in range(3):
            cov_matrix[i][j] /= total_weight
    
    # 求解特征值（简化版本，仅考虑对角元素）
    variance_x, variance_y, variance_z = cov_matrix[0][0], cov_matrix[1][1], cov_matrix[2][2]
    
    vars_sorted = sorted([(variance_x, Vector((1, 0, 0))), 
                          (variance_y, Vector((0, 1, 0))), 
                          (variance_z, Vector((0, 0, 1)))], reverse=True)
    
    return {
        'principal_axis': vars_sorted[0][1],
        'secondary_axis': vars_sorted[1][1],
        'center': center
    }


def _calc_weighted_center_world(vertices, weights):
    """计算世界坐标下的加权质心"""
    total_weight = sum(weights)
    if total_weight < 0.001:
        return Vector((0, 0, 0))
    
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    return center


# ---------------------------------------------------------------------------
# 2-2. 刚体参数计算模块 - 位置、数量、长度、角度
# ---------------------------------------------------------------------------

def _find_nearest_bone(armature, point):
    """
    找到距离给定点最近的骨骼（使用点到线段距离算法）
    
    Args:
        armature: 骨架对象
        point: 目标点（世界坐标）
    
    Returns:
        str: 最近骨骼的名称，None表示未找到
    """
    min_distance = float('inf')
    nearest_bone = None
    
    for bone in armature.data.bones:
        if not bone.use_deform:
            continue
        
        bone_head = armature.matrix_world @ bone.head_local
        bone_tail = armature.matrix_world @ bone.tail_local
        
        # 计算点到骨骼线段的最短距离
        bone_vector = bone_tail - bone_head
        bone_length = bone_vector.length
        
        if bone_length < 0.001:
            distance = (point - bone_head).length
        else:
            projection = (point - bone_head).dot(bone_vector) / bone_length
            projection = max(0.0, min(1.0, projection))
            closest_point = bone_head + bone_vector * projection
            distance = (point - closest_point).length
        
        if distance < min_distance:
            min_distance = distance
            nearest_bone = bone.name
    
    return nearest_bone


def _calc_segment_radius(vertices, weights, center, axis):
    """
    计算刚体段的圆环参数（近似圆环横截面）
    
    将横截面近似为圆环，圆环的中心轴（连接方向）为刚体长度方向（主轴）。
    计算外半径和内半径，形成一个空心圆柱形状。
    
    Args:
        vertices: 顶点列表
        weights: 顶点权重列表
        center: 段中心
        axis: 主轴方向（圆环连接方向，即刚体长度方向）
    
    Returns:
        dict: {'outer_radius': 外半径, 'inner_radius': 内半径}
    """
    centered_vertices = [v - center for v in vertices]
    total_weight = sum(weights)
    
    if total_weight < 0.001:
        return {'outer_radius': 0.01, 'inner_radius': 0.005}
    
    # 计算所有顶点到主轴的垂直距离（形成圆环的横截面半径）
    distances = []
    for cv, w in zip(centered_vertices, weights):
        if w > 0.001:
            dist = cv.cross(axis).length
            distances.extend([dist] * int(w * 100))  # 加权采样
    
    if not distances:
        return {'outer_radius': 0.01, 'inner_radius': 0.005}
    
    # 排序距离
    distances.sort()
    
    # 外半径：取较大的百分位数（如95%）
    outer_idx = int(len(distances) * 0.95)
    outer_radius = distances[min(outer_idx, len(distances)-1)] * 1.1  # 安全系数
    
    # 内半径：取较小的百分位数（如30%），形成空心效果
    inner_idx = int(len(distances) * 0.3)
    inner_radius = distances[max(inner_idx, 0)] * 0.9
    
    # 确保内半径小于外半径
    if inner_radius >= outer_radius:
        inner_radius = outer_radius * 0.5
    
    # 确保最小尺寸
    outer_radius = max(outer_radius, 0.005)
    inner_radius = max(inner_radius, 0.001)
    
    return {'outer_radius': outer_radius, 'inner_radius': inner_radius}


def _build_rotation_matrix(axis):
    """
    根据主轴方向构建旋转矩阵
    
    Args:
        axis: 主轴方向向量
    
    Returns:
        Matrix: 旋转矩阵
    """
    axis = axis.normalized()
    
    # 找到垂直于主轴的两个正交向量
    if abs(axis.y) < 0.9:
        u_axis = Vector((0, 1, 0)).cross(axis).normalized()
    else:
        u_axis = Vector((1, 0, 0)).cross(axis).normalized()
    v_axis = axis.cross(u_axis).normalized()
    
    return Matrix((
        u_axis,
        axis,
        v_axis
    )).transposed()


def calculate_body_rigid_params(armature, bone_names=None, min_segment_length=0.1, max_segment_length=0.2):
    """
    主入口：根据网格和权重计算身体刚体参数
    
    流程：
    1. 收集所有受变形骨骼影响的顶点
    2. 计算整体PCA确定主轴方向
    3. 沿主轴方向投影并排序顶点
    4. 根据长度阈值计算刚体段数
    5. 逐段计算参数（中心、尺寸、旋转）
    6. 为每个段匹配最近的骨骼
    
    Args:
        armature: 骨架对象
        bone_names: 骨骼名称列表，None表示使用所有变形骨骼
        min_segment_length: 最小刚体段长度（米）
        max_segment_length: 最大刚体段长度（米）
    
    Returns:
        list: 刚体参数列表
    """
    # 获取目标骨骼列表
    if bone_names is None:
        bone_names = [bone.name for bone in armature.data.bones if bone.use_deform]
    
    # 收集顶点数据（网格分析）
    all_vertices, all_weights, all_bone_names = _collect_mesh_vertices(armature, bone_names)
    
    if not all_vertices:
        return []
    
    # 整体PCA分析（确定主轴）
    pca_result = _compute_pca(all_vertices, all_weights)
    principal_axis = pca_result['principal_axis']
    
    # 沿主轴方向投影并排序
    projections = [(v.dot(principal_axis), v, w, bn) for v, w, bn in zip(all_vertices, all_weights, all_bone_names)]
    projections.sort(key=lambda x: x[0])
    
    min_proj, max_proj = projections[0][0], projections[-1][0]
    total_length = max_proj - min_proj
    
    # 计算刚体段数
    avg_segment_length = (min_segment_length + max_segment_length) / 2
    segment_count = max(1, int(total_length / avg_segment_length))
    segment_length = total_length / segment_count
    
    # 生成刚体段参数
    rigid_params = []
    for i in range(segment_count):
        segment_start = min_proj + i * segment_length
        segment_end = min_proj + (i + 1) * segment_length
        
        # 收集当前段的顶点
        segment_vertices = []
        segment_weights = []
        
        for proj, v, w, _ in projections:
            if segment_start <= proj <= segment_end:
                segment_vertices.append(v)
                segment_weights.append(w)
        
        if not segment_vertices:
            continue
        
        # 计算段参数
        segment_center = _calc_weighted_center_world(segment_vertices, segment_weights)
        segment_pca = _compute_pca(segment_vertices, segment_weights)
        segment_axis = segment_pca['principal_axis']
        
        # 计算圆环横截面参数（圆环连接方向为刚体长度方向，即主轴方向）
        ring_params = _calc_segment_radius(segment_vertices, segment_weights, segment_center, segment_axis)
        
        nearest_bone = _find_nearest_bone(armature, segment_center)
        rotation_matrix = _build_rotation_matrix(segment_axis)
        
        rigid_params.append({
            'index': i,
            'center': segment_center,
            'length': segment_length,
            'outer_radius': ring_params['outer_radius'],
            'inner_radius': ring_params['inner_radius'],
            'principal_axis': segment_axis,
            'rotation_matrix': rotation_matrix,
            'euler_rotation': rotation_matrix.to_euler('YXZ'),
            'nearest_bone': nearest_bone,
            'vertex_count': len(segment_vertices),
            'segment_start': segment_start,
            'segment_end': segment_end
        })
    
    return rigid_params


# ===========================================================================
# =                        3.1 原有函数（保持向后兼容）                        =
# ===========================================================================

def calculate_bone_rigid_size(armature, bone_name):
    """计算骨骼刚体尺寸（主入口）- 向后兼容"""
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return {'radius': 0.0, 'length': 0.0, 'axis': 'Y', 'count': 0, 'positions': [], 'center': Vector((0, 0, 0)), 'principal_axis': Vector((0, 1, 0)), 'rotation_matrix': None, 'segments': []}

    vertices_world = []
    weights = []
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > 0.001:
                    vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    weights.append(group.weight)
                    break

    if not vertices_world or bone_name not in armature.data.bones:
        return {'radius': 0.0, 'length': 0.0, 'axis': 'Y', 'count': 0, 'positions': [], 'center': Vector((0, 0, 0)), 'principal_axis': Vector((0, 1, 0)), 'rotation_matrix': None, 'segments': []}

    bone = armature.data.bones[bone_name]
    bone_local_matrix = (armature.matrix_world @ bone.matrix_local).inverted()
    vertices = [bone_local_matrix @ v for v in vertices_world]

    center = _calc_weighted_center_world_local(vertices, weights)
    
    pca_result = _calc_principal_axis_local(vertices, weights, center)
    principal_axis, axis = pca_result['principal_axis'], pca_result['axis']
    
    size_result = _calc_length_and_radius_local(vertices, weights, center, principal_axis)
    
    segment_result = _calc_rigid_body_segments_local(vertices, weights, principal_axis)

    count = segment_result['count']
    segments = segment_result['segments']
    positions = [0.0] if count == 1 else [(s['center'] - center).dot(principal_axis) for s in segments]

    return {'radius': size_result['radius'], 'length': size_result['length'], 'axis': axis, 'count': count, 'positions': positions, 'center': center, 'principal_axis': principal_axis, 'rotation_matrix': pca_result['rotation_matrix'], 'segments': segments}


def _calc_weighted_center_world_local(vertices, weights):
    """计算加权质心（本地坐标）"""
    total_weight = sum(weights)
    if total_weight < 0.001:
        return Vector((0, 0, 0))
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    return center


def _calc_principal_axis_local(vertices, weights, center):
    """通过协方差矩阵计算主轴方向（本地坐标）"""
    total_weight = sum(weights)
    if total_weight < 0.001:
        return {'principal_axis': Vector((0, 1, 0)), 'secondary_axis': Vector((1, 0, 0)), 'axis': 'Y', 'rotation_matrix': None}

    centered_vertices = [v - center for v in vertices]
    cov_matrix = [[0.0]*3 for _ in range(3)]
    for cv, w in zip(centered_vertices, weights):
        for i in range(3):
            for j in range(3):
                cov_matrix[i][j] += w * cv[i] * cv[j]
    for i in range(3):
        for j in range(3):
            cov_matrix[i][j] /= total_weight

    variance_x, variance_y, variance_z = cov_matrix[0][0], cov_matrix[1][1], cov_matrix[2][2]
    max_var = max(variance_x, variance_y, variance_z)

    if max_var == variance_x:
        principal_axis, axis = Vector((1, 0, 0)), 'X'
    elif max_var == variance_y:
        principal_axis, axis = Vector((0, 1, 0)), 'Y'
    else:
        principal_axis, axis = Vector((0, 0, 1)), 'Z'

    vars_sorted = sorted([(variance_x, 'X'), (variance_y, 'Y'), (variance_z, 'Z')], reverse=True)
    secondary_axis_name = vars_sorted[1][1]
    secondary_axis = Vector((1, 0, 0)) if secondary_axis_name == 'X' else Vector((0, 1, 0)) if secondary_axis_name == 'Y' else Vector((0, 0, 1))

    return {'principal_axis': principal_axis, 'secondary_axis': secondary_axis, 'axis': axis, 'rotation_matrix': None}


def _calc_length_and_radius_local(vertices, weights, center, principal_axis):
    """计算长度和半径（本地坐标）"""
    centered_vertices = [v - center for v in vertices]
    projections = [cv.dot(principal_axis) for cv in centered_vertices]
    length = max(projections) - min(projections) if projections else 0.01
    length = max(length, 0.01) * 1.1

    total_weight = sum(weights)
    if total_weight < 0.001:
        return {'length': length, 'radius': 0.01}

    total_distance = sum(w * cv.cross(principal_axis).length for cv, w in zip(centered_vertices, weights))
    radius = (total_distance / total_weight) * 1.2
    radius = max(radius, 0.005)

    return {'length': length, 'radius': radius}


def _extract_centerline_local(vertices, weights, principal_axis, slices=20):
    """提取中心线（本地坐标）"""
    if not vertices or not weights:
        return []

    projections = [v.dot(principal_axis) for v in vertices]
    min_proj, max_proj = min(projections), max(projections)

    if max_proj - min_proj < 0.001:
        return [_calc_weighted_center_world_local(vertices, weights)]

    step = (max_proj - min_proj) / slices
    centerline = []

    for i in range(slices):
        slice_start, slice_end = min_proj + i * step, min_proj + (i + 1) * step
        slice_vertices = [v for v, w, proj in zip(vertices, weights, projections) if slice_start <= proj <= slice_end]
        slice_weights = [w for v, w, proj in zip(vertices, weights, projections) if slice_start <= proj <= slice_end]
        if slice_vertices:
            centerline.append(_calc_weighted_center_world_local(slice_vertices, slice_weights))

    return centerline


def _calc_curvature_local(centerline):
    """计算中心线曲率"""
    if len(centerline) < 3:
        return []

    curvature = []
    for i in range(1, len(centerline) - 1):
        v1 = centerline[i] - centerline[i - 1]
        v2 = centerline[i + 1] - centerline[i]
        cross = v1.cross(v2)
        curvature.append(cross.length / max(v1.length ** 3, 0.0001))
    return curvature


def _segment_by_curvature_local(centerline, curvature, max_length=0.15, curvature_threshold=50.0):
    """根据曲率变化和长度阈值分段"""
    if len(centerline) <= 1:
        return [0, len(centerline) - 1] if centerline else []

    segments = [0]
    total_length = sum((centerline[i] - centerline[i - 1]).length for i in range(1, len(centerline)))

    if total_length <= max_length:
        return [0, len(centerline) - 1]

    current_length = 0.0
    start_idx = 0

    for i in range(1, len(centerline)):
        segment_length = (centerline[i] - centerline[i - 1]).length
        current_length += segment_length

        if current_length >= max_length:
            segments.append(i)
            start_idx = i
            current_length = 0.0
        elif i > start_idx + 2 and i - 2 < len(curvature) and curvature[i - 2] > curvature_threshold:
            segments.append(i)
            start_idx = i
            current_length = 0.0

    if segments[-1] != len(centerline) - 1:
        segments.append(len(centerline) - 1)

    return segments


def _calc_rigid_body_segments_local(vertices, weights, principal_axis, max_length=0.15, curvature_threshold=50.0):
    """计算刚体分段（本地坐标）"""
    centerline = _extract_centerline_local(vertices, weights, principal_axis)

    if len(centerline) <= 1:
        return {'count': 1, 'segments': [{'start': 0, 'end': 0, 'length': 0.0}]}

    curvature = _calc_curvature_local(centerline)
    segment_indices = _segment_by_curvature_local(centerline, curvature, max_length, curvature_threshold)

    segments = []
    for i in range(len(segment_indices) - 1):
        start_idx, end_idx = segment_indices[i], segment_indices[i + 1]
        segment_length = sum((centerline[j + 1] - centerline[j]).length for j in range(start_idx, end_idx))
        segments.append({
            'start': start_idx, 'end': end_idx, 'length': segment_length,
            'center': (centerline[start_idx] + centerline[end_idx]) / 2
        })

    return {'count': len(segments), 'segments': segments, 'total_length': sum(s['length'] for s in segments), 'centerline': centerline}


# ---------------------------------------------------------------------------
# 2-3. 身体刚体创建代码
# ---------------------------------------------------------------------------

class OBJECT_OT_build_body_rigid_bodies(bpy.types.Operator):
    """构建身体刚体系统（重写版本）- 先依据网格和权重计算刚体参数，最后匹配最近骨骼"""
    bl_idname = "object.build_body_rigid_bodies"
    bl_label = "构建身体刚体"
    bl_options = {'REGISTER', 'UNDO'}

    min_segment_length: bpy.props.FloatProperty(
        name="最小段长度",
        description="刚体段的最小长度（米）",
        default=0.1,
        min=0.01,
        max=0.5
    )

    max_segment_length: bpy.props.FloatProperty(
        name="最大段长度",
        description="刚体段的最大长度（米）",
        default=0.2,
        min=0.01,
        max=1.0
    )

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

            # 使用新算法创建身体刚体
            self._create_body_rigid_bodies_new(context, armature, root)
            self.report({'INFO'}, "身体刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _create_body_rigid_bodies_new(self, context, armature, root):
        """使用新算法创建身体刚体"""
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)

        # 获取所有变形骨骼
        deform_bones = [bone.name for bone in armature.data.bones if bone.use_deform]
        
        # 使用新算法计算刚体参数（网格分析 + 参数计算）
        rigid_params_list = calculate_body_rigid_params(
            armature, 
            bone_names=deform_bones,
            min_segment_length=self.min_segment_length,
            max_segment_length=self.max_segment_length
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

            # 转换世界坐标到本地坐标
            local_center = armature.matrix_world.inverted() @ params['center']

            # 设置位置和旋转
            rb_obj.location = local_center
            rb_obj.rotation_euler = params['euler_rotation']
            
            # 设置胶囊体尺寸（使用圆环外半径作为胶囊体半径）
            # 圆环连接方向为刚体长度方向（主轴方向）
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((params['outer_radius'], params['length'], params['outer_radius']))
            
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

            print(f"[身体刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=(外半径:{params['outer_radius']:.4f}, 长度:{params['length']:.4f}, 内半径:{params['inner_radius']:.4f}), 关联骨骼={params['nearest_bone']}")





# ===========================================================================
# =                        6. 通用横截面分析与刚体生成                          =
# ===========================================================================

def extract_cross_sections(armature, bone_name, slice_interval=0.025, weight_threshold=0.001, min_slices=5, max_slices=10):
    """
    沿骨骼主轴方向提取横截面切片（通用版本）
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼名称
        slice_interval: 切片间距（米），默认为2.5厘米
        weight_threshold: 权重阈值
        min_slices: 最小切片数量
        max_slices: 最大切片数量
    
    Returns:
        dict: 包含切片数据和骨骼信息
    """
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return None

    if bone_name not in armature.data.bones:
        return None

    bone = armature.data.bones[bone_name]
    
    # 获取骨骼世界坐标
    bone_head_world = armature.matrix_world @ bone.head_local
    bone_tail_world = armature.matrix_world @ bone.tail_local
    
    # 计算骨骼主轴方向
    bone_axis = (bone_tail_world - bone_head_world).normalized()
    
    # 收集顶点及其权重
    vertices_world = []
    weights = []
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > weight_threshold:
                    vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    weights.append(group.weight)
                    break

    if not vertices_world:
        return None

    # 计算顶点在主轴方向上的投影
    projections = [v.dot(bone_axis) for v in vertices_world]
    min_proj, max_proj = min(projections), max(projections)
    total_length = max_proj - min_proj
    
    # 根据骨骼长度调整切片数量
    ideal_slices = max(min_slices, min(max_slices, int(total_length / slice_interval)))
    adjusted_interval = total_length / (ideal_slices + 1)
    
    # 确定切片位置
    slice_positions = []
    for i in range(1, ideal_slices + 1):
        slice_positions.append(min_proj + adjusted_interval * i)

    # 提取每个切片的顶点
    slices = []
    for pos in slice_positions:
        slice_vertices = []
        slice_weights = []
        for v, w, proj in zip(vertices_world, weights, projections):
            if abs(proj - pos) < adjusted_interval:
                slice_vertices.append(v)
                slice_weights.append(w)
        
        if slice_vertices:
            slices.append({
                'position': pos,
                'vertices': slice_vertices,
                'weights': slice_weights,
                'world_position': bone_head_world + bone_axis * pos
            })

    return {
        'bone_name': bone_name,
        'bone_head_world': bone_head_world,
        'bone_tail_world': bone_tail_world,
        'bone_axis': bone_axis,
        'slices': slices,
        'total_vertices': len(vertices_world),
        'bone_length': total_length
    }


def fit_ellipse_to_slice_general(slice_data, bone_axis):
    """
    对单个切片进行PCA椭圆拟合（通用版本）
    
    Args:
        slice_data: 切片数据字典
        bone_axis: 骨骼主轴方向
    
    Returns:
        dict: 椭圆参数（中心、长轴、短轴、旋转角度）
    """
    vertices = slice_data['vertices']
    weights = slice_data['weights']
    
    if len(vertices) < 3:
        return None
    
    # 计算加权质心
    total_weight = sum(weights)
    if total_weight < 0.001:
        return None
    
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    
    # 构建垂直于骨骼主轴的平面坐标系
    if abs(bone_axis.y) < 0.9:
        u_axis = Vector((0, 1, 0)).cross(bone_axis).normalized()
    else:
        u_axis = Vector((1, 0, 0)).cross(bone_axis).normalized()
    v_axis = bone_axis.cross(u_axis).normalized()
    
    # 将顶点投影到切片平面
    projected_points = []
    for v in vertices:
        diff = v - center
        u = diff.dot(u_axis)
        v_val = diff.dot(v_axis)
        projected_points.append((u, v_val))
    
    # 计算协方差矩阵
    n = len(projected_points)
    if n < 3:
        return None
    
    mean_u = sum(p[0] for p in projected_points) / n
    mean_v = sum(p[1] for p in projected_points) / n
    
    cov_uu = sum((p[0] - mean_u) ** 2 for p in projected_points) / n
    cov_vv = sum((p[1] - mean_v) ** 2 for p in projected_points) / n
    cov_uv = sum((p[0] - mean_u) * (p[1] - mean_v) for p in projected_points) / n
    
    # 求解特征值和特征向量
    trace = cov_uu + cov_vv
    det = cov_uu * cov_vv - cov_uv ** 2
    
    if det < 0:
        det = 0
    
    sqrt_term = math.sqrt(trace ** 2 / 4 - det)
    lambda1 = trace / 2 + sqrt_term
    lambda2 = trace / 2 - sqrt_term
    
    # 长轴和短轴
    major_axis_length = math.sqrt(lambda1) * 2 if lambda1 > 0 else 0.01
    minor_axis_length = math.sqrt(lambda2) * 2 if lambda2 > 0 else 0.01
    
    # 计算长轴方向角
    if cov_uu == cov_vv:
        angle = 0
    else:
        angle = 0.5 * math.atan(2 * cov_uv / (cov_uu - cov_vv))
    
    # 计算最大距离作为椭圆半径（增加安全系数）
    max_dist_u = max(abs(p[0]) for p in projected_points) * 1.15
    max_dist_v = max(abs(p[1]) for p in projected_points) * 1.15
    
    return {
        'center': center,
        'major_axis_length': max(major_axis_length, max_dist_u),
        'minor_axis_length': max(minor_axis_length, max_dist_v),
        'angle': angle,
        'u_axis': u_axis,
        'v_axis': v_axis,
        'projected_points': projected_points,
        'vertex_count': len(vertices)
    }


def calculate_weighted_center(slice_data, bone_axis, side_weight_factor=2.0, side_direction='posterior'):
    """
    计算考虑特定方向隆起的加权中心（通用版本）
    
    Args:
        slice_data: 切片数据字典
        bone_axis: 骨骼主轴方向
        side_weight_factor: 特定方向权重系数
        side_direction: 权重增加的方向 ('posterior', 'anterior', 'left', 'right')
    
    Returns:
        Vector: 加权中心
    """
    vertices = slice_data['vertices']
    weights = slice_data['weights']
    
    if len(vertices) < 3:
        return None
    
    # 计算基础质心
    total_weight = sum(weights)
    if total_weight < 0.001:
        return None
    
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    
    # 确定权重增加方向
    if abs(bone_axis.y) < 0.9:
        posterior_dir = Vector((0, 0, 1)).cross(bone_axis).normalized()
    else:
        posterior_dir = Vector((0, 0, 1))
    
    if side_direction == 'posterior':
        weight_dir = posterior_dir
    elif side_direction == 'anterior':
        weight_dir = -posterior_dir
    elif side_direction == 'left':
        weight_dir = bone_axis.cross(posterior_dir).normalized()
    elif side_direction == 'right':
        weight_dir = -bone_axis.cross(posterior_dir).normalized()
    else:
        weight_dir = posterior_dir
    
    # 计算加权质心
    weighted_center = Vector((0, 0, 0))
    total_weighted = 0.0
    
    for v, w in zip(vertices, weights):
        diff = v - center
        side_factor = diff.dot(weight_dir)
        
        if side_factor > 0:
            weight = w * side_weight_factor
        else:
            weight = w
        
        weighted_center += v * weight
        total_weighted += weight
    
    if total_weighted > 0:
        weighted_center /= total_weighted
    
    return weighted_center


# ===========================================================================
# =                        6.1 四肢横截面分析（手臂/腿部）                      =
# ===========================================================================

def generate_limb_rigid_bodies(armature, bone_name, limb_type='leg', slice_interval=0.025):
    """
    生成四肢（手臂/腿部）多段胶囊体刚体
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼名称
        limb_type: 四肢类型 ('arm', 'leg')
        slice_interval: 切片间距
    
    Returns:
        dict: 刚体参数列表
    """
    # 根据四肢类型调整参数
    if limb_type == 'arm':
        min_slices, max_slices = 4, 8
        segment_count = 2  # 手臂分为两段
    else:  # leg
        min_slices, max_slices = 5, 10
        segment_count = 3  # 腿部分为三段
    
    # 提取横截面切片
    section_data = extract_cross_sections(armature, bone_name, slice_interval, min_slices=min_slices, max_slices=max_slices)
    if not section_data or not section_data['slices']:
        return None
    
    slices = section_data['slices']
    bone_axis = section_data['bone_axis']
    
    # 对每个切片进行椭圆拟合
    ellipse_params = []
    for slice_data in slices:
        ellipse = fit_ellipse_to_slice_general(slice_data, bone_axis)
        if ellipse:
            ellipse_params.append(ellipse)
    
    if len(ellipse_params) < segment_count:
        return None
    
    # 将切片分组
    group_size = len(ellipse_params) // segment_count
    groups = []
    
    for i in range(segment_count):
        start = i * group_size
        end = (i + 1) * group_size if i < segment_count - 1 else len(ellipse_params)
        if start < end:
            groups.append(ellipse_params[start:end])
    
    if len(groups) < segment_count:
        return None
    
    # 生成段名称后缀
    if segment_count == 2:
        group_names = ["上", "下"]
    else:
        group_names = ["上", "中", "下"]
    
    # 为每个组计算刚体参数
    rigid_body_params = []
    
    for i, (group, name_suffix) in enumerate(zip(groups, group_names)):
        if not group:
            continue
        
        avg_center = sum(e['center'] for e in group) / len(group)
        avg_major = sum(e['major_axis_length'] for e in group) / len(group)
        avg_minor = sum(e['minor_axis_length'] for e in group) / len(group)
        
        first_center = group[0]['center']
        last_center = group[-1]['center']
        length = (last_center - first_center).dot(bone_axis)
        length = max(length, 0.02)
        
        u_axis = group[0]['u_axis']
        v_axis = group[0]['v_axis']
        
        rot_matrix = Matrix((
            u_axis,
            bone_axis,
            v_axis
        )).transposed()
        
        rigid_body_params.append({
            'name': f"{bone_name}_{name_suffix}",
            'center': avg_center,
            'length': length,
            'radius_x': avg_minor / 2,
            'radius_y': avg_major / 2,
            'rotation_matrix': rot_matrix,
            'euler_rotation': rot_matrix.to_euler('YXZ'),
            'slice_count': len(group),
            'segment_type': limb_type
        })
    
    return {
        'bone_name': bone_name,
        'bone_axis': bone_axis,
        'slices': slices,
        'ellipse_params': ellipse_params,
        'rigid_bodies': rigid_body_params,
        'limb_type': limb_type
    }


# ===========================================================================
# =                        6.2 躯干横截面分析                                  =
# ===========================================================================

def generate_torso_rigid_bodies(armature, bone_name, slice_interval=0.03):
    """
    生成躯干多段胶囊体刚体
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼名称（如脊椎骨）
        slice_interval: 切片间距
    
    Returns:
        dict: 刚体参数列表
    """
    # 躯干通常分为更多段
    section_data = extract_cross_sections(armature, bone_name, slice_interval, min_slices=6, max_slices=12)
    if not section_data or not section_data['slices']:
        return None
    
    slices = section_data['slices']
    bone_axis = section_data['bone_axis']
    
    # 对每个切片进行椭圆拟合
    ellipse_params = []
    for slice_data in slices:
        ellipse = fit_ellipse_to_slice_general(slice_data, bone_axis)
        if ellipse:
            ellipse_params.append(ellipse)
    
    if len(ellipse_params) < 4:
        return None
    
    # 躯干分为4-5段
    segment_count = min(5, max(4, len(ellipse_params) // 2))
    group_size = len(ellipse_params) // segment_count
    
    groups = []
    for i in range(segment_count):
        start = i * group_size
        end = (i + 1) * group_size if i < segment_count - 1 else len(ellipse_params)
        if start < end:
            groups.append(ellipse_params[start:end])
    
    if len(groups) < segment_count:
        return None
    
    group_names = ["上", "中上", "中下", "下"] if segment_count == 4 else ["上", "中上", "中", "中下", "下"]
    
    rigid_body_params = []
    
    for i, (group, name_suffix) in enumerate(zip(groups, group_names)):
        if not group:
            continue
        
        avg_center = sum(e['center'] for e in group) / len(group)
        avg_major = sum(e['major_axis_length'] for e in group) / len(group)
        avg_minor = sum(e['minor_axis_length'] for e in group) / len(group)
        
        first_center = group[0]['center']
        last_center = group[-1]['center']
        length = (last_center - first_center).dot(bone_axis)
        length = max(length, 0.02)
        
        u_axis = group[0]['u_axis']
        v_axis = group[0]['v_axis']
        
        rot_matrix = Matrix((
            u_axis,
            bone_axis,
            v_axis
        )).transposed()
        
        rigid_body_params.append({
            'name': f"{bone_name}_{name_suffix}",
            'center': avg_center,
            'length': length,
            'radius_x': avg_minor / 2,
            'radius_y': avg_major / 2,
            'rotation_matrix': rot_matrix,
            'euler_rotation': rot_matrix.to_euler('YXZ'),
            'slice_count': len(group),
            'segment_type': 'torso'
        })
    
    return {
        'bone_name': bone_name,
        'bone_axis': bone_axis,
        'slices': slices,
        'ellipse_params': ellipse_params,
        'rigid_bodies': rigid_body_params,
        'limb_type': 'torso'
    }


# ===========================================================================
# =                        6.3 小腿横截面分析（保持向后兼容）                   =
# ===========================================================================

def extract_calf_cross_sections(armature, bone_name, slice_interval=0.025, weight_threshold=0.001):
    """
    沿小腿骨骼主轴方向提取横截面切片
    
    Args:
        armature: 骨架对象
        bone_name: 小腿骨骼名称
        slice_interval: 切片间距（米），默认为2.5厘米
        weight_threshold: 权重阈值
    
    Returns:
        dict: 包含切片数据和骨骼信息
    """
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return None

    if bone_name not in armature.data.bones:
        return None

    bone = armature.data.bones[bone_name]
    
    # 获取骨骼世界坐标
    bone_head_world = armature.matrix_world @ bone.head_local
    bone_tail_world = armature.matrix_world @ bone.tail_local
    
    # 计算骨骼主轴方向（从膝盖到脚踝）
    bone_axis = (bone_tail_world - bone_head_world).normalized()
    
    # 收集顶点及其权重
    vertices_world = []
    weights = []
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > weight_threshold:
                    vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    weights.append(group.weight)
                    break

    if not vertices_world:
        return None

    # 计算顶点在主轴方向上的投影
    projections = [v.dot(bone_axis) for v in vertices_world]
    min_proj, max_proj = min(projections), max(projections)
    
    # 确定切片位置
    slice_positions = []
    current_pos = min_proj + slice_interval
    while current_pos < max_proj - slice_interval:
        slice_positions.append(current_pos)
        current_pos += slice_interval
    
    # 如果切片太少，至少保留5个切片
    if len(slice_positions) < 5:
        slice_positions = [min_proj + (max_proj - min_proj) * (i + 1) / 6 for i in range(5)]

    # 提取每个切片的顶点
    slices = []
    for pos in slice_positions:
        slice_vertices = []
        slice_weights = []
        for v, w, proj in zip(vertices_world, weights, projections):
            if abs(proj - pos) < slice_interval:
                slice_vertices.append(v)
                slice_weights.append(w)
        
        if slice_vertices:
            slices.append({
                'position': pos,
                'vertices': slice_vertices,
                'weights': slice_weights,
                'world_position': bone_head_world + bone_axis * pos
            })

    return {
        'bone_name': bone_name,
        'bone_head_world': bone_head_world,
        'bone_tail_world': bone_tail_world,
        'bone_axis': bone_axis,
        'slices': slices,
        'total_vertices': len(vertices_world)
    }


def fit_ellipse_to_slice(slice_data, bone_axis):
    """
    对单个切片进行PCA椭圆拟合
    
    Args:
        slice_data: 切片数据字典
        bone_axis: 骨骼主轴方向
    
    Returns:
        dict: 椭圆参数（中心、长轴、短轴、旋转角度）
    """
    vertices = slice_data['vertices']
    weights = slice_data['weights']
    
    if len(vertices) < 3:
        return None
    
    # 计算加权质心
    total_weight = sum(weights)
    if total_weight < 0.001:
        return None
    
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    
    # 构建垂直于骨骼主轴的平面坐标系
    # 找到两个正交于bone_axis的向量
    if abs(bone_axis.y) < 0.9:
        u_axis = Vector((0, 1, 0)).cross(bone_axis).normalized()
    else:
        u_axis = Vector((1, 0, 0)).cross(bone_axis).normalized()
    v_axis = bone_axis.cross(u_axis).normalized()
    
    # 将顶点投影到切片平面
    projected_points = []
    for v in vertices:
        diff = v - center
        u = diff.dot(u_axis)
        v_val = diff.dot(v_axis)
        projected_points.append((u, v_val))
    
    # 计算协方差矩阵
    n = len(projected_points)
    if n < 3:
        return None
    
    mean_u = sum(p[0] for p in projected_points) / n
    mean_v = sum(p[1] for p in projected_points) / n
    
    cov_uu = sum((p[0] - mean_u) ** 2 for p in projected_points) / n
    cov_vv = sum((p[1] - mean_v) ** 2 for p in projected_points) / n
    cov_uv = sum((p[0] - mean_u) * (p[1] - mean_v) for p in projected_points) / n
    
    # 求解特征值和特征向量
    trace = cov_uu + cov_vv
    det = cov_uu * cov_vv - cov_uv ** 2
    
    if det < 0:
        det = 0
    
    sqrt_term = math.sqrt(trace ** 2 / 4 - det)
    lambda1 = trace / 2 + sqrt_term
    lambda2 = trace / 2 - sqrt_term
    
    # 长轴和短轴
    major_axis_length = math.sqrt(lambda1) * 2 if lambda1 > 0 else 0.01
    minor_axis_length = math.sqrt(lambda2) * 2 if lambda2 > 0 else 0.01
    
    # 计算长轴方向角
    if cov_uu == cov_vv:
        angle = 0
    else:
        angle = 0.5 * math.atan(2 * cov_uv / (cov_uu - cov_vv))
    
    # 计算最大距离作为椭圆半径
    max_dist_u = max(abs(p[0]) for p in projected_points) * 1.1
    max_dist_v = max(abs(p[1]) for p in projected_points) * 1.1
    
    return {
        'center': center,
        'major_axis_length': max(major_axis_length, max_dist_u),
        'minor_axis_length': max(minor_axis_length, max_dist_v),
        'angle': angle,
        'u_axis': u_axis,
        'v_axis': v_axis,
        'projected_points': projected_points,
        'vertex_count': len(vertices)
    }


def calculate_weighted_curvature_center(slice_data, bone_axis, posterior_weight=2.0):
    """
    计算考虑肌肉隆起的加权曲率中心
    
    Args:
        slice_data: 切片数据字典
        bone_axis: 骨骼主轴方向
        posterior_weight: 后侧肌肉权重系数
    
    Returns:
        Vector: 加权曲率中心
    """
    vertices = slice_data['vertices']
    weights = slice_data['weights']
    
    if len(vertices) < 3:
        return None
    
    # 计算基础质心
    total_weight = sum(weights)
    if total_weight < 0.001:
        return None
    
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    
    # 确定前后方向（小腿后侧通常是肌肉隆起处）
    if abs(bone_axis.y) < 0.9:
        posterior_dir = Vector((0, 0, 1)).cross(bone_axis).normalized()
    else:
        posterior_dir = Vector((0, 0, 1))
    
    # 计算加权质心，后侧顶点权重更高
    weighted_center = Vector((0, 0, 0))
    total_weighted = 0.0
    
    for v, w in zip(vertices, weights):
        # 计算顶点相对于中心的前后位置
        diff = v - center
        posterior_factor = diff.dot(posterior_dir)
        
        # 后侧顶点（posterior_factor > 0）权重增加
        if posterior_factor > 0:
            weight = w * posterior_weight
        else:
            weight = w
        
        weighted_center += v * weight
        total_weighted += weight
    
    if total_weighted > 0:
        weighted_center /= total_weighted
    
    return weighted_center


def generate_calf_rigid_bodies(armature, bone_name, slice_interval=0.025):
    """
    生成小腿多段胶囊体刚体
    
    Args:
        armature: 骨架对象
        bone_name: 小腿骨骼名称
        slice_interval: 切片间距
    
    Returns:
        dict: 刚体参数列表
    """
    # 提取横截面切片
    section_data = extract_calf_cross_sections(armature, bone_name, slice_interval)
    if not section_data or not section_data['slices']:
        return None
    
    slices = section_data['slices']
    bone_axis = section_data['bone_axis']
    
    # 对每个切片进行椭圆拟合
    ellipse_params = []
    for slice_data in slices:
        ellipse = fit_ellipse_to_slice(slice_data, bone_axis)
        if ellipse:
            ellipse_params.append(ellipse)
    
    if len(ellipse_params) < 3:
        return None
    
    # 将切片分为三组（小腿上、小腿中、小腿下）
    group_size = len(ellipse_params) // 3
    groups = []
    
    for i in range(3):
        start = i * group_size
        end = (i + 1) * group_size if i < 2 else len(ellipse_params)
        if start < end:
            groups.append(ellipse_params[start:end])
    
    # 如果分组不均匀，调整最后一组
    if len(groups) < 3:
        return None
    
    # 为每个组计算刚体参数
    rigid_body_params = []
    group_names = ["上", "中", "下"]
    
    for i, (group, name_suffix) in enumerate(zip(groups, group_names)):
        if not group:
            continue
        
        # 计算组内椭圆参数的平均值
        avg_center = sum(e['center'] for e in group) / len(group)
        avg_major = sum(e['major_axis_length'] for e in group) / len(group)
        avg_minor = sum(e['minor_axis_length'] for e in group) / len(group)
        avg_angle = sum(e['angle'] for e in group) / len(group)
        
        # 计算刚体长度（沿骨骼轴方向）
        first_center = group[0]['center']
        last_center = group[-1]['center']
        length = (last_center - first_center).dot(bone_axis)
        length = max(length, 0.02)
        
        # 计算旋转矩阵
        u_axis = group[0]['u_axis']
        v_axis = group[0]['v_axis']
        
        # 构建旋转矩阵
        rot_matrix = Matrix((
            u_axis,
            bone_axis,
            v_axis
        )).transposed()
        
        rigid_body_params.append({
            'name': f"{bone_name}_{name_suffix}",
            'center': avg_center,
            'length': length,
            'radius_x': avg_minor / 2,
            'radius_y': avg_major / 2,
            'rotation_matrix': rot_matrix,
            'euler_rotation': rot_matrix.to_euler('YXZ'),
            'slice_count': len(group),
            'start_slice': i * group_size,
            'end_slice': (i + 1) * group_size if i < 2 else len(ellipse_params)
        })
    
    return {
        'bone_name': bone_name,
        'bone_axis': bone_axis,
        'slices': slices,
        'ellipse_params': ellipse_params,
        'rigid_bodies': rigid_body_params
    }


class OBJECT_OT_build_limb_rigid_bodies(bpy.types.Operator):
    """构建四肢刚体系统"""
    bl_idname = "object.build_limb_rigid_bodies"
    bl_label = "构建四肢刚体"
    bl_options = {'REGISTER', 'UNDO'}

    limb_type: bpy.props.EnumProperty(
        name="四肢类型",
        description="选择要构建的四肢类型",
        items=[
            ('ARM', '手臂', '构建手臂刚体'),
            ('LEG', '腿部', '构建腿部刚体'),
            ('BOTH', '两者', '同时构建手臂和腿部刚体')
        ],
        default='BOTH'
    )

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

            # 根据选择构建四肢刚体
            if self.limb_type in ('ARM', 'BOTH'):
                self._build_arms(context, armature, root)
            
            if self.limb_type in ('LEG', 'BOTH'):
                self._build_legs(context, armature, root)

            self.report({'INFO'}, "四肢刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _build_arms(self, context, armature, root):
        """构建双臂刚体"""
        left_arm_bone = context.scene.left_arm_bone if hasattr(context.scene, "left_arm_bone") else "左上臂"
        right_arm_bone = context.scene.right_arm_bone if hasattr(context.scene, "right_arm_bone") else "右上臂"
        
        self._build_single_limb(context, armature, root, left_arm_bone, 'arm')
        self._build_single_limb(context, armature, root, right_arm_bone, 'arm')

    def _build_legs(self, context, armature, root):
        """构建双腿刚体"""
        left_leg_bone = context.scene.left_leg_bone if hasattr(context.scene, "left_leg_bone") else "左大腿"
        right_leg_bone = context.scene.right_leg_bone if hasattr(context.scene, "right_leg_bone") else "右大腿"
        left_calf_bone = context.scene.left_calf_bone if hasattr(context.scene, "left_calf_bone") else "左小腿"
        right_calf_bone = context.scene.right_calf_bone if hasattr(context.scene, "right_calf_bone") else "右小腿"
        
        self._build_single_limb(context, armature, root, left_leg_bone, 'leg')
        self._build_single_limb(context, armature, root, right_leg_bone, 'leg')
        self._build_single_limb(context, armature, root, left_calf_bone, 'leg')
        self._build_single_limb(context, armature, root, right_calf_bone, 'leg')

    def _build_single_limb(self, context, armature, root, bone_name, limb_type):
        """构建单条肢体的刚体"""
        if bone_name not in armature.data.bones:
            self.report({'WARNING'}, f"骨骼 '{bone_name}' 不存在，跳过")
            return

        rigid_params = generate_limb_rigid_bodies(armature, bone_name, limb_type)
        if not rigid_params or not rigid_params['rigid_bodies']:
            self.report({'WARNING'}, f"无法生成 {bone_name} 的刚体参数")
            return

        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        
        for rb_param in rigid_params['rigid_bodies']:
            rb_name = rb_param['name']
            
            if rb_name in bpy.data.objects:
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            
            world_center = rb_param['center']
            local_center = armature.matrix_world.inverted() @ world_center
            
            rb_obj.location = local_center
            rb_obj.rotation_euler = rb_param['euler_rotation']
            
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((rb_param['radius_x'], rb_param['length'], rb_param['radius_y']))
            
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 0.3
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            print(f"[{limb_type}刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=({rb_param['radius_x']:.4f}, {rb_param['length']:.4f}, {rb_param['radius_y']:.4f})")


class OBJECT_OT_build_torso_rigid_bodies(bpy.types.Operator):
    """构建躯干刚体系统"""
    bl_idname = "object.build_torso_rigid_bodies"
    bl_label = "构建躯干刚体"
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

            torso_bone = context.scene.torso_bone if hasattr(context.scene, "torso_bone") else "脊椎"
            
            self._build_torso(context, armature, root, torso_bone)

            self.report({'INFO'}, "躯干刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _build_torso(self, context, armature, root, bone_name):
        """构建躯干刚体"""
        if bone_name not in armature.data.bones:
            self.report({'WARNING'}, f"骨骼 '{bone_name}' 不存在，跳过")
            return

        rigid_params = generate_torso_rigid_bodies(armature, bone_name)
        if not rigid_params or not rigid_params['rigid_bodies']:
            self.report({'WARNING'}, f"无法生成 {bone_name} 的刚体参数")
            return

        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        
        for rb_param in rigid_params['rigid_bodies']:
            rb_name = rb_param['name']
            
            if rb_name in bpy.data.objects:
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            
            world_center = rb_param['center']
            local_center = armature.matrix_world.inverted() @ world_center
            
            rb_obj.location = local_center
            rb_obj.rotation_euler = rb_param['euler_rotation']
            
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((rb_param['radius_x'], rb_param['length'], rb_param['radius_y']))
            
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 0.5
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            print(f"[躯干刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=({rb_param['radius_x']:.4f}, {rb_param['length']:.4f}, {rb_param['radius_y']:.4f})")


class OBJECT_OT_build_calf_rigid_bodies(bpy.types.Operator):
    """构建小腿刚体系统（向后兼容）"""
    bl_idname = "object.build_calf_rigid_bodies"
    bl_label = "构建小腿刚体"
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

            left_calf_bone = context.scene.left_calf_bone if hasattr(context.scene, "left_calf_bone") else "左小腿"
            right_calf_bone = context.scene.right_calf_bone if hasattr(context.scene, "right_calf_bone") else "右小腿"

            if not left_calf_bone or not right_calf_bone:
                self.report({'ERROR'}, "请先设置小腿骨骼名称")
                return {'CANCELLED'}

            self._build_single_calf(context, armature, root, left_calf_bone)
            self._build_single_calf(context, armature, root, right_calf_bone)

            self.report({'INFO'}, "小腿刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _build_single_calf(self, context, armature, root, bone_name):
        """构建单条小腿的刚体"""
        if bone_name not in armature.data.bones:
            self.report({'WARNING'}, f"骨骼 '{bone_name}' 不存在，跳过")
            return

        rigid_params = generate_limb_rigid_bodies(armature, bone_name, 'leg')
        if not rigid_params or not rigid_params['rigid_bodies']:
            self.report({'WARNING'}, f"无法生成 {bone_name} 的刚体参数")
            return

        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        
        for rb_param in rigid_params['rigid_bodies']:
            rb_name = rb_param['name']
            
            if rb_name in bpy.data.objects:
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            
            world_center = rb_param['center']
            local_center = armature.matrix_world.inverted() @ world_center
            
            rb_obj.location = local_center
            rb_obj.rotation_euler = rb_param['euler_rotation']
            
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((rb_param['radius_x'], rb_param['length'], rb_param['radius_y']))
            
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 0.3
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            print(f"[小腿刚体] 创建: {rb_name}, 位置={local_center}, 尺寸=({rb_param['radius_x']:.4f}, {rb_param['length']:.4f}, {rb_param['radius_y']:.4f})")


# ===========================================================================
# =                        3. 注册/反注册函数                                 =
# ===========================================================================

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(OBJECT_OT_build_body_rigid_bodies)
    bpy.utils.register_class(OBJECT_OT_build_limb_rigid_bodies)
    bpy.utils.register_class(OBJECT_OT_build_torso_rigid_bodies)
    bpy.utils.register_class(OBJECT_OT_build_calf_rigid_bodies)
    
    # 乳房物理属性
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(name="左胸部骨骼", default="")
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(name="右胸部骨骼", default="")
    
    # 四肢物理属性
    if not hasattr(bpy.types.Scene, "left_arm_bone"):
        bpy.types.Scene.left_arm_bone = bpy.props.StringProperty(name="左上臂骨骼", default="左上臂")
    if not hasattr(bpy.types.Scene, "right_arm_bone"):
        bpy.types.Scene.right_arm_bone = bpy.props.StringProperty(name="右上臂骨骼", default="右上臂")
    if not hasattr(bpy.types.Scene, "left_leg_bone"):
        bpy.types.Scene.left_leg_bone = bpy.props.StringProperty(name="左大腿骨骼", default="左大腿")
    if not hasattr(bpy.types.Scene, "right_leg_bone"):
        bpy.types.Scene.right_leg_bone = bpy.props.StringProperty(name="右大腿骨骼", default="右大腿")
    if not hasattr(bpy.types.Scene, "left_calf_bone"):
        bpy.types.Scene.left_calf_bone = bpy.props.StringProperty(name="左小腿骨骼", default="左小腿")
    if not hasattr(bpy.types.Scene, "right_calf_bone"):
        bpy.types.Scene.right_calf_bone = bpy.props.StringProperty(name="右小腿骨骼", default="右小腿")
    
    # 躯干物理属性
    if not hasattr(bpy.types.Scene, "torso_bone"):
        bpy.types.Scene.torso_bone = bpy.props.StringProperty(name="躯干骨骼", default="脊椎")


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(OBJECT_OT_build_body_rigid_bodies)
    bpy.utils.unregister_class(OBJECT_OT_build_limb_rigid_bodies)
    bpy.utils.unregister_class(OBJECT_OT_build_torso_rigid_bodies)
    bpy.utils.unregister_class(OBJECT_OT_build_calf_rigid_bodies)


if __name__ == "__main__":
    register()
