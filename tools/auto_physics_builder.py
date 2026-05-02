"""
自动胸部物理构建器
基于 MMD 标准 GENERIC_SPRING 刚体物理体系构建胸部物理，
参数来源于对真实 MMD 胸部物理参考文件的逆向分析。

使用 mmd_tools API 创建完整的刚体和约束系统。
"""
import bpy
import math
from mathutils import Vector, Euler
from .. import bone_utils

# 导入 mmd_tools（Blender 5.1+ 扩展系统）
# Blender 5.1 使用 bl_ext.blender_org 前缀
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
        print(f"Error importing mmd_tools: {e}")
        print("Please install mmd_tools extension from Blender's extension repository")
        print("In Blender: Edit > Preferences > Extensions > Search 'mmd_tools' > Install")
        raise


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def get_vertex_group_y_min(armature, group_name):
    """获取顶点组中所有顶点的 Y 轴最小值（遍历所有网格对象）"""
    # 查找所有网格对象
    mesh_objs = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.parent == armature:
            mesh_objs.append(obj)
    
    if not mesh_objs:
        print(f"[调试] 未找到任何网格对象")
        return None
    
    print(f"[调试] 找到 {len(mesh_objs)} 个网格对象：{[m.name for m in mesh_objs]}")
    
    all_y_values = []
    
    for mesh_obj in mesh_objs:
        vg = mesh_obj.vertex_groups.get(group_name)
        if not vg:
            continue
        
        print(f"[调试] 在 {mesh_obj.name} 中找到顶点组：{group_name}，索引：{vg.index}")
        
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.group == vg.index and group.weight > 0:
                    world_pos = mesh_obj.matrix_world @ vertex.co
                    all_y_values.append(world_pos.y)
                    break
    
    if not all_y_values:
        print(f"[调试] 所有网格对象中顶点组 {group_name} 都没有权重值 > 0 的顶点")
        return None
    
    print(f"[调试] 总共找到 {len(all_y_values)} 个顶点，Y 最小值：{min(all_y_values)}")
    return min(all_y_values)


# ---------------------------------------------------------------------------
# 参考参数常量（来自 body_physics_final_with_size.md 胸部部分）
# ---------------------------------------------------------------------------

DEG5 = 0.0872665  # 5 度
DEG10 = 0.174533  # 10 度
DEG20 = 0.349066  # 20 度

# 碰撞组掩码设置（16 个碰撞组）
COLLISION_GROUP_MASK_0 = [True] * 16  # 组 0（躯干）
COLLISION_GROUP_MASK_2 = [True] * 16  # 组 2（胸部物理）

# 刚体完整参数定义（来自 body_physics_final_with_size.md 第 76-82 行）
# 格式：{骨骼名：{形状，质量，摩擦，线性阻尼，角阻尼，是否运动学，碰撞组，直径 X, 长度 Y}}
# CAPSULE: X=直径，Y=长度 | SPHERE: X=Y=Z=直径
# 注意：胸親需要放在最后，因为它的位置依赖于左右胸上刚体
CHEST_RIGID_BODIES = {
    "左胸上": {
        "shape": "CAPSULE",
        "mass": 0.05,
        "friction": 0.0,
        "linear_damping": 0.8,
        "angular_damping": 0.8,
        "is_kinematic": False,     # PHYSICS 模式
        "collision_group": 2,
        "size_x": 0.01,            # 直径
        "size_y": 0.02,            # 长度
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
        "size_x": 0.06,            # 直径
        "size_y": 0.06,            # 直径
        "size_z": 0.06,            # 直径
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
        "is_kinematic": True,      # BONE 模式
        "collision_group": 0,
        "size_x": 0.06,            # 直径
        "size_y": 0.11,            # 长度
        "size_z": 0.0,
    },
}


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

            # 获取用户选中的骨骼
            left_bone = context.scene.left_chest_bone if hasattr(context.scene, "left_chest_bone") else ""
            right_bone = context.scene.right_chest_bone if hasattr(context.scene, "right_chest_bone") else ""

            if not left_bone or not right_bone:
                self.report({'ERROR'}, "请先选择左/右胸部骨骼")
                return {'CANCELLED'}

            # 1. 创建骨骼链（包含重命名和创建新骨骼）
            self._build_chest_bone_chain(context, armature, left_bone, right_bone)

            # 2. 使用 mmd_tools API 创建刚体
            rb_objects = self._create_rigid_bodies(context, armature)

            # 3. 使用 mmd_tools API 创建关节
            self._create_spring_joints(context, armature, rb_objects)

            # 恢复选择
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

    # ------------------------------------------------------------------
    # 1. 创建骨骼链（在 EDIT 模式下）
    # ------------------------------------------------------------------
    def _build_chest_bone_chain(self, context, armature, left_bone, right_bone):
        """
        1. 在 EDIT 模式下重命名用户选中的骨骼为 左胸上 2 / 右胸上 2
        2. 创建左/右胸上（CAPSULE 的父骨骼）
        3. 创建左/右胸下（下方弹性支撑）
        4. 创建单一胸親（锚点）
        
        骨骼方向：
        - 胸親：向上（与上半身相同方向）
        - 胸上：向前
        - 胸上 2：向下
        - 胸下：向前
        """
        scene = context.scene
        
        print(f"[胸部物理] 构建骨骼链，left='{left_bone}', right='{right_bone}'")

        # 切换到 EDIT 模式
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones

        # 检查上半身骨骼是否存在
        if "上半身" not in eb:
            raise ValueError("缺少'上半身'骨骼，无法构建胸部物理系统")
        
        # 获取上半身骨骼的 Y 位置
        up_body_y = eb["上半身"].head.y
        
        # 获取用户选择的胸親父级骨骼（默认为上半身）
        chest_parent_name = scene.breast_parent_bone if scene.breast_parent_bone else "上半身"
        if chest_parent_name not in eb:
            print(f"[警告] 胸親父级骨骼 '{chest_parent_name}' 不存在，使用'上半身'")
            chest_parent_name = "上半身"
        
        # 先创建胸親骨骼（向上，与上半身相同方向）
        # 头部 Y 与上半身相同，Z 与上半身相同
        # 长度约为 0.08，尾部在头部上方
        BrP_head = Vector((0, up_body_y, eb["上半身"].head.z))
        BrP_tail = BrP_head + Vector((0, 0, 0.08))  # 尾部在头部上方 0.08
        
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

            # 在 EDIT 模式下重命名骨骼
            BrUp2_name = f"{prefix}胸上 2"
            if user_bone != BrUp2_name:
                eb[user_bone].name = BrUp2_name

            BrUp2 = eb[BrUp2_name]
            
            # 获取顶点组 Y 最小值
            vg_y_min = get_vertex_group_y_min(armature, BrUp2_name)
            
            # 计算胸上 2 的 Y 值（顶点组最小值和上半身 Y 值的平均）
            br_up2_y = (vg_y_min + up_body_y) / 2
            
            BrUp_name = f"{prefix}胸上"
            BrDown_name = f"{prefix}胸下"
            
            # 修改 BrUp2 的位置
            # 头部 Z = 原头部 Z + 0.04
            # 尾部 Z = 原头部 Z - 0.04
            original_z = BrUp2.head.z
            BrUp2.head = Vector((BrUp2.head.x, br_up2_y, original_z + 0.04))
            BrUp2.tail = Vector((BrUp2.tail.x, br_up2_y, original_z - 0.04))
            
            # 创建胸上骨骼
            # 头部 Y = 上半身 Y（靠近身体）
            # 尾部 = 胸上 2 的头部位置（远离身体，向前）
            BrUp_head = Vector((BrUp2.head.x, up_body_y, BrUp2.head.z))  # 头部靠近身体
            BrUp_tail = BrUp2.head  # 尾部在胸上 2 头部位置（向前）
            bone_utils.create_or_update_bone(
                edit_bones=eb,
                name=BrUp_name,
                head_position=BrUp_head,
                tail_position=BrUp_tail,
                use_connect=False,
                parent_name=None,
                use_deform=True
            )
            
            # 设置胸上 2 的父级为胸上
            BrUp2.parent = eb[BrUp_name]

            # 创建胸下骨骼
            # 头部 = 胸上 2 尾部位置（远离身体，向前）
            # 尾部 Y = 上半身 Y（靠近身体）
            BrDown_head = BrUp2.tail  # 头部在胸上 2 尾部位置（向前）
            BrDown_tail = Vector((BrUp2.head.x, up_body_y, BrUp2.tail.z))  # 尾部靠近身体
            bone_utils.create_or_update_bone(
                edit_bones=eb,
                name=BrDown_name,
                head_position=BrDown_head,
                tail_position=BrDown_tail,
                use_connect=False,
                parent_name=None,
                use_deform=True
            )

        # 设置胸上/胸下的父级为 BrP（胸親）
        for prefix in ("左", "右"):
            eb[f"{prefix}胸上"].parent = BrP
            eb[f"{prefix}胸下"].parent = BrP

        # 更新场景属性
        scene.left_chest_bone = "左胸上 2"
        scene.right_chest_bone = "右胸上 2"
        
        # 切换回 OBJECT 模式，让骨骼更改生效
        bpy.ops.object.mode_set(mode='OBJECT')
        
        print("[胸部物理] 骨骼链构建完成")

    # ------------------------------------------------------------------
    # 2. 使用 mmd_tools API 创建刚体
    # ------------------------------------------------------------------

    def _create_rigid_bodies(self, context, armature):
        """
        使用 mmd_tools API 创建刚体对象。
        mmd_tools 会自动管理刚体的层级和集合。
        """
        # 获取 mmd_tools 模型根对象
        root = FnModel.find_root_object(armature)
        if not root:
            raise RuntimeError("未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
        
        # 获取或创建刚体组对象（与面板行为一致）
        rigid_grp_obj = FnModel.ensure_rigid_group_object(context, root)
        
        rb_objects = {}

        for bone_name, params in CHEST_RIGID_BODIES.items():
            if bone_name not in armature.data.bones:
                print(f"[胸部物理] 跳过刚体 '{bone_name}'（骨骼不存在）")
                continue

            # 使用骨骼名作为刚体名（与 mmd_tools 面板一致）
            rb_name = bone_name
            
            if rb_name in bpy.data.objects:
                rb_obj = bpy.data.objects[rb_name]
                rb_objects[bone_name] = rb_obj
                print(f"[胸部物理] 跳过已存在的：{rb_name}")
                continue

            # 创建刚体（使用 ensure_rigid_group_object，与面板行为一致）
            rb_obj = FnRigidBody.new_rigid_body_object(context, rigid_grp_obj)
            
            # 获取骨骼对象（使用 pose_bone，与面板一致）
            pbone = armature.pose.bones.get(bone_name)
            if not pbone:
                continue
            
            bone = pbone.bone
            
            # 构建尺寸向量（CAPSULE: X=直径，Y=长度 | SPHERE: X=Y=Z=直径）
            size = Vector((params["size_x"], params["size_y"], params["size_z"]))
            
            # 计算位置（骨骼中心点，使用 head_local/tail_local，与面板一致）
            bone_loc = (bone.head_local + bone.tail_local) / 2
            
            # 计算旋转（与面板一致）
            bone_rot = bone.matrix_local.to_euler("YXZ")
            bone_rot.rotate_axis("X", math.pi / 2)
            
            # 设置刚体参数
            rb_obj.location = bone_loc
            rb_obj.rotation_euler = bone_rot
            rb_obj.mmd_rigid.shape = params["shape"]
            rb_obj.mmd_rigid.size = size
            rb_obj.mmd_rigid.type = "0" if params["is_kinematic"] else "1"
            rb_obj.mmd_rigid.collision_group_number = params["collision_group"]
            
            # 设置碰撞组掩码
            collision_mask = COLLISION_GROUP_MASK_0 if params["collision_group"] == 0 else COLLISION_GROUP_MASK_2
            rb_obj.mmd_rigid.collision_group_mask = collision_mask
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            # 设置物理参数
            rb = rb_obj.rigid_body
            rb.friction = params["friction"]
            rb.mass = params["mass"]
            rb.angular_damping = params["angular_damping"]
            rb.linear_damping = params["linear_damping"]
            rb.restitution = 0.0
            
            rb_objects[bone_name] = rb_obj
            print(f"[胸部物理] 创建：{rb_name}, type={params['shape']}, mass={params['mass']}")

        # 创建完成后，调整胸親的位置和旋转
        rb_parent = rb_objects.get("胸親")
        if rb_parent:
            left_up2_rb = rb_objects.get("左胸上 2")
            right_up2_rb = rb_objects.get("右胸上 2")
            
            if left_up2_rb and right_up2_rb:
                # 胸親位置 = 左右胸上 2 位置的中间
                rb_parent.location = (left_up2_rb.location + right_up2_rb.location) / 2
                
                # 胸親旋转：Y 轴 -90 度
                rb_parent.rotation_euler = Euler((0, -math.pi/2, 0), 'YXZ')
                print(f"[胸部物理] 调整胸親位置到中心，Y 旋转 -90 度")

        return rb_objects

    # ------------------------------------------------------------------
    # 3. 使用 mmd_tools API 创建关节
    # ------------------------------------------------------------------

    def _create_spring_joints(self, context, armature, rb_objects):
        """
        使用 mmd_tools API 创建 6 个核心弹簧约束。
        mmd_tools 会自动管理约束的层级和集合。
        """
        # 获取 mmd_tools 模型根对象
        root = FnModel.find_root_object(armature)
        
        # 获取或创建关节组对象（与面板一致）
        joint_grp_obj = FnModel.ensure_joint_group_object(context, root)
        
        spring_defs = self._get_spring_definitions()

        for sd in spring_defs:
            rb1 = rb_objects.get(sd["rb1"])
            rb2 = rb_objects.get(sd["rb2"])
            if rb1 is None or rb2 is None:
                print(f"[胸部物理] 跳过约束（刚体不存在）: {sd['joint']}")
                continue

            # joint 名字使用第二个刚体的名字（与 mmd_tools 面板一致）
            # 第 434-435 行：name_j = rigid_b.mmd_rigid.name_j or rigid_b.name
            joint_name = rb2.name
            
            # 检查是否存在同名的关节对象（需要检查 mmd_type）
            if joint_name in bpy.data.objects:
                obj = bpy.data.objects[joint_name]
                if obj.mmd_type == "JOINT":
                    joint_obj = obj
                    print(f"[胸部物理] 跳过已存在的约束：{joint_name}")
                    continue
            
            # 创建关节（使用 ensure_joint_group_object，与面板一致）
            joint_obj = FnRigidBody.new_joint_object(context, joint_grp_obj, FnModel.get_empty_display_size(root))
            
            # 计算中点位置
            mid = (rb1.location + rb2.location) / 2
            
            # 使用 setup_joint_object 设置关节参数（与面板一致）
            joint_obj = FnRigidBody.setup_joint_object(
                obj=joint_obj,
                name=rb2.name,  # 使用第二个刚体的名字
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
            
            # 关闭碰撞
            joint_obj.rigid_body_constraint.disable_collisions = True

            print(f"[胸部物理] 创建弹簧：{joint_name}")

    def _get_spring_definitions(self):
        """
        返回 6 个核心弹簧约束的参数字典。
        全部为 GENERIC_SPRING，disable_collisions=True，阻尼=0.5。
        
        根据 joint_params_report.md：
        - J.胸上：ang_z ±5°，K_z=100
        - J.胸上 2：无约束（全 0）
        - J.胸下：ang_x ±10°，ang_z ±5°，K_x=100, K_z=100
        """
        def s(joint, rb1, rb2, **kw):
            # 默认值：所有线性/角限位为 0
            for ax in 'xyz':
                for pre in (f'lin_{ax}', f'ang_{ax}'):
                    if pre not in kw:
                        kw[pre] = 0
            kw.update({"joint": joint, "rb1": rb1, "rb2": rb2})
            return kw

        defs = []

        for prefix in ('左', '右'):
            # J.胸上：胸親 → 胸上，ang_z ±5°，K_z=100
            defs.append(s(
                f"J.{prefix}胸上", "胸親", f"{prefix}胸上",
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_z=100,
            ))
            # J.胸上 2：胸上 → 胸上 2，无约束（全 0）
            defs.append(s(
                f"J.{prefix}胸上 2", f"{prefix}胸上", f"{prefix}胸上 2",
            ))
            # J.胸下：胸親 → 胸下，ang_x ±10°，ang_z ±5°，K_x=100, K_z=100
            defs.append(s(
                f"J.{prefix}胸下", "胸親", f"{prefix}胸下",
                ang_x_lo=-DEG10, ang_x_hi=DEG10,
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_x=100, k_ang_z=100,
            ))

        return defs

    def _get_bone_world_pos(self, armature, bone_name):
        """获取骨骼的世界坐标位置"""
        bone = armature.data.bones.get(bone_name)
        if not bone:
            return (0, 0, 0)
        
        # 获取骨骼的头部位置（局部坐标）
        local_pos = bone.head
        
        # 转换为世界坐标
        world_pos = armature.matrix_world @ Vector(local_pos)
        return tuple(world_pos)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(
            name="左胸部骨骼", description="选择左侧胸部骨骼（对应左胸上 2，SPHERE 碰撞核心）", default=""
        )
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(
            name="右胸部骨骼", description="选择右侧胸部骨骼（对应右胸上 2，SPHERE 碰撞核心）", default=""
        )


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)


if __name__ == "__main__":
    register()
