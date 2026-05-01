"""
自动胸部物理构建器
基于 MMD 标准 GENERIC_SPRING 刚体物理体系构建胸部物理，
参数来源于对真实 MMD 胸部物理参考文件的逆向分析。

物理结构总览：
  骨骼链（创建的骨骼）：
         胸親（单一锚点）
         ├── 左胸上 → 左胸上2（用户选中的权重骨骼）
         ├── 左胸下
         ├── 右胸上 → 右胸上2（用户选中的权重骨骼）
         └── 右胸下

  刚体 (7个):
    胸親 - KINEMATIC CAPSULE，mass=1.0，单一锚点，左右共用
    左胸上/右胸上 - ACTIVE CAPSULE，mass=0.05, damping=0.8
    左胸上2/右胸上2 - ACTIVE SPHERE,  mass=0.20, damping=0.8  ← 碰撞核心（用户选中骨骼）
    左胸下/右胸下 - ACTIVE CAPSULE，mass=0.05, damping=0.8

  弹簧约束 (9个，均为 GENERIC_SPRING，关闭碰撞):
    J.左/右胸上   - 胸親→胸上,   ang_z=±5°,        K_ang_z=100
    J.左/右胸上2  - 胸上→胸上2,  ang_x=±10°,       K=0 纯阻尼
    J.左/右胸下   - 胸親→胸下,   ang_x=±20°/z=±5°, K_ang_x/z=100
    J.左/右胸補助 - 胸上2↔胸下,  ang_x=±20°, lin_x=±8mm, K_ang=100, K_lin=50
    J.胸间辅      - 左胸上2↔右胸上2, xyz=±10°/±24mm, K=0 纯阻尼

"""

import bpy
import math
import mathutils


# ---------------------------------------------------------------------------
# 参考参数常量（来自 spring_result.json 逆向分析）
# ---------------------------------------------------------------------------

DEG5  = math.radians(5)
DEG10 = math.radians(10)
DEG20 = math.radians(20)

# 刚体参数: (shape, mass, friction, linear_damping, angular_damping, kinematic)
RB_PARAMS = {
    "胸親":     ("CAPSULE", 1.0,  0.5, 0.5, 0.5, True),
    "左胸上":   ("CAPSULE", 0.05, 0.0, 0.8, 0.8, False),
    "右胸上":   ("CAPSULE", 0.05, 0.0, 0.8, 0.8, False),
    "左胸上2":  ("SPHERE",  0.20, 0.0, 0.8, 0.8, False),
    "右胸上2":  ("SPHERE",  0.20, 0.0, 0.8, 0.8, False),
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _ensure_rigidbody_world(scene):
    if not scene.rigidbody_world:
        bpy.ops.rigidbody.world_add()
    scene.rigidbody_world.enabled = True


def _get_bone_world_pos(armature, bone_name):
    bone = armature.data.bones.get(bone_name)
    if bone is None:
        return mathutils.Vector((0, 0, 0))
    return armature.matrix_world @ bone.head_local


def _select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _create_empty_mesh_obj(name, location):
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    return obj


def _rb_collection(scene):
    rbc = scene.rigidbody_world.collection
    if rbc is None:
        col = bpy.data.collections.new("RigidBodyWorld")
        scene.rigidbody_world.collection = col
    return scene.rigidbody_world.collection


def _rbj_collection(scene):
    rbwc = scene.rigidbody_world.constraints
    if rbwc is None:
        col = bpy.data.collections.new("RigidBodyConstraints")
        scene.rigidbody_world.constraints = col
    return scene.rigidbody_world.constraints


# ---------------------------------------------------------------------------
# 主算子
# ---------------------------------------------------------------------------

class OBJECT_OT_auto_physics_builder(bpy.types.Operator):
    """自动构建符合 MMD 标准的胸部物理系统"""
    bl_idname = "object.auto_physics_builder"
    bl_label = "自动构建胸部物理"
    bl_description = "基于指定的胸部骨骼，自动创建完整骨骼链、刚体和弹簧约束"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene
        left_bone  = scene.left_chest_bone
        right_bone = scene.right_chest_bone

        if not left_bone or not right_bone:
            self.report({'ERROR'}, "请先指定左右胸部骨骼")
            return {'CANCELLED'}

        if left_bone not in armature.data.bones:
            self.report({'ERROR'}, f"左侧骨骼 '{left_bone}' 不存在")
            return {'CANCELLED'}
        if right_bone not in armature.data.bones:
            self.report({'ERROR'}, f"右侧骨骼 '{right_bone}' 不存在")
            return {'CANCELLED'}

        try:
            _ensure_rigidbody_world(scene)

            # 步骤 0：重命名并构建完整骨骼链
            self._build_chest_bone_chain(armature, left_bone, right_bone)

            # 步骤 1：创建刚体
            rb_objects = self._create_rigid_bodies(context, armature)

            # 步骤 2：创建弹簧约束
            self._create_spring_joints(context, armature, rb_objects)

            # 步骤 3：骨骼跟随刚体
            self._bind_bones_to_rb(armature, rb_objects)

            # 恢复选择
            bpy.ops.object.mode_set(mode='OBJECT')
            _select_only(armature)

            self.report({'INFO'}, "胸部物理系统构建完成")
        except Exception as exc:
            import traceback
            self.report({'ERROR'}, f"构建失败：{exc}")
            print(traceback.format_exc())
            return {'CANCELLED'}

        return {'FINISHED'}

    # ------------------------------------------------------------------
    # 步骤 0：重命名骨骼 + 构建完整骨骼链
    #
    #  用户选中的骨骼 = 胸部权重所在的骨骼 = 对应 左胸上2 / 右胸上2
    #  骨骼链最终结构:
    #    胸親 ── 左胸上 ── 左胸上2  ← 用户选中的骨骼（重命名）
    #     ↓           └─ 左胸下
    #     └─ 右胸上 ── 右胸上2
    #                └─ 右胸下
    # ------------------------------------------------------------------

    def _build_chest_bone_chain(self, armature, left_user_bone, right_user_bone):
        """
        1. 将用户选中的骨骼重命名为 左胸上2 / 右胸上2
        2. 创建左/右胸上（CAPSULE 的父骨骼）
        3. 创建左/右胸下（下方弹性支撑）
        4. 创建单一胸親（锚点）
        """
        print(f"[胸部物理] 构建骨骼链, left='{left_user_bone}', right='{right_user_bone}'")

        # 切换到编辑模式
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armature.data.edit_bones

        # 先处理左右两侧的骨骼（胸上、胸上2、胸下），然后创建单一胸親
        up1_bones = {}  # 保存左胸上/右胸上的引用
        down_bones = {}  # 保存左胸下/右胸下的引用
        ref_len = 0.05

        for user_name, prefix, sx in [(left_user_bone, '左', 1), (right_user_bone, '右', -1)]:
            # ----------------------------------------------------------
            # 0. 获取用户骨骼的编辑骨骼引用
            # ----------------------------------------------------------
            user_eb = eb.get(user_name)
            if user_eb is None:
                all_names = [b.name for b in eb]
                raise RuntimeError(f"找不到骨骼 '{user_name}'，可用骨骼: {all_names[:10]}")

            print(f"[胸部物理] 用户骨骼 '{user_name}' -> head={user_eb.head}, tail={user_eb.tail}")

            # 基准长度用于适配不同体型
            ref_len = max(user_eb.length, 0.05)
            user_head = user_eb.head.copy()
            user_tail = user_eb.tail.copy()

            # ----------------------------------------------------------
            # 1. 重命名用户骨骼为 左胸上2 / 右胸上2
            # ----------------------------------------------------------
            target_up2 = f"{prefix}胸上2"
            if user_name != target_up2:
                user_eb.name = target_up2
                print(f"[胸部物理] 重命名: '{user_name}' -> '{target_up2}'")
            # 重新获取引用（重命名后需要更新）
            up2_eb = eb.get(target_up2)

            # ----------------------------------------------------------
            # 2. 创建胸上（胸上2 的父骨骼，CAPSULE 刚体对应）
            # ----------------------------------------------------------
            target_up1 = f"{prefix}胸上"
            if target_up1 not in eb:
                up1 = eb.new(target_up1)
                # 胸上从胸上2 的 head 向上延伸
                up1.head = up2_eb.head + mathutils.Vector((sx * 0.05, 0.05, 0.05)) * ref_len
                up1.tail = up2_eb.head.copy()
                # 父级暂时设为 None，后面再挂到胸親下
                up1.parent = None
                up1.use_connect = False
                print(f"[胸部物理] 创建骨骼: '{target_up1}'")
            else:
                up1 = eb[target_up1]

            up1_bones[prefix] = up1

            # 将胸上2 的 parent 指向胸上（非连接）
            up2_eb.parent = up1
            up2_eb.use_connect = False

            # ----------------------------------------------------------
            # 3. 创建胸下（胸下方的弹性支撑）
            # ----------------------------------------------------------
            target_down = f"{prefix}胸下"
            if target_down not in eb:
                down = eb.new(target_down)
                down.head = up2_eb.tail.copy()
                down.tail = down.head + mathutils.Vector((sx * 0.05, -0.05, -0.8)) * ref_len
                down.parent = None  # 后面再挂到胸親下
                down.use_connect = False
                print(f"[胸部物理] 创建骨骼: '{target_down}'")
            else:
                down = eb[target_down]

            down_bones[prefix] = down

        # ----------------------------------------------------------
        # 4. 创建单一胸親（Kinematic 锚点）
        # ----------------------------------------------------------
        target_parent = "胸親"
        if target_parent not in eb:
            # 取左右胸上的中点作为锚点位置
            left_up1 = up1_bones.get('左')
            right_up1 = up1_bones.get('右')
            if left_up1 and right_up1:
                mid_head = (left_up1.head + right_up1.head) / 2
            elif left_up1:
                mid_head = left_up1.head
            else:
                mid_head = right_up1.head

            parent_bone = eb.new(target_parent)
            parent_bone.head = mid_head + mathutils.Vector((0, 0.08, 0.08)) * ref_len
            parent_bone.tail = mid_head.copy()
            parent_bone.parent = None
            parent_bone.use_connect = False
            print(f"[胸部物理] 创建骨骼: '{target_parent}'")
        else:
            parent_bone = eb[target_parent]

        # 将左右胸上的 parent 都指向同一胸親（非连接）
        for prefix in ('左', '右'):
            up1 = up1_bones.get(prefix)
            if up1:
                up1.parent = parent_bone
                up1.use_connect = False

        # 将左右胸下的 parent 都指向同一胸親（非连接）
        for prefix in ('左', '右'):
            down = down_bones.get(prefix)
            if down:
                down.parent = parent_bone
                down.use_connect = False

        # 验证：打印最终骨骼列表
        chest_names = [n for n in eb.keys if any(x in n for x in ("胸", "親"))]
        print(f"[胸部物理] 胸部相关骨骼: {sorted(chest_names)}")

        bpy.ops.object.mode_set(mode='OBJECT')

    # ------------------------------------------------------------------
    # 步骤 1：创建刚体
    # ------------------------------------------------------------------

    def _create_rigid_bodies(self, context, armature):
        """
        为每个定义的骨骼创建刚体对象。
        返回 dict: bone_name -> bpy.types.Object
        """
        scene = context.scene
        rb_col = _rb_collection(scene)
        rb_objects = {}

        for bone_name, (shape, mass, friction, lin_damp, ang_damp, is_kinematic) in RB_PARAMS.items():
            if bone_name not in armature.data.bones:
                print(f"[胸部物理] 跳过刚体 '{bone_name}'（骨骼不存在）")
                continue

            existing_name = f"RB_{bone_name}"
            if existing_name in bpy.data.objects:
                rb_objects[bone_name] = bpy.data.objects[existing_name]
                continue

            pos = _get_bone_world_pos(armature, bone_name)
            rb_obj = _create_empty_mesh_obj(existing_name, pos)

            if rb_obj.name not in rb_col.objects:
                rb_col.objects.link(rb_obj)

            _select_only(rb_obj)
            bpy.ops.rigidbody.object_add()

            rb = rb_obj.rigid_body
            rb.type = 'PASSIVE' if is_kinematic else 'ACTIVE'
            rb.kinematic = is_kinematic
            rb.collision_shape = shape
            rb.mass = mass
            rb.friction = friction
            rb.restitution = 0.0
            rb.linear_damping = lin_damp
            rb.angular_damping = ang_damp

            bone = armature.data.bones.get(bone_name)
            if bone:
                bl = max(bone.length, 0.02)
                rb_obj.scale = (bl * 0.5, bl * 0.5, bl * 0.5)

            rb_objects[bone_name] = rb_obj
            print(f"[胸部物理] 创建刚体: {bone_name}, shape={shape}, mass={mass}")

        return rb_objects

    # ------------------------------------------------------------------
    # 步骤 2：创建弹簧约束
    # ------------------------------------------------------------------

    def _create_spring_joints(self, context, armature, rb_objects):
        """
        创建 9 个 GENERIC_SPRING 刚体约束。
        """
        scene = context.scene
        rbj_col = _rbj_collection(scene)

        spring_defs = self._get_spring_definitions()

        for sd in spring_defs:
            rb1 = rb_objects.get(sd["rb1"])
            rb2 = rb_objects.get(sd["rb2"])
            if rb1 is None or rb2 is None:
                print(f"[胸部物理] 跳过约束（刚体不存在）: {sd['joint']}")
                continue

            if sd["joint"] in bpy.data.objects:
                continue

            mid = (rb1.location + rb2.location) / 2
            empty = bpy.data.objects.new(sd["joint"], None)
            empty.empty_display_type = 'ARROWS'
            empty.empty_display_size = 0.03
            empty.location = mid
            bpy.context.collection.objects.link(empty)

            if empty.name not in rbj_col.objects:
                rbj_col.objects.link(empty)

            _select_only(empty)
            bpy.ops.rigidbody.constraint_add(type='GENERIC_SPRING')

            rbc = empty.rigid_body_constraint
            rbc.object1 = rb1
            rbc.object2 = rb2
            rbc.disable_collisions = True

            # 线性限制
            for axis in 'xyz':
                lo = sd.get(f"lin_{axis}_lo", 0)
                hi = sd.get(f"lin_{axis}_hi", 0)
                use_lim = (lo != 0 or hi != 0)
                setattr(rbc, f"use_limit_lin_{axis}", use_lim)
                setattr(rbc, f"limit_lin_{axis}_lower", lo)
                setattr(rbc, f"limit_lin_{axis}_upper", hi)

            # 角度限制
            for axis in 'xyz':
                lo = sd.get(f"ang_{axis}_lo", 0)
                hi = sd.get(f"ang_{axis}_hi", 0)
                use_lim = (lo != 0 or hi != 0)
                setattr(rbc, f"use_limit_ang_{axis}", use_lim)
                setattr(rbc, f"limit_ang_{axis}_lower", lo)
                setattr(rbc, f"limit_ang_{axis}_upper", hi)

            # 线性弹簧
            for axis in 'xyz':
                k = sd.get(f"k_lin_{axis}", 0)
                setattr(rbc, f"use_spring_{axis}", k != 0)
                setattr(rbc, f"spring_stiffness_{axis}", k)
                setattr(rbc, f"spring_damping_{axis}", 0.5)

            # 角度弹簧
            for axis in 'xyz':
                k = sd.get(f"k_ang_{axis}", 0)
                setattr(rbc, f"use_spring_ang_{axis}", k != 0)
                setattr(rbc, f"spring_stiffness_ang_{axis}", k)
                setattr(rbc, f"spring_damping_ang_{axis}", 0.5)

            print(f"[胸部物理] 创建弹簧: {sd['joint']}")

    def _get_spring_definitions(self):
        """
        返回 9 个弹簧约束的参数字典。
        全部为 GENERIC_SPRING，disable_collisions=True，阻尼=0.5。
        """
        def s(joint, rb1, rb2, **kw):
            for ax in 'xyz':
                for pre in (f'lin_{ax}', f'ang_{ax}'):
                    if pre not in kw:
                        kw[pre] = 0
                for pre in (f'k_lin_{ax}', f'k_ang_{ax}'):
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
            # J.胸上2：胸上 → 胸上2，角度限制 ang_x ±10°，K 全 0（纯阻尼）
            defs.append(s(
                f"J.{prefix}胸上2", f"{prefix}胸上", f"{prefix}胸上2",
                ang_x_lo=-DEG10, ang_x_hi=DEG10,
            ))
            # J.胸下：胸親 → 胸下，角度限制 ang_x ±20° / ang_z ±5°，K_x=K_z=100
            defs.append(s(
                f"J.{prefix}胸下", "胸親", f"{prefix}胸下",
                ang_x_lo=-DEG20, ang_x_hi=DEG20,
                ang_z_lo=-DEG5, ang_z_hi=DEG5,
                k_ang_x=100, k_ang_z=100,
            ))
            # J.胸補助：胸上2 ↔ 胸下，角度限制 + 线性限制
            defs.append(s(
                f"J.{prefix}胸補助", f"{prefix}胸上2", f"{prefix}胸下",
                lin_x_lo=-0.008, lin_x_hi=0.008,
                ang_x_lo=-DEG20, ang_x_hi=DEG20,
                k_lin_x=50, k_lin_z=50,
                k_ang_x=100, k_ang_z=100,
            ))

        # J.胸间辅：左胸上2 ↔ 右胸上2
        defs.append(s(
            "J.胸间辅", "左胸上2", "右胸上2",
            lin_x_lo=-0.024, lin_x_hi=0.024,
            lin_y_lo=-0.024, lin_y_hi=0.024,
            lin_z_lo=-0.024, lin_z_hi=0.024,
            ang_x_lo=-DEG10, ang_x_hi=DEG10,
            ang_y_lo=-DEG10, ang_y_hi=DEG10,
            ang_z_lo=-DEG10, ang_z_hi=DEG10,
        ))

        return defs

    # ------------------------------------------------------------------
    # 步骤 3：骨骼跟随刚体
    # ------------------------------------------------------------------

    def _bind_bones_to_rb(self, armature, rb_objects):
        """
        在姿态模式下，为每个动态刚体对应的骨骼添加 CHILD_OF 约束，
        使骨骼跟随刚体运动。
        """
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode='POSE')

        for bone_name, rb_obj in rb_objects.items():
            pbone = armature.pose.bones.get(bone_name)
            if pbone is None:
                continue

            con_name = f"跟随刚体_{bone_name}"
            if any(c.name == con_name for c in pbone.constraints):
                continue

            con = pbone.constraints.new('CHILD_OF')
            con.name = con_name
            con.target = rb_obj
            con.use_scale_x = False
            con.use_scale_y = False
            con.use_scale_z = False
            try:
                con.inverse_matrix = rb_obj.matrix_world.inverted()
            except Exception:
                con.inverse_matrix = mathutils.Matrix.Identity(4)

        bpy.ops.object.mode_set(mode='OBJECT')


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)
    if not hasattr(bpy.types.Scene, "left_chest_bone"):
        bpy.types.Scene.left_chest_bone = bpy.props.StringProperty(
            name="左胸部骨骼", description="选择左侧胸部骨骼（对应左胸上2，SPHERE碰撞核心）", default=""
        )
    if not hasattr(bpy.types.Scene, "right_chest_bone"):
        bpy.types.Scene.right_chest_bone = bpy.props.StringProperty(
            name="右胸部骨骼", description="选择右侧胸部骨骼（对应右胸上2，SPHERE碰撞核心）", default=""
        )


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)
    for prop in ("left_chest_bone", "right_chest_bone"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)


if __name__ == "__main__":
    register()
