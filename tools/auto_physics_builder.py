"""
自动物理构建器
包含胸部物理和身体刚体构建功能

基于 MMD 标准 GENERIC_SPRING 刚体物理体系构建胸部物理，
以及为每个骨骼创建身体刚体。

使用 mmd_tools API 创建完整的刚体和约束系统。
"""
from configparser import MissingSectionHeaderError
import bpy
import math
from mathutils import Vector, Euler
from .. import bone_utils

# 导入 mmd_tools（支持 Blender 5.1+ 扩展系统）
try:
    # Blender 5.1+ 扩展系统
    from bl_ext.blender_org.mmd_tools.core.rigid_body import FnRigidBody
    from bl_ext.blender_org.mmd_tools.core.model import FnModel
except ImportError:
    try:
        # 旧版本或其他安装方式
        from mmd_tools.core.rigid_body import FnRigidBody
        from mmd_tools.core.model import FnModel
    except ImportError as e:
        print(f"导入 mmd_tools 错误 {e}")
        print("请在 Blender 扩展仓库中安装 mmd_tools 扩展")
        print("在 Blender 中执行：编辑 > 编辑偏好 > 扩展插件 > 搜索 > 'mmd_tools' > 安装")
        raise


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def get_bone_vertex_info(armature, bone_name, weight_threshold=0.001):
    """
    获取骨骼影响的顶点范围信息（骨骼局部坐标系）。
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼/顶点组名称
        weight_threshold: 权重阈值（默认0.001）
   
    Returns:
        dict {'x_min', 'x_max', 'x_range', 'y_min', 'y_max', 'y_range', 
              'z_min', 'z_max', 'z_range', 'center_local'} 或 None
    """
    # 1. 收集所有网格对象
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.parent == armature]
    
    # 校验：检查是否找到网格对象
    if not mesh_objs:
        print(f"[get_bone_vertex_info] 警告：未找到骨架 '{armature.name}' 的子网格对象")
        return None
    
    # 2. 获取权重顶点（世界坐标）
    vertices_world = []
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > weight_threshold:
                    vertices_world.append(mesh_obj.matrix_world @ Vector(vertex.co))
                    break
    
    # 校验：检查是否找到顶点
    if not vertices_world:
        return None
    
    # 3. 检查骨骼是否存在
    if bone_name not in armature.data.bones:
        return None
    
    # 获取骨骼的世界变换矩阵的逆矩阵（使用基础骨骼数据，确保与刚体创建时的坐标系一致）
    bone = armature.data.bones[bone_name]
    bone_local_matrix = (armature.matrix_world @ bone.matrix_local).inverted()
    
    # 将顶点转换到骨骼局部坐标系
    vertices_local = [bone_local_matrix @ v for v in vertices_world]
    
    # 计算各方向的最大最小值
    x_min = y_min = z_min = float('inf')
    x_max = y_max = z_max = float('-inf')
    
    for v_local in vertices_local:
        x_min = min(x_min, v_local.x)
        x_max = max(x_max, v_local.x)
        y_min = min(y_min, v_local.y)
        y_max = max(y_max, v_local.y)
        z_min = min(z_min, v_local.z)
        z_max = max(z_max, v_local.z)
    
    return {
        'x_min': x_min, 'x_max': x_max, 'x_range': x_max - x_min,
        'y_min': y_min, 'y_max': y_max, 'y_range': y_max - y_min,
        'z_min': z_min, 'z_max': z_max, 'z_range': z_max - z_min,
        'center_local': Vector(((x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2)),
    }


# ---------------------------------------------------------------------------
# 参考参数常量（胸部物理）
# ---------------------------------------------------------------------------

DEG5 = 0.0872665  # 5 度
DEG10 = 0.174533  # 10 度
DEG20 = 0.349066  # 20 度

COLLISION_GROUP_MASK_0 = [True] * 16  # 组 0（躯干）
COLLISION_GROUP_MASK_2 = [True] * 16  # 组 2（胸部物理）

CHEST_RIGID_BODIES = {
    "左胸上": {
        "shape": "CAPSULE",
        "mass": 0.05,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.01,
        "size_y": 0.02,
        "size_z": 0.0,
    },
    "右胸上": {
        "shape": "CAPSULE",
        "mass": 0.05,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.01,
        "size_y": 0.02,
        "size_z": 0.0,
    },
    "左胸上 2": {
        "shape": "SPHERE",
        "mass": 0.20,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.06,
        "size_y": 0.06,
        "size_z": 0.06,
    },
    "右胸上 2": {
        "shape": "SPHERE",
        "mass": 0.20,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.06,
        "size_y": 0.06,
        "size_z": 0.06,
    },
    "左胸下": {
        "shape": "CAPSULE",
        "mass": 0.05,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.01,
        "size_y": 0.02,
        "size_z": 0.0,
    },
    "右胸下": {
        "shape": "CAPSULE",
        "mass": 0.05,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,
        "collision_group": 2,
        "size_x": 0.01,
        "size_y": 0.02,
        "size_z": 0.0,
    },
    "胸親": {
        "shape": "CAPSULE",
        "mass": 1.0,
        "friction": 0.5,
        "linear_damping": 0.5,
        "angular_damping": 0.5,
        "is_kinematic": True,
        "collision_group": 0,
        "size_x": 0.06,
        "size_y": 0.11,
        "size_z": 0.0,
    },
}




# ---------------------------------------------------------------------------
# 胸部物理构建器
# ---------------------------------------------------------------------------

class OBJECT_OT_auto_physics_builder(bpy.types.Operator):
    """自动构建胸部物理系统"""
    bl_idname = "object.auto_physics_builder"
    bl_label = "Auto Build Chest Physics"
    bl_description = "基于 MMD 标准构建胸部物理系统"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = context.active_object
            if not armature or armature.type != 'ARMATURE':
                self.report({'ERROR'}, "请选择骨架对象")
                return {'CANCELLED'}

            left_bone = context.scene.left_chest_bone if hasattr(context.scene, "left_chest_bone") else ""
            right_bone = context.scene.right_chest_bone if hasattr(context.scene, "right_chest_bone") else ""

            if not left_bone or not right_bone:
                self.report({'ERROR'}, "请先选择左/右胸部骨骼")
                return {'CANCELLED'}

            self._build_chest_bone_chain(context, armature, left_bone, right_bone)
            rb_objects = self._create_rigid_bodies(context, armature)
            self._create_spring_joints(context, armature, rb_objects)

            bpy.ops.object.mode_set(mode='OBJECT')
            armature.select_set(True)
            context.view_layer.objects.active = armature

            self.report({'INFO'}, "胸部物理系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    def _build_chest_bone_chain(self, context, armature, left_bone, right_bone):
        scene = context.scene
        
        print(f"[胸部物理] 构建骨骼链，left='{left_bone}', right='{right_bone}'")

        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones

        if "上半身" not in eb:
            raise ValueError("缺少'上半身'骨骼，无法构建胸部物理系统")
        
        up_body_y = eb["上半身"].head.y
        
        chest_parent_name = scene.breast_parent_bone if scene.breast_parent_bone else "上半身"
        if chest_parent_name not in eb:
            print(f"[警告] 胸親父级骨骼 '{chest_parent_name}' 不存在，使用'上半身'")
            chest_parent_name = "上半身"
        
        BrP_head = Vector((0, up_body_y, eb["上半身"].head.z))
        BrP_tail = BrP_head + Vector((0, 0, 0.08))
        
        BrP = bone_utils.create_or_update_bone(
            edit_bones=eb,
            name="胸親",
            head_position=BrP_head,
            tail_position=BrP_tail,
            use_connect=False,
            parent_name=chest_parent_name,
            use_deform=True
        )
        
        print(f"[胸部物理] 胸親骨骼已创建，父级：{chest_parent_name}")
        
        for prefix, user_bone in (("左", left_bone), ("右", right_bone)):
            if user_bone not in eb:
                raise ValueError(f"骨骼 '{user_bone}' 不存在")

            BrUp2_name = f"{prefix}胸上 2"
            if user_bone != BrUp2_name:
                eb[user_bone].name = BrUp2_name

            BrUp2 = eb[BrUp2_name]
            
            bounds = get_bone_vertex_info(armature, BrUp2_name, weight_threshold=0)
            if bounds is None:
                # 如果无法获取顶点信息，使用骨骼头部的 Y 坐标作为默认值
                print(f"[警告] 无法获取骨骼 '{BrUp2_name}' 的顶点信息，使用默认位置")
                br_up2_y = BrUp2.head.y
            else:
                br_up2_y = (bounds['y_min'] + up_body_y) / 2
            
            BrUp_name = f"{prefix}胸上"
            BrDown_name = f"{prefix}胸下"
            
            original_z = BrUp2.head.z
            BrUp2.head = Vector((BrUp2.head.x, br_up2_y, original_z + 0.04))
            BrUp2.tail = Vector((BrUp2.tail.x, br_up2_y, original_z - 0.04))
            
            BrUp_head = Vector((BrUp2.head.x, up_body_y, BrUp2.head.z))
            BrUp_tail = BrUp2.head
            bone_utils.create_or_update_bone(
                edit_bones=eb,
                name=BrUp_name,
                head_position=BrUp_head,
                tail_position=BrUp_tail,
                use_connect=False,
                parent_name=None,
                use_deform=True
            )
            
            BrUp2.parent = eb[BrUp_name]

            BrDown_head = BrUp2.tail
            BrDown_tail = Vector((BrUp2.head.x, up_body_y, BrUp2.tail.z))
            bone_utils.create_or_update_bone(
                edit_bones=eb,
                name=BrDown_name,
                head_position=BrDown_head,
                tail_position=BrDown_tail,
                use_connect=False,
                parent_name=None,
                use_deform=True
            )

        for prefix in ("左", "右"):
            eb[f"{prefix}胸上"].parent = BrP
            eb[f"{prefix}胸下"].parent = BrP

        scene.left_chest_bone = "左胸上 2"
        scene.right_chest_bone = "右胸上 2"
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        print("[胸部物理] 骨骼链构建完成")

    def _create_rigid_bodies(self, context, armature):
        root = FnModel.find_root_object(armature)
        if not root:
            raise RuntimeError("未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
        
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        
        rb_objects = {}

        for bone_name, params in CHEST_RIGID_BODIES.items():
            if bone_name not in armature.data.bones:
                print(f"[胸部物理] 跳过刚体 '{bone_name}'（骨骼不存在）")
                continue

            rb_name = bone_name
            
            if rb_name in bpy.data.objects:
                rb_obj = bpy.data.objects[rb_name]
                rb_objects[bone_name] = rb_obj
                print(f"[胸部物理] 跳过已存在的：{rb_name}")
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            
            pbone = armature.pose.bones.get(bone_name)
            if not pbone:
                continue
            
            bone = pbone.bone
            
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
            
            collision_mask = COLLISION_GROUP_MASK_0 if params["collision_group"] == 0 else COLLISION_GROUP_MASK_2
            rb_obj.mmd_rigid.collision_group_mask = collision_mask
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            rb = rb_obj.rigid_body
            rb.friction = params["friction"]
            rb.mass = params["mass"]
            rb.angular_damping = params["angular_damping"]
            rb.linear_damping = params["linear_damping"]
            rb.restitution = 0.0
            
            rb_objects[bone_name] = rb_obj
            #print(f"[胸部物理] 创建：{rb_name}, type={params['shape']}, mass={params['mass']}")

        rb_parent = rb_objects.get("胸親")
        if rb_parent:
            left_up2_rb = rb_objects.get("左胸上 2")
            right_up2_rb = rb_objects.get("右胸上 2")
            
            if left_up2_rb and right_up2_rb:
                rb_parent.location = (left_up2_rb.location + right_up2_rb.location) / 2
                rb_parent.rotation_euler = Euler((0, -math.pi/2, 0), 'YXZ')
                #print(f"[胸部物理] 调整胸親位置到中心，Y 旋转 -90 度")

        return rb_objects

    def _create_spring_joints(self, context, armature, rb_objects):
        root = FnModel.find_root_object(armature)
        
        joint_grp_obj = FnModel.ensure_joint_group_object(context, root)
        
        spring_defs = self._get_spring_definitions()

        for sd in spring_defs:
            rb1 = rb_objects.get(sd["rb1"])
            rb2 = rb_objects.get(sd["rb2"])
            if rb1 is None or rb2 is None:
                print(f"[胸部物理] 跳过约束（刚体不存在）: {sd['joint']}")
                continue

            joint_name = rb2.name
            
            if joint_name in bpy.data.objects:
                obj = bpy.data.objects[joint_name]
                if obj.mmd_type == "JOINT":
                    print(f"[胸部物理] 跳过已存在的约束：{joint_name}")
                    continue
            
            joint_obj = FnRigidBody.new_joint_object(context, joint_grp_obj, FnModel.get_empty_display_size(root))
            
            mid = (rb1.location + rb2.location) / 2
            
            joint_obj = FnRigidBody.setup_joint_object(
                obj=joint_obj,
                name=rb2.name,
                name_e=rb2.name,
                location=Vector(mid),
                rotation=Euler((0, 0, 0)),
                rigid_a=rb1,
                rigid_b=rb2,
                maximum_location=Vector((sd.get("lin_x_hi", 0), sd.get("lin_y_hi", 0), sd.get("lin_z_hi", 0))),
                minimum_location=Vector((sd.get("lin_x_lo", 0), sd.get("lin_y_lo", 0), sd.get("lin_z_lo", 0))),
                maximum_rotation=Vector((sd.get("ang_x_hi", 0), sd.get("ang_y_hi", 0), sd.get("ang_z_hi", 0))),
                minimum_rotation=Vector((sd.get("ang_x_lo", 0), sd.get("ang_y_lo", 0), sd.get("ang_z_lo", 0))),
                spring_linear=Vector((sd.get("k_lin_x", 0), sd.get("k_lin_y", 0), sd.get("k_lin_z", 0))),
                spring_angular=Vector((sd.get("k_ang_x", 0), sd.get("k_ang_y", 0), sd.get("k_ang_z", 0))),
            )
            
            joint_obj.rigid_body_constraint.disable_collisions = True

            #print(f"[胸部物理] 创建弹簧：{joint_name}")

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
            defs.append(s(
                f"J.{prefix}胸上", "胸親", f"{prefix}胸上",
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_z=100,
            ))
            defs.append(s(
                f"J.{prefix}胸上 2", f"{prefix}胸上", f"{prefix}胸上 2",
            ))
            defs.append(s(
                f"J.{prefix}胸下", "胸親", f"{prefix}胸下",
                ang_x_lo=-DEG10, ang_x_hi=DEG10,
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_x=100, k_ang_z=100,
            ))

        return defs

    def _get_bone_world_pos(self, armature, bone_name):
        bone = armature.data.bones.get(bone_name)
        if not bone:
            return (0, 0, 0)
        
        local_pos = bone.head
        world_pos = armature.matrix_world @ Vector(local_pos)
        return tuple(world_pos)

# ---------------------------------------------------------------------------
# 身体刚体相关函数
# ---------------------------------------------------------------------------
#刚体尺寸计算
def calculate_bone_rigid_size(armature, bone_name):
    """
    计算骨骼刚体的尺寸，根据顶点范围动态确定刚体数量和位置。
    
    Args:
        armature: 骨架对象
        bone_name: 骨骼名称
    
    Returns:
        dict: {'radius', 'length', 'axis', 'count', 'positions'}
    """
    bounds = get_bone_vertex_info(armature, bone_name)
    
    if bounds:
        x_min, x_max = bounds['x_min'], bounds['x_max']
        y_min, y_max = bounds['y_min'], bounds['y_max']
        z_range = bounds['z_range']
        
        # 计算 X/Y 轴范围
        x_range = max(x_max - x_min, 0.001)
        y_range = max(y_max - y_min, 0.001)
        
        # 直径 = 较短轴的范围，半径 = 直径/2
        min_xy = min(x_range, y_range)
        max_xy = max(x_range, y_range)
        # 如果长轴范围小于1.2倍短短轴范围，将直径设置为长轴范围
        if max_xy/min_xy <1.2:
            min_xy = max_xy
    
        diameter = min_xy

        radius = diameter / 2
        
        # 长轴方向范围
        
        
        # 每个骨骼只创建一个刚体
        count = 1
        positions = [0.0]
        
        # 获取骨骼长度作为刚体长度（使用骨骼实际长度）
        bone_length = 1.0
        if bone_name in armature.data.bones:
            bone = armature.data.bones[bone_name]
            bone_length = (bone.tail_local - bone.head_local).length
            bone_length = max(bone_length, z_range, 0.001)
        
        #动态确定主轴方向（使用范围最大的轴）
        axis = 'Y'
        if  x_range > z_range:
            axis = 'X'
        elif z_range > x_range:
            axis = 'Z'
        
        return {
            'radius': radius,
            'length': bone_length,
            'axis': axis,
            'count': count,
            'positions': positions,
        }
    
    return {
        'radius': 0.0,
        'length': 0.0,
        'axis': 'Y',
        'count': 0,
        'positions': [],
    }


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
        
        bone_size_cache = {}
        #print("[身体刚体] 开始计算骨骼刚体尺寸...")
        for bone in armature.data.bones:
            result = calculate_bone_rigid_size(armature, bone.name)
            bone_size_cache[bone.name] = result
            count = result.get('count', 1)
            #print(f"[身体刚体] 骨骼 {bone.name}: 半径={result['radius']:.4f}, 长度={result['length']:.4f}, 数量={count}")
        
        created_count = 0
        skipped_count = 0
        
        for bone in armature.data.bones:
            bone_name = bone.name
            
            bone_length = (bone.tail_local - bone.head_local).length
            if bone_length < 0.01:
                continue
            
            # 获取尺寸数据（包含 count 和 positions）
            size_data = bone_size_cache.get(bone_name, {
                'radius': 0.0, 
                'length': 0.0, 
                'count': 0, 
                'positions': [],
                'axis': 'Y'
            })
            radius = size_data['radius']
            length = size_data['length']
            count = size_data.get('count', 1)
            positions = size_data.get('positions', [0.0])
            axis = size_data.get('axis', 'Y')
            
            # 跳过尺寸为 0 的刚体（未找到顶点组）
            if radius == 0.0 or length == 0.0 or count == 0:
                skipped_count += 1
                continue
            
            # 获取骨骼中心点和旋转
            bone_center = (bone.head_local + bone.tail_local) / 2
            
            # 使用缓存中已计算的尺寸值
            input_x = radius
            input_y = length
       
            # 检查是否已存在
            if bone_name in bpy.data.objects:
                skipped_count += 1
                continue
            
            # 创建刚体对象
            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)

            # 设置刚体属性（位置为骨骼中心点）
            rb_obj.location = bone_center
            
            # 获取骨骼的本地旋转（参考胸部刚体设置）
            bone_rot = bone.matrix_local.to_euler("YXZ")
            bone_rot.rotate_axis("X", math.pi / 2)
            rb_obj.rotation_euler = bone_rot

            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((input_x, input_y, 0.0))
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = self._get_collision_mask(1)
            rb_obj.name = bone_name
            rb_obj.mmd_rigid.name_j = bone_name
            rb_obj.mmd_rigid.name_e = bone_name
            rb_obj.data.name = bone_name
            rb_obj.mmd_rigid.bone = bone_name
            
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 1.0
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0
            
            created_count += 1
        
        #print(f"[身体刚体] 创建完成：{created_count} 个刚体，跳过 {skipped_count} 个已存在的")
    
    def _get_collision_mask(self, group):
        """获取碰撞遮罩（返回 16 个布尔值的列表）"""
        # mmd_tools 的 collision_group_mask 是包含 16 个布尔值的列表
        mask = [False] * 16
        if group == 0:
            # 组 0（躯干）与组 0 和组 1 碰撞
            mask[0] = True
            mask[1] = True
        elif group == 1:
            # 组 1（身体刚体）与组 0 和组 1 碰撞
            mask[0] = True
            mask[1] = True
        else:
            # 其他组只与自身碰撞
            mask[group] = True
        return mask


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(OBJECT_OT_build_body_rigid_bodies)
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(
            name="左胸部骨骼", description="选择左侧胸部骨骼", default=""
        )
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(
            name="右胸部骨骼", description="选择右侧胸部骨骼", default=""
        )


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(OBJECT_OT_build_body_rigid_bodies)


if __name__ == "__main__":
    register()