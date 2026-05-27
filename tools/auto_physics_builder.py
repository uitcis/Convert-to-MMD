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

    3. 高级身体刚体系统（简化版）
       3-1. 网格分析模块 - 权重收集、曲率分析
       3-2. 参数计算模块 - 位置、半径、旋转、分段计算
       3-3. 高级刚体生成算法

    4. 注册/反注册函数
"""
import bpy
import math
import gc

from mathutils import Vector, Euler, Matrix

CHUNK_SIZE = 2000
MAX_MEMORY_PERCENTAGE = 80
from .. import bone_utils

try:
    from bl_ext.blender_org.mmd_tools.core.rigid_body import FnRigidBody
    from bl_ext.blender_org.mmd_tools.core.model import FnModel
    MMD_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from mmd_tools.core.rigid_body import FnRigidBody
        from mmd_tools.core.model import FnModel
        MMD_TOOLS_AVAILABLE = True
    except ImportError:
        # 延迟导入，不在加载时强制检测
        FnRigidBody = None
        FnModel = None
        MMD_TOOLS_AVAILABLE = False


# ---------------------------------------------------------------------------
# 内存监控与垃圾回收辅助函数
# ---------------------------------------------------------------------------

def _get_memory_info():
    """获取系统内存信息（使用 Blender API 和系统 API）"""
    result = {
        'memory_percent': None,
        'used_gb': None,
        'available_gb': None,
        'peak_gb': None
    }
    
    try:
        result['used_gb'] = bpy.app.debug_memory_usage() / (1024**3)
        result['peak_gb'] = bpy.app.debug_memory_peak() / (1024**3)
    except:
        pass
    
    import os
    if os.name == 'nt':
        try:
            from ctypes import windll, Structure, c_ulonglong, byref
            class MEMORYSTATUSEX(Structure):
                _fields_ = [("dwLength", c_ulonglong), ("dwMemoryLoad", c_ulonglong),
                            ("ullTotalPhys", c_ulonglong), ("ullAvailPhys", c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = c_ulonglong(24)
            if windll.kernel32.GlobalMemoryStatusEx(byref(stat)):
                result['memory_percent'] = stat.dwMemoryLoad
                result['used_gb'] = (stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3)
                result['available_gb'] = stat.ullAvailPhys / (1024**3)
        except:
            pass
    else:
        try:
            total_mem = None
            avail_mem = None
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        total_mem = int(line.split()[1]) * 1024
                    elif line.startswith('MemAvailable:'):
                        avail_mem = int(line.split()[1]) * 1024
            if total_mem and avail_mem:
                result['memory_percent'] = ((total_mem - avail_mem) / total_mem) * 100
                result['used_gb'] = (total_mem - avail_mem) / (1024**3)
                result['available_gb'] = avail_mem / (1024**3)
        except:
            pass
    
    return result

def _check_memory_and_gc(force=False):
    """
    检查内存使用并在必要时触发垃圾回收
    
    当内存使用率超过 GC_MEMORY_THRESHOLD (70%) 时触发 gc.collect()，
    当内存使用率超过 MAX_MEMORY_PERCENTAGE (80%) 时返回 False 阻止继续处理。
    
    Args:
        force: 是否强制执行内存检查和GC
    
    Returns:
        bool: True=继续处理，False=内存不足应停止
    """
    GC_MEMORY_THRESHOLD = 70

    mem_info = _get_memory_info()
    memory_percent = mem_info['memory_percent'] if mem_info else None
    
    # 强制触发GC（只在force=True或内存超过阈值时）
    if force or (memory_percent is not None and memory_percent > GC_MEMORY_THRESHOLD):
        collected = gc.collect()
        
        if force and collected > 0:
            # 只在force=True且有回收时打印
            mem_info2 = _get_memory_info()
            parts = [f"GC回收: {collected}"]
            if mem_info2 and mem_info2['memory_percent'] is not None:
                parts.append(f"使用率: {mem_info2['memory_percent']:.1f}%")
            print(f"[GC] {' | '.join(parts)}")
        
        if memory_percent is not None and memory_percent > GC_MEMORY_THRESHOLD and not force:
            # 内存超过阈值时的日志
            parts = [f"已回收 {collected} 个对象"]
            if mem_info['used_gb'] is not None:
                parts.append(f"已使用: {mem_info['used_gb']:.2f} GB")
            if memory_percent is not None:
                parts.append(f"使用率: {memory_percent:.1f}%")
            print(f"[GC] {' | '.join(parts)}")

    if memory_percent is not None and memory_percent > MAX_MEMORY_PERCENTAGE:
        parts = [f"[内存警告] 内存使用率过高 ({memory_percent:.1f}% > {MAX_MEMORY_PERCENTAGE}%)，正在终止操作..."]
        if mem_info['used_gb'] is not None:
            parts.append(f"已使用: {mem_info['used_gb']:.2f} GB")
        if mem_info['available_gb'] is not None:
            parts.append(f"可用: {mem_info['available_gb']:.2f} GB")
        print('\n'.join(parts))
        return False
    return True


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
        except MemoryError as me:
            self.report({'ERROR'}, str(me))
            print(f"内存错误: {me}")
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
            rb_parent.rotation_euler = Euler((0, -math.pi/2, 0), 'YXZ')
            
            left_radius = breast_data["左"]['radius']
            right_radius = breast_data["右"]['radius']
            avg_radius = (left_radius + right_radius) / 2
            x_distance = abs(left_rb.location.x - right_rb.location.x)
            rb_parent.mmd_rigid.size = Vector((avg_radius, x_distance, 0.0))

        return rb_objects
    #乳房弹簧构建
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
# =                        #身体刚体通用代码                          =
# ===========================================================================        

def _solve_eigen_3x3_sym(m):
    """
    求解3x3对称矩阵的特征值和特征向量（使用Jacobi迭代法，数值稳定）
    
    参数:
        m: 3x3对称矩阵，列表形式 [[a,b,c],[b,d,e],[c,e,f]]
    
    返回:
        eigenvalues: 特征值列表 [lambda1, lambda2, lambda3]，按升序排列
        eigenvectors: 特征向量列表 [[x1,y1,z1], [x2,y2,z2], [x3,y3,z3]]
    """
    # 复制矩阵
    a = [[m[i][j] for j in range(3)] for i in range(3)]
    
    # 初始化特征向量矩阵为单位矩阵
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    
    # Jacobi迭代
    max_iter = 100
    for _ in range(max_iter):
        # 找到最大的非对角元素
        max_val = 0.0
        p = 0
        q = 1
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(a[i][j]) > max_val:
                    max_val = abs(a[i][j])
                    p = i
                    q = j
        
        # 如果收敛了
        if max_val < 1e-10:
            break
        
        # 计算旋转角度
        if a[p][p] == a[q][q]:
            theta = math.pi / 4 if a[p][q] > 0 else -math.pi / 4
        else:
            theta = 0.5 * math.atan(2 * a[p][q] / (a[p][p] - a[q][q]))
        
        c = math.cos(theta)
        s = math.sin(theta)
        
        # 旋转矩阵
        # 只更新受影响的元素
        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]
        
        # 更新对角元素
        a[p][p] = c * c * app - 2 * c * s * apq + s * s * aqq
        a[q][q] = s * s * app + 2 * c * s * apq + c * c * aqq
        a[p][q] = 0.0
        a[q][p] = 0.0
        
        # 更新其他元素
        for r in range(3):
            if r != p and r != q:
                apr = a[p][r]
                aqr = a[q][r]
                a[p][r] = c * apr - s * aqr
                a[r][p] = a[p][r]
                a[q][r] = s * apr + c * aqr
                a[r][q] = a[q][r]
        
        # 更新特征向量矩阵
        for r in range(3):
            vpr = v[p][r]
            vqr = v[q][r]
            v[p][r] = c * vpr - s * vqr
            v[q][r] = s * vpr + c * vqr
    
    # 提取特征值和特征向量
    eigenvalues = [a[i][i] for i in range(3)]
    eigenvectors = [[v[i][j] for i in range(3)] for j in range(3)]
    
    # 按特征值排序
    idx = sorted(range(3), key=lambda i: eigenvalues[i])
    eigenvalues = [eigenvalues[i] for i in idx]
    eigenvectors = [eigenvectors[i] for i in idx]
    
    return eigenvalues, eigenvectors


def _build_rotation_matrix(axis):
    """构建将世界Z轴旋转到给定轴方向的旋转矩阵"""
    z_axis = Vector((0, 0, 1))
    
    # 如果axis已经平行于Z轴正方向，返回单位矩阵
    if axis.dot(z_axis) > 0.9999:
        return Matrix.Identity(3)
    # 如果axis平行于Z轴负方向，返回绕X轴旋转180度
    if axis.dot(z_axis) < -0.9999:
        return Matrix.Rotation(math.pi, 3, 'X')
    
    # 计算旋转轴和旋转角度
    # 需要从Z轴旋转到axis方向，所以用z_axis.cross(axis)
    rot_axis = z_axis.cross(axis)
    if rot_axis.length < 0.0001:
        return Matrix.Identity(3)
    rot_axis.normalize()
    angle = math.acos(max(-1.0, min(1.0, axis.dot(z_axis))))
    
    return Matrix.Rotation(angle, 3, rot_axis)

# ===========================================================================
# =                        2. 身体刚体系统（简易模式）                          =
# ===========================================================================

# ---------------------------------------------------------------------------
# 2-1. 简易身体刚体生成（基于骨骼权重）
# ---------------------------------------------------------------------------



def calculate_simple_body_rigid_params(armature, bone_names=None):
    """
    简易身体刚体参数计算（基于骨骼权重）
    
    圆柱拟合步骤：
    1. 第一步：获取轴线（通过协方差矩阵特征值分解确定方向）
    2. 第二步：获取半径（计算所有顶点到轴线的最大垂直距离）
    3. 第三步：获取圆柱尺寸（计算顶点在轴线方向上的投影范围）
    4. 第四步：圆柱的中心即为刚体位置（计算几何中心）
    
    算法流程：
    - 通过特征值分解协方差矩阵获取主成分方向作为轴线
    - 将顶点投影到垂直于轴线的平面上进行圆拟合
    - 使用所有点到轴线的最大距离确保包围所有顶点
    - 刚体位置设置为圆柱的几何中心（投影范围的中点）
    
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
    
    for bone_idx, bone_name in enumerate(bone_names):
        if not _check_memory_and_gc():
            break
        
        if bone_name not in armature.data.bones:
            continue
        
        bone = armature.data.bones[bone_name]
        
        # 2-1. 获取骨骼对应顶点组权重顶点（保留权重值）
        weighted_vertices = []
        
        for mesh_obj in mesh_objs:
            vg = mesh_obj.vertex_groups.get(bone_name)
            if not vg:
                continue
            
            for vertex in mesh_obj.data.vertices:
                for group in vertex.groups:
                    if group.group == vg.index and group.weight > 0.4:
                        v_world = mesh_obj.matrix_world @ Vector(vertex.co)
                        weighted_vertices.append((v_world, group.weight))
                        break
        
        if not weighted_vertices:
            continue
        
        # 2-2. 提取顶点和权重
        vertices_world = [v for v, _ in weighted_vertices]
        weights = [w for _, w in weighted_vertices]
        n = len(vertices_world)
        
        # 2-3. 计算加权质心
        total_weight = sum(weights)
        if total_weight > 0:
            centroid = sum((v * w for v, w in weighted_vertices), Vector()) / total_weight
        else:
            centroid = sum((v for v in vertices_world), Vector()) / n
        
        # 2-4. 计算协方差矩阵（用于确定轴线方向）
        cov_matrix = [[0.0] * 3 for _ in range(3)]
        for i, v in enumerate(vertices_world):
            dx = v.x - centroid.x
            dy = v.y - centroid.y
            dz = v.z - centroid.z
            weight = weights[i] if total_weight > 0 else 1.0 / n
            cov_matrix[0][0] += dx * dx * weight
            cov_matrix[0][1] += dx * dy * weight
            cov_matrix[0][2] += dx * dz * weight
            cov_matrix[1][1] += dy * dy * weight
            cov_matrix[1][2] += dy * dz * weight
            cov_matrix[2][2] += dz * dz * weight
        cov_matrix[1][0] = cov_matrix[0][1]
        cov_matrix[2][0] = cov_matrix[0][2]
        cov_matrix[2][1] = cov_matrix[1][2]
        
        # =========================================================================
        # 第一步：获取轴线
        # =========================================================================
        # 2-5. 求解特征值和特征向量（最大特征值对应圆柱轴线方向）
        axis_dir = None
        
        # 检查协方差矩阵是否有效且顶点数量足够
        cov_valid = True
        for i in range(3):
            for j in range(3):
                if not (isinstance(cov_matrix[i][j], (int, float)) and math.isfinite(cov_matrix[i][j])):
                    cov_valid = False
                    break
            if not cov_valid:
                break
        
        if n >= 3 and cov_valid:
            try:
                # 使用自定义的对称矩阵特征值求解算法
                eigenvalues, eigenvectors = _solve_eigen_3x3_sym(cov_matrix)
                
                # 找到最大特征值对应的特征向量（圆柱轴线方向）
                max_eigen_idx = 0
                max_eigen_val = eigenvalues[0]
                for i in range(1, 3):
                    if eigenvalues[i] > max_eigen_val:
                        max_eigen_val = eigenvalues[i]
                        max_eigen_idx = i
                
                # 获取对应的特征向量作为轴线方向
                axis_dir = Vector(eigenvectors[max_eigen_idx])
                
                # 计算骨骼方向作为参考
                bone_head_world = armature.matrix_world @ bone.head_local
                bone_tail_world = armature.matrix_world @ bone.tail_local
                bone_dir = (bone_tail_world - bone_head_world).normalized()
                
                # 如果特征向量方向与骨骼方向相反，取反以确保一致性
                if axis_dir.dot(bone_dir) < 0:
                    axis_dir = -axis_dir
                
                # 如果特征向量与骨骼方向几乎垂直，回退到骨骼方向
                if abs(axis_dir.dot(bone_dir)) < 0.5:
                    axis_dir = bone_dir.copy()
                
                # 检查特征向量是否有效
                if axis_dir.length >= 0.0001:
                    axis_dir.normalize()
            except Exception:
                pass
        
        # 如果特征值求解失败，回退到使用骨骼方向
        if axis_dir is None:
            bone_head_world = armature.matrix_world @ bone.head_local
            bone_tail_world = armature.matrix_world @ bone.tail_local
            axis_dir = (bone_tail_world - bone_head_world).normalized()
        
        # =========================================================================
        # 辅助步骤：投影计算（为获取半径做准备）
        # =========================================================================
        # 2-6. 将所有点投影到垂直于轴线的平面上
        # 创建正交基：u, v 是垂直于轴线的两个正交向量
        if abs(axis_dir.x) < abs(axis_dir.y):
            if abs(axis_dir.x) < abs(axis_dir.z):
                u = Vector((1, 0, 0))
            else:
                u = Vector((0, 0, 1))
        else:
            if abs(axis_dir.y) < abs(axis_dir.z):
                u = Vector((0, 1, 0))
            else:
                u = Vector((0, 0, 1))
        
        # 正交化 u
        u = (u - u.dot(axis_dir) * axis_dir).normalized()
        v = axis_dir.cross(u).normalized()
        
        # =========================================================================
        # 辅助步骤：圆拟合（为获取半径和中心做准备）
        # =========================================================================
        # 2-7. 在投影平面上拟合圆
        # 投影坐标
        proj_x = [v_world.dot(u) for v_world in vertices_world]
        proj_y = [v_world.dot(v) for v_world in vertices_world]
        
        # 使用最小二乘法拟合圆: (x - a)^2 + (y - b)^2 = r^2
        # 展开得: x^2 + y^2 = 2*a*x + 2*b*y + (r^2 - a^2 - b^2)
        # 即: Ax = b，其中 A = [2x, 2y, 1], x = [a, b, c], b = x^2 + y^2
        
        # 构建线性方程组
        A = [[0.0] * 3 for _ in range(n)]
        b = [0.0] * n
        
        for i in range(n):
            A[i][0] = 2 * proj_x[i]
            A[i][1] = 2 * proj_y[i]
            A[i][2] = 1.0
            b[i] = proj_x[i]**2 + proj_y[i]**2
        
        # 求解最小二乘问题
        try:
            A_mat = Matrix(A)
            b_vec = Vector(b)
            # 使用伪逆求解
            x = A_mat.transposed() @ ((A_mat @ A_mat.transposed()).inverted() @ b_vec)
            a_fit = x[0]
            b_fit = x[1]
            c_fit = x[2]
            
            # 计算拟合圆心在3D空间中的位置
            C_fit = centroid + a_fit * u + b_fit * v
        except Exception:
            # 如果拟合失败，使用质心作为圆心
            C_fit = centroid
        
        # =========================================================================
        # 第二步：获取半径
        # =========================================================================
        # 2-8. 使用所有点到轴线的最大垂直距离作为半径（确保包住所有顶点）
        max_radius = 0.0
        for v_world in vertices_world:
            # 计算点到轴线的垂直距离
            v_rel = v_world - C_fit
            proj_len = v_rel.dot(axis_dir)
            v_rel_proj = proj_len * axis_dir
            distance = (v_rel - v_rel_proj).length
            if distance > max_radius:
                max_radius = distance
        
        radius = max_radius
        
        # =========================================================================
        # 第三步：获取圆柱尺寸
        # =========================================================================
        # 2-9. 计算圆柱长度（顶点在轴线上的投影范围）
        projections = [v.dot(axis_dir) for v in vertices_world]
        min_proj = min(projections)
        max_proj = max(projections)
        bone_length = max_proj - min_proj
        
        # =========================================================================
        # 第四步：圆柱的中心即为刚体位置
        # =========================================================================
        # 2-10. 计算圆柱几何中心（轴线方向上投影范围的中点）
        # 圆柱中心 = 拟合圆心在垂直平面上的位置 + 轴线方向上的中点投影
        center_proj = (min_proj + max_proj) / 2  # 轴线方向上的中点投影
        C_fit_proj = C_fit.dot(axis_dir)          # 拟合圆心在轴线上的投影
        delta_proj = center_proj - C_fit_proj      # 需要调整的投影距离
        cylinder_center = C_fit + delta_proj * axis_dir  # 圆柱几何中心
        
        # 2-11. 创建刚体，刚体位置使用圆柱几何中心，长度使用投影范围
        rotation_matrix = _build_rotation_matrix(axis_dir)
        
        # 打印刚体旋转角度和轴线角度信息
        x_axis = Vector((1, 0, 0))
        y_axis = Vector((0, 1, 0))
        z_axis = Vector((0, 0, 1))
        
        # 计算轴线与各坐标轴的夹角（弧度转角度）
        angle_x = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(x_axis)))))
        angle_y = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(y_axis)))))
        angle_z = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(z_axis)))))
        
        # 从旋转矩阵提取欧拉角
        euler = rotation_matrix.to_euler()
        
        print(f"[{bone_name}] 轴线角度: X={angle_x:.1f}°, Y={angle_y:.1f}°, Z={angle_z:.1f}°")
        print(f"[{bone_name}] 旋转欧拉角: X={math.degrees(euler.x):.1f}°, Y={math.degrees(euler.y):.1f}°, Z={math.degrees(euler.z):.1f}°")
        
        rigid_params.append({
            'index': len(rigid_params),
            'center': cylinder_center,
            'length': bone_length,
            'outer_radius': radius,
            'rotation_matrix': rotation_matrix,
            'nearest_bone': bone_name,
            'vertex_count': len(vertices_world)
        })
        
        del weighted_vertices, vertices_world, weights
        _check_memory_and_gc(force=True)
    
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

            if not MMD_TOOLS_AVAILABLE:
                self.report({'ERROR'}, "mmd_tools 未安装，请先安装 mmd_tools 扩展")
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

        deform_bones = [bone.name for bone in armature.data.bones if bone.use_deform]
        
        rigid_params_list = calculate_simple_body_rigid_params(
            armature, 
            bone_names=deform_bones
        )

        if not rigid_params_list:
            self.report({'WARNING'}, "未找到足够的顶点数据来生成刚体")
            return

        total = len(rigid_params_list)
        created_count = 0

        for rb_idx, params in enumerate(rigid_params_list):
            if not _check_memory_and_gc():
                break
            
            bone_name = params['nearest_bone']
            rb_name = f"{bone_name}"
            
            if rb_name in bpy.data.objects:
                continue

            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)

            local_center = rigid_grp_obj.matrix_world.inverted() @ params['center']
            rb_obj.location = local_center

            parent_rot_inv = rigid_grp_obj.matrix_world.inverted().to_3x3()
            local_rotation = parent_rot_inv @ params['rotation_matrix']
            rb_obj.rotation_euler = local_rotation.to_euler('YXZ')
            
            rb_obj.mmd_rigid.shape = "CAPSULE"
            rb_obj.mmd_rigid.size = Vector((params['outer_radius'], params['length'], 0.0))
            
            rb_obj.mmd_rigid.type = "0"
            rb_obj.mmd_rigid.collision_group_number = 1
            rb_obj.mmd_rigid.collision_group_mask = [False] * 16
            rb_obj.mmd_rigid.collision_group_mask[0] = True
            rb_obj.mmd_rigid.collision_group_mask[1] = True
            
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            
            if params['nearest_bone']:
                rb_obj.mmd_rigid.bone = params['nearest_bone']
            
            rb = rb_obj.rigid_body
            rb.friction = 0.5
            rb.mass = 1.0 / total
            rb.angular_damping = 0.5
            rb.linear_damping = 0.5
            rb.restitution = 0.0

            created_count += 1
            print(f"[简易身体刚体] 创建: {rb_name} ({created_count}/{total}), 尺寸=(半径:{params['outer_radius']:.4f}, 长度:{params['length']:.4f})")

            if created_count % 20 == 0:
                context.view_layer.update()
                try:
                    bpy.ops.ed.undo_push(message=f"简易刚体 {created_count}/{total}")
                except:
                    pass

        del rigid_params_list
        _check_memory_and_gc(force=True)
        context.view_layer.update()

        if created_count < total:
            self.report({'WARNING'}, f"内存不足，已提前终止（创建 {created_count}/{total} 个刚体）")


# ===========================================================================
# =                        3. 注册/反注册函数                                 =
# ===========================================================================

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.register_class(OBJECT_OT_build_simple_body_rigid)
 
def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    bpy.utils.unregister_class(OBJECT_OT_build_simple_body_rigid)


if __name__ == "__main__":
    register()
