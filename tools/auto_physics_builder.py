"""
自动胸部物理构建器
基于 MMD 标准 GENERIC_SPRING 刚体物理体系构建胸部物理，
参数来源于对真实 MMD 胸部物理参考文件的逆向分析。

使用 mmd_tools API 构建完整的刚体和约束系统。
"""
import bpy
from mathutils import Vector, Euler

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
# 参考参数常量（来自 spring_result.json 逆向分析）
# ---------------------------------------------------------------------------

# 刚体参数：shape, mass, friction, lin_damp, ang_damp, is_kinematic
RB_PARAMS = {
    "胸親": ("CAPSULE", 1.0, 0.5, 0.04, 0.1, True),    # Kinematic 锚点
    "左胸上": ("CAPSULE", 0.05, 0.5, 0.8, 0.8, False),
    "右胸上": ("CAPSULE", 0.05, 0.5, 0.8, 0.8, False),
    "左胸上 2": ("SPHERE", 0.20, 0.5, 0.8, 0.8, False),  # 碰撞核心
    "右胸上 2": ("SPHERE", 0.20, 0.5, 0.8, 0.8, False),
    "左胸下": ("CAPSULE", 0.05, 0.5, 0.8, 0.8, False),
    "右胸下": ("CAPSULE", 0.05, 0.5, 0.8, 0.8, False),
}

DEG5 = 0.0872665  # 5 度
DEG10 = 0.174533  # 10 度
DEG20 = 0.349066  # 20 度


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

            # 1. 修改和创建骨骼
            self._build_chest_bone_chain(armature, left_bone, right_bone)

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
    # 1. 修改和创建骨骼
    # ------------------------------------------------------------------

    def _build_chest_bone_chain(self, armature, left_user_bone, right_user_bone):
        """
        1. 将用户选中的骨骼重命名为 左胸上 2 / 右胸上 2
        2. 创建左/右胸上（CAPSULE 的父骨骼）
        3. 创建左/右胸下（下方弹性支撑）
        4. 创建单一胸親（锚点）
        
        骨骼方向：
        - 胸親：向上（与上半身相同方向）
        - 胸上：向前
        - 胸上 2：向下
        - 胸下：向前
        """
        print(f"[胸部物理] 构建骨骼链，left='{left_user_bone}', right='{right_user_bone}'")

        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones

        up1_bones = {}
        down_bones = {}

        for prefix, user_bone in (("左", left_user_bone), ("右", right_user_bone)):
            if user_bone not in eb:
                raise ValueError(f"骨骼 '{user_bone}' 不存在")

            up2_name = f"{prefix}胸上 2"
            up1_name = f"{prefix}胸上"
            down_name = f"{prefix}胸下"

            # 重命名用户选中的骨骼
            if user_bone != up2_name:
                eb[user_bone].name = up2_name

            up2 = eb[up2_name]
            
            # 创建胸上骨骼（向前）
            if up1_name not in eb:
                up1 = eb.new(up1_name)
                up1.tail = up2.head
                up1.head = up2.head + Vector((0, 0.1, 0))  # 向前
                up1_bones[prefix] = up1
            else:
                up1_bones[prefix] = eb[up1_name]

            # 创建胸下骨骼（向前，与胸上相同的 X、Y 轴位置，与胸上 2 尾部相同的 Z 轴位置）
            if down_name not in eb:
                down = eb.new(down_name)
                # 使用胸上的 X、Y 轴位置，胸上 2 尾部的 Z 轴位置，向前延伸
                down.tail = Vector((up1_bones[prefix].tail.x, up1_bones[prefix].tail.y, up2.tail.z))
                down.head = Vector((up1_bones[prefix].head.x, up1_bones[prefix].head.y, up2.tail.z))
                down_bones[prefix] = down
            else:
                down_bones[prefix] = eb[down_name]

        # 创建胸親骨骼（向上，与上半身相同方向）
        if "胸親" not in eb:
            parent = eb.new("胸親")
            left_head = eb["左胸上"].head.copy()
            right_head = eb["右胸上"].head.copy()
            parent.head = (left_head + right_head) / 2
            parent.tail = parent.head + Vector((0, 0, 0.1))  # 向上
        else:
            parent = eb["胸親"]
        
        # 设置胸親的父级为上半身骨骼
        if "上半身" in eb:
            parent.parent = eb["上半身"]
        else:
            print("[警告] 未找到'上半身'骨骼，胸親将没有父级")

        # 设置父子关系
        for prefix in ("左", "右"):
            eb[f"{prefix}胸上"].parent = parent
            eb[f"{prefix}胸下"].parent = parent

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
        
        bone_idx_map = {
            "胸親": 51,
            "左胸上": 52,
            "右胸上": 53,
            "左胸上 2": 54,
            "右胸上 2": 55,
            "左胸下": 56,
            "右胸下": 57
        }
        
        bone_to_size = {
            "胸親": (0.1, 0.2, 0.0),
            "左胸上": (0.1, 0.2, 0.0),
            "右胸上": (0.1, 0.2, 0.0),
            "左胸上 2": (0.05, 0.05, 0.05),
            "右胸上 2": (0.05, 0.05, 0.05),
            "左胸下": (0.1, 0.2, 0.0),
            "右胸下": (0.1, 0.2, 0.0)
        }

        for bone_name, (shape, mass, friction, lin_damp, ang_damp, is_kinematic) in RB_PARAMS.items():
            if bone_name not in armature.data.bones:
                print(f"[胸部物理] 跳过刚体 '{bone_name}'（骨骼不存在）")
                continue

            idx = bone_idx_map.get(bone_name, 55)
            rb_name = f"{idx:03d}_{bone_name}"
            
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
            
            # 计算尺寸
            size = Vector(bone_to_size.get(bone_name, (0.1, 0.2, 0.0)))
            if shape == "CAPSULE":
                bl = max(bone.length, 0.02)
                size = Vector((bl * 0.25, bl, 0.0))
            elif shape == "SPHERE":
                bl = max(bone.length, 0.02)
                size = Vector((bl * 0.3, bl * 0.3, bl * 0.3))
            
            # 计算位置（骨骼中心点，使用 head_local/tail_local，与面板一致）
            bone_loc = (bone.head_local + bone.tail_local) / 2
            
            # 计算旋转（与面板一致）
            import math
            bone_rot = bone.matrix_local.to_euler("YXZ")
            bone_rot.rotate_axis("X", math.pi / 2)
            
            # 设置刚体参数
            rb_obj.location = bone_loc
            rb_obj.rotation_euler = bone_rot
            rb_obj.mmd_rigid.shape = shape
            rb_obj.mmd_rigid.size = size
            rb_obj.mmd_rigid.type = "0" if is_kinematic else "1"
            rb_obj.mmd_rigid.collision_group_number = 0
            rb_obj.mmd_rigid.collision_group_mask = [True]*16
            rb_obj.name = rb_name
            rb_obj.mmd_rigid.name_j = rb_name
            rb_obj.mmd_rigid.name_e = rb_name
            rb_obj.data.name = rb_name
            rb_obj.mmd_rigid.bone = bone_name
            
            # 设置物理参数
            rb = rb_obj.rigid_body
            rb.friction = friction
            rb.mass = mass
            rb.angular_damping = ang_damp
            rb.linear_damping = lin_damp
            rb.restitution = 0.0
            
            rb_objects[bone_name] = rb_obj
            print(f"[胸部物理] 创建：{rb_name}, type={shape}, mass={mass}")

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

            joint_name = sd["joint"]
            if joint_name in bpy.data.objects:
                joint_obj = bpy.data.objects[joint_name]
                print(f"[胸部物理] 跳过已存在的约束：{joint_name}")
                continue

            # 创建关节（使用 ensure_joint_group_object，与面板一致）
            joint_obj = FnRigidBody.new_joint_object(context, joint_grp_obj, FnModel.get_empty_display_size(root))
            
            # 计算中点位置
            mid = (rb1.location + rb2.location) / 2
            
            # 设置关节参数
            joint_obj.location = Vector(mid)
            joint_obj.rotation_euler = Euler((0, 0, 0))
            joint_obj.rigid_body_constraint.object1 = rb1
            joint_obj.rigid_body_constraint.object2 = rb2
            joint_obj.rigid_body_constraint.limit_lin_x_upper = sd.get("lin_x_hi", 0)
            joint_obj.rigid_body_constraint.limit_lin_y_upper = sd.get("lin_y_hi", 0)
            joint_obj.rigid_body_constraint.limit_lin_z_upper = sd.get("lin_z_hi", 0)
            joint_obj.rigid_body_constraint.limit_lin_x_lower = sd.get("lin_x_lo", 0)
            joint_obj.rigid_body_constraint.limit_lin_y_lower = sd.get("lin_y_lo", 0)
            joint_obj.rigid_body_constraint.limit_lin_z_lower = sd.get("lin_z_lo", 0)
            joint_obj.rigid_body_constraint.limit_ang_x_upper = sd.get("ang_x_hi", 0)
            joint_obj.rigid_body_constraint.limit_ang_y_upper = sd.get("ang_y_hi", 0)
            joint_obj.rigid_body_constraint.limit_ang_z_upper = sd.get("ang_z_hi", 0)
            joint_obj.rigid_body_constraint.limit_ang_x_lower = sd.get("ang_x_lo", 0)
            joint_obj.rigid_body_constraint.limit_ang_y_lower = sd.get("ang_y_lo", 0)
            joint_obj.rigid_body_constraint.limit_ang_z_lower = sd.get("ang_z_lo", 0)
            joint_obj.mmd_joint.name_j = joint_name.replace("J.", "")
            joint_obj.mmd_joint.name_e = joint_name.replace("J.", "")
            joint_obj.mmd_joint.spring_linear = Vector((sd.get("k_lin_x", 0), sd.get("k_lin_y", 0), sd.get("k_lin_z", 0)))
            joint_obj.mmd_joint.spring_angular = Vector((sd.get("k_ang_x", 0), sd.get("k_ang_y", 0), sd.get("k_ang_z", 0)))
            
            # 关闭碰撞
            joint_obj.rigid_body_constraint.disable_collisions = True

            print(f"[胸部物理] 创建弹簧：{joint_name}")

    def _get_spring_definitions(self):
        """
        返回 6 个核心弹簧约束的参数字典（已排除辅助约束）。
        全部为 GENERIC_SPRING，disable_collisions=True，阻尼=0.5。
        """
        def s(joint, rb1, rb2, **kw):
            for ax in 'xyz':
                for pre in (f'lin_{ax}', f'ang_{ax}'):
                    if pre not in kw:
                        kw[pre] = 0
            kw.update({"joint": joint, "rb1": rb1, "rb2": rb2})
            return kw

        defs = []

        for prefix in ('左', '右'):
            # J.胸上：胸親 → 胸上，角度限制 ang_z ±5°，K_z=100
            defs.append(s(
                f"J.{prefix}胸上", "胸親", f"{prefix}胸上",
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_z=100,
            ))
            # J.胸上 2：胸上 → 胸上 2，角度限制 ang_x ±10°，K 全 0（纯阻尼）
            defs.append(s(
                f"J.{prefix}胸上 2", f"{prefix}胸上", f"{prefix}胸上 2",
                ang_x_lo=-DEG10, ang_x_hi=DEG10,
            ))
            # J.胸下：胸親 → 胸下，角度限制 ang_x ±20° / ang_z ±5°，K_x=K_z=100
            defs.append(s(
                f"J.{prefix}胸下", "胸親", f"{prefix}胸下",
                ang_x_lo=-DEG20, ang_x_hi=DEG20,
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
