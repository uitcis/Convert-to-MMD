"""
自动物理构建器
包含乳房物理和身体刚体构建功能

代码结构：
    1. 通用基础工具函数
    2. 乳房专用工具函数
    3. 乳房刚体构建代码
    4. 身体专用工具函数
    5. 身体刚体构建代码
    6. 注册/反注册函数
"""
import bpy
import math
from mathutils import Vector, Euler
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
# =                        3. 身体专用工具函数                                 =
# ===========================================================================

def calculate_bone_rigid_size(armature, bone_name):
    """计算骨骼刚体尺寸（主入口）"""
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

    # 1. 计算加权质心
    center = _calc_weighted_center(vertices, weights)
    
    # 2. 计算主轴方向（PCA）
    pca_result = _calc_principal_axis(vertices, weights, center)
    principal_axis, axis = pca_result['principal_axis'], pca_result['axis']
    
    # 3. 计算长度和半径
    size_result = _calc_length_and_radius(vertices, weights, center, principal_axis)
    
    # 4. 计算刚体分段
    segment_result = _calc_rigid_body_segments(vertices, weights, principal_axis)

    count = segment_result['count']
    segments = segment_result['segments']
    positions = [0.0] if count == 1 else [(s['center'] - center).dot(principal_axis) for s in segments]

    return {'radius': size_result['radius'], 'length': size_result['length'], 'axis': axis, 'count': count, 'positions': positions, 'center': center, 'principal_axis': principal_axis, 'rotation_matrix': pca_result['rotation_matrix'], 'segments': segments}


def _calc_weighted_center(vertices, weights):
    """计算加权质心"""
    total_weight = sum(weights)
    if total_weight < 0.001:
        return Vector((0, 0, 0))
    center = Vector((0, 0, 0))
    for v, w in zip(vertices, weights):
        center += v * w
    center /= total_weight
    return center


def _calc_principal_axis(vertices, weights, center):
    """通过协方差矩阵计算主轴方向"""
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


def _calc_length_and_radius(vertices, weights, center, principal_axis):
    """计算长度和半径"""
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


def _extract_centerline(vertices, weights, principal_axis, slices=20):
    """提取中心线"""
    if not vertices or not weights:
        return []

    projections = [v.dot(principal_axis) for v in vertices]
    min_proj, max_proj = min(projections), max(projections)

    if max_proj - min_proj < 0.001:
        return [_calc_weighted_center(vertices, weights)]

    step = (max_proj - min_proj) / slices
    centerline = []

    for i in range(slices):
        slice_start, slice_end = min_proj + i * step, min_proj + (i + 1) * step
        slice_vertices = [v for v, w, proj in zip(vertices, weights, projections) if slice_start <= proj <= slice_end]
        slice_weights = [w for v, w, proj in zip(vertices, weights, projections) if slice_start <= proj <= slice_end]
        if slice_vertices:
            centerline.append(_calc_weighted_center(slice_vertices, slice_weights))

    return centerline


def _calc_curvature(centerline):
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


def _segment_by_curvature(centerline, curvature, max_length=0.15, curvature_threshold=50.0):
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


def _calc_rigid_body_segments(vertices, weights, principal_axis, max_length=0.15, curvature_threshold=50.0):
    """计算刚体分段"""
    centerline = _extract_centerline(vertices, weights, principal_axis)

    if len(centerline) <= 1:
        return {'count': 1, 'segments': [{'start': 0, 'end': 0, 'length': 0.0}]}

    curvature = _calc_curvature(centerline)
    segment_indices = _segment_by_curvature(centerline, curvature, max_length, curvature_threshold)

    segments = []
    for i in range(len(segment_indices) - 1):
        start_idx, end_idx = segment_indices[i], segment_indices[i + 1]
        segment_length = sum((centerline[j + 1] - centerline[j]).length for j in range(start_idx, end_idx))
        segments.append({
            'start': start_idx, 'end': end_idx, 'length': segment_length,
            'center': (centerline[start_idx] + centerline[end_idx]) / 2
        })

    return {'count': len(segments), 'segments': segments, 'total_length': sum(s['length'] for s in segments), 'centerline': centerline}


# ===========================================================================
# =                        4. 身体刚体构建代码                                =
# ===========================================================================

class OBJECT_OT_build_body_rigid_bodies(bpy.types.Operator):
    bl_idname = "object.build_body_rigid_bodies"
    bl_label = "构建身体刚体"
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

            self._create_body_rigid_bodies(context, armature, root)
            self.report({'INFO'}, "身体刚体系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _create_body_rigid_bodies(self, context, armature, root):
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)

        for bone in armature.data.bones:
            bone_length = (bone.tail_local - bone.head_local).length
            if bone_length < 0.01:
                continue

            rigid_params = calculate_bone_rigid_size(armature, bone.name)
            if rigid_params['count'] == 0 or rigid_params['radius'] == 0.0:
                continue

            print(f"[身体刚体] {bone.name}: 半径={rigid_params['radius']:.4f}, 长度={rigid_params['length']:.4f}, 数量={rigid_params['count']}")
            self._create_bone_rigid_bodies(context, armature, bone, rigid_params, rigid_grp_obj)

    def _create_bone_rigid_bodies(self, context, armature, bone, params, parent_obj):
        bone_center = (bone.head_local + bone.tail_local) / 2
        bone_rot_matrix = bone.matrix_local.to_3x3()
        bone_rot = bone.matrix_local.to_euler("YXZ")
        bone_rot.rotate_axis("X", math.pi / 2)

        for i in range(params['count']):
            rb_name = f"{bone.name}_{i + 1}" if params['count'] > 1 else bone.name
            if rb_name in bpy.data.objects:
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, parent_obj)

            pos_offset = params['positions'][i] if i < len(params['positions']) else 0.0
            axis = params['axis']
            local_offset = Vector((pos_offset, 0, 0)) if axis == 'X' else Vector((0, pos_offset, 0)) if axis == 'Y' else Vector((0, 0, pos_offset))
            skeleton_offset = bone_rot_matrix @ local_offset

            rb_obj.location = bone_center + skeleton_offset
            rb_obj.rotation_euler = bone_rot
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((params['radius'], params['length'], 0.0))
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone.name

            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 1.0 / params['count']
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0


# ===========================================================================
# =                        5. 注册/反注册函数                                 =
# ===========================================================================

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(OBJECT_OT_build_body_rigid_bodies)
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(name="左胸部骨骼", default="")
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(name="右胸部骨骼", default="")


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(OBJECT_OT_build_body_rigid_bodies)


if __name__ == "__main__":
    register()
