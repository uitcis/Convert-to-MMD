"""
胸物理构建模块

包含：
    1. 乳房球形拟合算法
    2. 胸部刚体参数定义
    3. OBJECT_OT_auto_physics_builder 操作符（骨骼链/刚体/弹簧）
"""

import bpy
import math

from mathutils import Vector, Euler

from .physics_utils import (
    _check_memory_and_gc, MMD_TOOLS_AVAILABLE, FnRigidBody, FnModel
)
from .. import bone_utils


# ===========================================================================
# =                        乳房专用工具函数                                =
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
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    if not mesh_objs:
        return None

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

    bone_exists = bone_name in armature.data.bones or (
        hasattr(armature.data, 'edit_bones') and bone_name in armature.data.edit_bones
    )
    if not vertices_world or not bone_exists:
        return None

    total_weight = sum(weights)
    if total_weight == 0:
        return None

    center_x = sum(v.x * w for v, w in zip(vertices_world, weights)) / total_weight
    center_y = sum(v.y * w for v, w in zip(vertices_world, weights)) / total_weight
    center_z = sum(v.z * w for v, w in zip(vertices_world, weights)) / total_weight
    center = Vector((center_x, center_y, center_z))

    total_distance = sum((v - center).length * w for v, w in zip(vertices_world, weights))
    radius = total_distance / total_weight

    return {
        'center': center,
        'radius': radius,
        'vertex_count': len(vertices_world),
        'total_weight': total_weight
    }


# ===========================================================================
# =                        乳房刚体构建代码                                =
# ===========================================================================

DEG5 = 0.0872665
DEG10 = 0.174533
DEG20 = 0.349066

COLLISION_GROUP_MASK_0 = [True] * 16
COLLISION_GROUP_MASK_2 = [True] * 16

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
             "size_x": 0.5, "size_y": 1, "size_z": 0.0},
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
        except MemoryError as me:
            self.report({'ERROR'}, str(me))
            print(f"内存错误: {me}")
            return {'CANCELLED'}

        return {'FINISHED'}

    # 乳房骨骼链构建
    def _build_breast_bone_chain(self, context, armature, left_bone, right_bone):
        scene = context.scene
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones

        # 胸親骨骼 - 确定参考骨骼用于定位
        breast_parent_name = scene.breast_parent_bone if getattr(scene, 'breast_parent_bone', None) else None
        if breast_parent_name and breast_parent_name in eb:
            reference_bone = eb[breast_parent_name]
        else:
            # Fallback: 使用左/右胸骨骼作为位置参考
            reference_bone = eb.get(left_bone) or eb.get(right_bone)
            if reference_bone is None:
                self.report({'ERROR'}, "未找到胸親父级骨骼或胸部骨骼")
                bpy.ops.object.mode_set(mode='OBJECT')
                return {'CANCELLED'}
        reference_y = reference_bone.head.y
        reference_z = reference_bone.head.z

        BrP_head = Vector((0, reference_y, reference_z))
        BrP_tail = BrP_head + Vector((0, 0, 0.08))

        BrP = bone_utils.create_or_update_bone(
            edit_bones=eb, name="胸親",
            head_position=BrP_head, tail_position=BrP_tail,
            use_connect=False, parent_name=breast_parent_name, use_deform=True
        )

        # 作用：胸上2骨骼
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

            original_bone_x = BrUp2.head.x
            original_bone_y = BrUp2.head.y

            br_up2_head_z = breast_center.z + breast_radius
            br_up2_tail_z = breast_center.z - breast_radius

            BrUp2.head = Vector((breast_center.x, breast_center.y, br_up2_head_z))
            BrUp2.tail = Vector((breast_center.x, breast_center.y, br_up2_tail_z))

            BrUp_head = Vector((original_bone_x, original_bone_y, br_up2_head_z))
            bone_utils.create_or_update_bone(edit_bones=eb, name=BrUp_name,
                                            head_position=BrUp_head, tail_position=BrUp2.head,
                                            use_connect=False, parent_name=None, use_deform=True)
            BrUp2.parent = eb[BrUp_name]

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

    # 乳房刚体构建
    def _create_rigid_bodies(self, context, armature, breast_data):
        if not MMD_TOOLS_AVAILABLE:
            self.report({'ERROR'}, "mmd_tools 未安装，请先安装 mmd_tools 扩展")
            return None

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
            rb_parent.rotation_euler = Euler((0, -math.pi / 2, 0), 'YXZ')

            left_radius = breast_data["左"]['radius']
            right_radius = breast_data["右"]['radius']
            avg_radius = (left_radius + right_radius) / 2
            x_distance = abs(left_rb.location.x - right_rb.location.x)
            rb_parent.mmd_rigid.size = Vector((avg_radius, x_distance, 0.0))

        return rb_objects

    # 乳房弹簧构建
    def _create_spring_joints(self, context, armature, rb_objects):
        if not MMD_TOOLS_AVAILABLE:
            self.report({'ERROR'}, "mmd_tools 未安装，请先安装 mmd_tools 扩展")
            return None

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

    # 乳房弹簧定义
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


def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)


if __name__ == "__main__":
    register()
