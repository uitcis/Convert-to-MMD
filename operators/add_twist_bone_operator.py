"""
腕/肘捩骨骼构建模块

对腕部和手部骨骼进行捩骨骼设置，包括：
    1. 创建捩骨骼（主捩 + 3个细分 + shadow/dummy）
    2. 设置 TRANSFORM / COPY_TRANSFORMS 约束
    3. 分配顶点权重（沿骨骼方向线性分段）
"""

import bpy
import math
from mathutils import Vector
from bpy.props import StringProperty


# ---------------------------------------------------------------------------
# 捩骨骼约束配置
# ---------------------------------------------------------------------------

# 每个细分索引对应的旋转限制角度（度）
_TWIST_ROTATION_LIMITS = {
    1: (-45, 45),
    2: (-90, 90),
    3: (-135, 135),
}

# 骨骼类型配置：(基础骨名键, 捩名前缀, 捩类型标识)
_TWIST_CONFIG = [
    # (基础骨骼名, [主捩, 细分1, 细分2, 细分3])
    ("左腕", ["左腕捩", "左腕捩1", "左腕捩2", "左腕捩3"]),
    ("左ひじ", ["左手捩", "左手捩1", "左手捩2", "左手捩3"]),
    ("右腕", ["右腕捩", "右腕捩1", "右腕捩2", "右腕捩3"]),
    ("右ひじ", ["右手捩", "右手捩1", "右手捩2", "右手捩3"]),
]


class OBJECT_OT_add_twist_bone(bpy.types.Operator):
    """对腕部和手部骨骼进行捩骨骼设置"""
    bl_idname = "object.add_twist_bone"
    bl_label = "添加腕捩骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请先选择一个骨架对象")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        for bone_name, twist_names in _TWIST_CONFIG:
            if bone_name not in edit_bones:
                continue

            self._create_twist_bone_chain(edit_bones, bone_name, twist_names)

        self._setup_all_constraints(obj)
        self._setup_all_weights(obj)

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.create_bone_group()
        self.report({'INFO'}, "成功拆分腕捩骨骼并设置权重和约束")
        return {'FINISHED'}

    # ------------------------------------------------------------------
    # 创建捩骨骼链
    # ------------------------------------------------------------------
    def _create_twist_bone_chain(self, edit_bones, base_name, twist_names):
        base_bone = edit_bones[base_name]
        parent_bone = base_bone.parent
        children_bones = [child for child in edit_bones if child.parent == base_bone]

        bone_head = base_bone.head
        bone_tail = base_bone.tail
        bone_vector = bone_tail - bone_head
        bone_length = bone_vector.length

        # 创建所有捩骨骼
        twist_bones = []
        for i, twist_name in enumerate(twist_names):
            twist_bone = edit_bones.new(twist_name)

            if i == 0:
                t = 0.6
                twist_head = bone_head + bone_vector * t
                twist_tail = bone_head + bone_vector * 1.0
                twist_bone.head = twist_head
                twist_bone.tail = twist_tail
                twist_bone.roll = base_bone.roll
            else:
                t = i * 0.2
                twist_head = bone_head + bone_vector * t
                twist_bone.head = twist_head
                twist_bone.tail = twist_head + Vector((0, 0, 0.08))
                twist_bone.roll = 0.0

            twist_bone.use_connect = False
            twist_bones.append(twist_bone)

        # 为细分的捩骨骼创建shadow/dummy
        for i, twist_bone in enumerate(twist_bones):
            if i == 0:
                continue

            if len(twist_bones) > 3:
                shadow_head = (twist_bones[2].head + twist_bones[3].head) / 2
            elif len(twist_bones) > 2:
                shadow_head = twist_bones[2].head
            else:
                shadow_head = twist_bone.head

            # shadow骨骼
            shadow_name = f"_shadow_{twist_bone.name}"
            shadow_bone = edit_bones.new(shadow_name)
            shadow_bone.head = shadow_head
            shadow_bone.tail = shadow_head + Vector((0, 0, 0.08))
            shadow_bone.parent = base_bone
            shadow_bone.use_connect = False
            shadow_bone.roll = 0.0

            # dummy骨骼
            dummy_name = f"_dummy_{twist_bone.name}"
            dummy_bone = edit_bones.new(dummy_name)
            dummy_bone.head = shadow_head
            dummy_bone.tail = shadow_head + Vector((0, 0, 0.08))

            main_twist_name = twist_bone.name.replace("1", "").replace("2", "").replace("3", "")
            dummy_bone.parent = edit_bones.get(main_twist_name, base_bone)
            dummy_bone.use_connect = False
            dummy_bone.roll = 0.0

        # 设置捩骨骼父级
        for twist_bone in twist_bones:
            twist_bone.parent = base_bone

        # 移动原骨骼子级到主捩下
        if twist_bones:
            for child in children_bones:
                original_head = child.head.copy()
                original_tail = child.tail.copy()
                child.parent = twist_bones[0]
                child.use_connect = False
                child.head = original_head
                child.tail = original_tail

    # ------------------------------------------------------------------
    # 约束设置（参数化消除腕/手重复）
    # ------------------------------------------------------------------
    def _setup_all_constraints(self, obj):
        """为所有捩骨骼添加约束"""
        bpy.ops.object.mode_set(mode='POSE')
        pose_bones = obj.pose.bones

        # 锁定捩骨骼移动和X/Z轴旋转
        for bone in pose_bones:
            if "腕捩" in bone.name or "手捩" in bone.name:
                bone.lock_location[0] = True
                bone.lock_location[1] = True
                bone.lock_location[2] = True
                bone.lock_rotation[0] = True
                bone.lock_rotation[1] = False
                bone.lock_rotation[2] = True

        for side in ('左', '右'):
            self._setup_twist_constraints(pose_bones, obj, side, "腕捩")
            self._setup_twist_constraints(pose_bones, obj, side, "手捩")
            self._setup_shadow_constraints(pose_bones, obj, side, "腕捩")
            self._setup_shadow_constraints(pose_bones, obj, side, "手捩")

    @staticmethod
    def _setup_twist_constraints(pose_bones, obj, side, twist_type):
        """为指定类型的捩骨骼添加TRANSFORM约束"""
        for i in range(1, 4):
            bone_name = f"{side}{twist_type}{i}"
            if bone_name not in pose_bones:
                continue

            bone = pose_bones[bone_name]

            # 清除现有约束
            for constraint in list(bone.constraints):
                bone.constraints.remove(constraint)

            tc = bone.constraints.new('TRANSFORM')
            tc.name = "mmd_additional_rotation"
            tc.target = obj
            tc.subtarget = f"_shadow{bone_name.replace(side+twist_type, '_'+side+twist_type)}"
            tc.influence = 1.0
            tc.use_motion_extrapolate = True
            tc.owner_space = 'LOCAL'
            tc.target_space = 'LOCAL'
            tc.map_from = 'ROTATION'
            tc.map_to = 'ROTATION'
            tc.from_rotation_mode = 'XYZ'
            tc.to_euler_order = 'XYZ'
            tc.mix_mode_rot = 'AFTER'

            # 旋转范围
            tc.from_min_x_rot = math.radians(-180.0)
            tc.from_min_y_rot = math.radians(-180.0)
            tc.from_min_z_rot = math.radians(-180.0)
            tc.from_max_x_rot = math.radians(180.0)
            tc.from_max_y_rot = math.radians(180.0)
            tc.from_max_z_rot = math.radians(180.0)

            lo, hi = _TWIST_ROTATION_LIMITS[i]
            tc.to_min_x_rot = math.radians(lo)
            tc.to_min_y_rot = math.radians(lo)
            tc.to_min_z_rot = math.radians(lo)
            tc.to_max_x_rot = math.radians(hi)
            tc.to_max_y_rot = math.radians(hi)
            tc.to_max_z_rot = math.radians(hi)

    @staticmethod
    def _setup_shadow_constraints(pose_bones, obj, side, twist_type):
        """为shadow骨骼添加COPY_TRANSFORMS约束"""
        for i in range(1, 4):
            shadow_name = f"_shadow_{side}{twist_type}{i}"
            if shadow_name not in pose_bones:
                continue

            bone = pose_bones[shadow_name]

            for constraint in list(bone.constraints):
                bone.constraints.remove(constraint)

            cc = bone.constraints.new('COPY_TRANSFORMS')
            cc.name = "mmd_tools_at_dummy"
            cc.target = obj
            cc.subtarget = f"_dummy_{side}{twist_type}{i}"
            cc.influence = 1.0
            cc.owner_space = 'POSE'
            cc.target_space = 'POSE'

    # ------------------------------------------------------------------
    # 权重设置（参数化消除腕/手重复）
    # ------------------------------------------------------------------
    @staticmethod
    def _setup_all_weights(obj):
        """设置所有捩骨骼的权重"""
        mesh_objects = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.parent == obj]

        for mesh in mesh_objects:
            bpy.context.view_layer.objects.active = mesh
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')

            vertex_groups = mesh.vertex_groups

            for side in ("左", "右"):
                # 腕捩权重
                OBJECT_OT_add_twist_bone._distribute_twist_weights(
                    mesh, vertex_groups, obj,
                    base_name=f"{side}腕",
                    main_twist_name=f"{side}腕捩",
                    twist_type="腕捩",
                    label="腕部",
                )
                # 手捩权重
                OBJECT_OT_add_twist_bone._distribute_twist_weights(
                    mesh, vertex_groups, obj,
                    base_name=f"{side}ひじ",
                    main_twist_name=f"{side}手捩",
                    twist_type="手捩",
                    label="肘部",
                )

    @staticmethod
    def _distribute_twist_weights(mesh, vertex_groups, armature, base_name, main_twist_name, twist_type, label):
        """
        将基础骨骼的权重重新分配到捩骨骼链上

        沿骨骼方向分为五段：基础(0-20%) -> 主捩(20-40%) -> 细分1(40-60%) -> 细分2(60-80%) -> 细分3(80-100%)
        """
        if base_name not in vertex_groups:
            return

        base_group = vertex_groups[base_name]
        twist_names = [main_twist_name, f"{main_twist_name}1", f"{main_twist_name}2", f"{main_twist_name}3"]

        # 创建/获取捩骨骼的顶点组
        twist_groups = []
        for tn in twist_names:
            if tn not in vertex_groups:
                vg = vertex_groups.new(name=tn)
            else:
                vg = vertex_groups[tn]
            twist_groups.append(vg)

        # 获取基础骨骼世界坐标
        pose_bones = armature.pose.bones
        head_world = tail_world = None
        if base_name in pose_bones:
            pb = pose_bones[base_name]
            head_world = armature.matrix_world @ pb.head
            tail_world = armature.matrix_world @ pb.tail

        for v in mesh.data.vertices:
            # 查找原权重
            base_weight = 0.0
            for g in v.groups:
                if g.group == base_group.index:
                    base_weight = g.weight
                    break

            if base_weight <= 0:
                continue

            # 清除原权重
            base_group.remove([v.index])

            # 计算顶点在骨骼方向上的投影位置
            pos = 0.5  # 默认值
            if head_world is not None and tail_world is not None:
                bv = tail_world - head_world
                bl = bv.length
                if bl > 0:
                    vw = mesh.matrix_world @ v.co
                    proj_len = (vw - head_world).dot(bv.normalized())
                    pos = max(0, min(1, proj_len / bl))

            # 五段线性权重计算
            w_base   = max(0, 1.0 - pos * 5)              # 基础 (0-20%)
            w_main   = max(0, pos * 5 - 4)                 # 主捩 (80-100%)
            w_t1     = max(0, min(1.0, pos * 5 - 1, 2 - pos * 5))  # 细分1 (20-40%)
            w_t2     = max(0, min(1.0, pos * 5 - 2, 3 - pos * 5))  # 细分2 (40-60%)
            w_t3     = max(0, min(1.0, pos * 5 - 3, 4 - pos * 5))  # 细分3 (60-80%)

            total_base = w_base + w_main + w_t1 + w_t2 + w_t3
            scale = 0.65

            if total_base > 0:
                weights = [w_main / total_base * scale, w_t1 / total_base * scale,
                           w_t2 / total_base * scale, w_t3 / total_base * scale,
                           w_base / total_base * scale]
            else:
                weights = [0.2, 0.2, 0.3, 0.2, 0.1]

            # 应用权重：顺序=主捩, 细分1, 细分2, 细分3, 基础
            twist_groups[0].add([v.index], weights[0] * base_weight, 'REPLACE')
            twist_groups[1].add([v.index], weights[1] * base_weight, 'REPLACE')
            twist_groups[2].add([v.index], weights[2] * base_weight, 'REPLACE')
            twist_groups[3].add([v.index], weights[3] * base_weight, 'REPLACE')
            base_group.add([v.index], weights[4] * base_weight, 'REPLACE')


def register():
    bpy.utils.register_class(OBJECT_OT_add_twist_bone)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_twist_bone)


if __name__ == "__main__":
    register()
