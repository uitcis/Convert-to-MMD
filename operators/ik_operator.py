import bpy
from mathutils import Vector
from math import radians
from .. import bone_utils

# IK约束相关函数
def add_ik_constraint(bone, target, subtarget, chain_count, iterations, ik_min_x=None, ik_max_x=None, use_ik_limit_x=False, ik_min_y=0, ik_max_y=0, use_ik_limit_y=False, ik_min_z=0, ik_max_z=0, use_ik_limit_z=False):
    ik_constraint = bone.constraints.new(type='IK')
    ik_constraint.name = "IK"
    ik_constraint.target = target
    ik_constraint.subtarget = subtarget
    ik_constraint.chain_count = chain_count
    ik_constraint.iterations = iterations
    
    # 设置X轴限制
    if ik_min_x is not None:
        bone.ik_min_x = ik_min_x
    if ik_max_x is not None:
        bone.ik_max_x = ik_max_x
    bone.use_ik_limit_x = use_ik_limit_x
    
    # 设置Y轴限制
    if ik_min_y is not None:
        bone.ik_min_y = ik_min_y
    if ik_max_y is not None:
        bone.ik_max_y = ik_max_y
    bone.use_ik_limit_y = use_ik_limit_y
    
    # 设置Z轴限制
    if ik_min_z is not None:
        bone.ik_min_z = ik_min_z
    if ik_max_z is not None:
        bone.ik_max_z = ik_max_z
    bone.use_ik_limit_z = use_ik_limit_z

def add_limit_rotation_constraint(bone, influence=1, use_limit_x=False, min_x=None, max_x=None, owner_space='LOCAL'):
    limit_constraint = bone.constraints.new(type='LIMIT_ROTATION')
    limit_constraint.name = "mmd_ik_limit_override"
    limit_constraint.influence = influence
    limit_constraint.use_limit_x = use_limit_x
    limit_constraint.owner_space = owner_space
    
    if min_x is not None:
        limit_constraint.min_x = min_x
    if max_x is not None:
        limit_constraint.max_x = max_x

def add_damped_track_constraint(bone, target, subtarget, influence=0):
    damped_track_constraint = bone.constraints.new(type='DAMPED_TRACK')
    damped_track_constraint.name = "mmd_ik_target_override"
    damped_track_constraint.target = target
    damped_track_constraint.subtarget = subtarget
    damped_track_constraint.influence = influence

def clear_ik_constraints(bone):
    """清除本插件添加的旧约束，避免重复执行时约束叠加导致IK失效。

    Args:
        bone: 姿态骨骼（PoseBone）
    """
    managed_names = {"IK", "mmd_ik_limit_override", "mmd_ik_target_override"}
    for constraint in list(bone.constraints):
        if constraint.name in managed_names:
            bone.constraints.remove(constraint)

LEG_BONE_NAMES = frozenset({
    "左足", "右足", "左ひざ", "右ひざ", "左足首", "右足首",
    "左足先EX", "右足先EX",
    "左足D", "右足D", "左ひざD", "右ひざD", "左足首D", "右足首D",
})


def compute_mesh_ground_z(armature_obj):
    """计算绑定网格在骨架局部空间的最低 Z（用于足IK親骨高度）。

    只统计权重挂在腿骨（足/ひざ/足首/足先EX 及对应 D 骨）上的顶点，
    避免被脚部以外的杂散几何带偏；完全没有腿骨权重顶点时回退到全部顶点。
    返回 (最低Z, 参与计算的网格数, 是否使用腿骨权重)；没有可用网格时返回 (None, 0, False)。
    """
    meshes = bone_utils.get_bound_meshes(armature_obj)
    if not meshes:
        return None, 0, False

    armature_inverse = armature_obj.matrix_world.inverted()
    try:
        import numpy as np
    except ImportError:
        np = None

    def load_z_values(mesh_obj):
        mesh = mesh_obj.data
        row = (armature_inverse @ mesh_obj.matrix_world)[2]
        if np is not None:
            coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", coords)
            coords = coords.reshape(-1, 3)
            return (coords @ np.array([row[0], row[1], row[2]], dtype=np.float32)
                    + row[3])
        return [row[0] * v.co.x + row[1] * v.co.y + row[2] * v.co.z + row[3]
                for v in mesh.vertices]

    def min_of(values, indices=None):
        if np is not None:
            picked = values if indices is None else values[indices]
            return float(picked.min())
        picked = values if indices is None else [values[i] for i in indices]
        return min(picked)

    checked = 0
    leg_min = None
    leg_vertex_count = 0

    # 第一轮：只统计腿骨权重顶点
    for mesh_obj in meshes:
        mesh = mesh_obj.data
        if mesh is None or len(mesh.vertices) == 0:
            continue
        try:
            z_values = load_z_values(mesh_obj)
            leg_group_indices = {vg.index for vg in mesh_obj.vertex_groups
                                 if vg.name in LEG_BONE_NAMES}
            if leg_group_indices:
                indices = [
                    v.index for v in mesh.vertices
                    if any(g.weight > 0 and g.group in leg_group_indices
                           for g in v.groups)
                ]
                if indices:
                    leg_vertex_count += len(indices)
                    mesh_min_z = min_of(z_values, indices)
                    leg_min = mesh_min_z if leg_min is None else min(leg_min, mesh_min_z)
            checked += 1
        except Exception as exc:
            print(f"[MMD IK] 跳过网格 {mesh_obj.name}: {exc}")

    if leg_min is not None:
        return leg_min, checked, True

    # 第二轮（回退）：没有任何腿骨权重顶点时，用全部顶点最低点
    all_min = None
    for mesh_obj in meshes:
        mesh = mesh_obj.data
        if mesh is None or len(mesh.vertices) == 0:
            continue
        try:
            mesh_min_z = min_of(load_z_values(mesh_obj))
            all_min = mesh_min_z if all_min is None else min(all_min, mesh_min_z)
        except Exception as exc:
            print(f"[MMD IK] 跳过网格 {mesh_obj.name}: {exc}")

    if all_min is None:
        return None, 0, False
    return all_min, checked, False


# IK操作类
class OBJECT_OT_add_ik(bpy.types.Operator):
    """为骨架添加MMD IK"""
    bl_idname = "object.add_mmd_ik"
    bl_label = "Add MMD IK"

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "没有选择骨架对象")
            return {'CANCELLED'}

        original_mode = context.mode
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)
        if original_mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones
        required_bones = ['左ひざ', '右ひざ', '左足首', '右足首', '全ての親']
        missing_bones = [name for name in required_bones if name not in edit_bones]
        if missing_bones:
            if context.mode != original_mode:
                bpy.ops.object.mode_set(mode=restore_mode)
            self.report({'ERROR'}, f"缺失基础骨骼: {', '.join(missing_bones)}，请先补全骨骼")
            return {'CANCELLED'}

        # 计算骨架高度和bone_length
        bone_length = bone_utils.calculate_bone_length(edit_bones)
        print(f"骨架高度: {bone_length * 8}")
        print(f"bone_length: {bone_length}")
        # 脚底高度：优先只取腿骨权重顶点的最低点；取不到网格时回退到脚踝末端
        mesh_ground_z, mesh_count, used_leg_weights = compute_mesh_ground_z(obj)
        if mesh_ground_z is None:
            ground_z = min(edit_bones["左足首"].tail.z, edit_bones["右足首"].tail.z)
            self.report({'WARNING'},
                        "未找到绑定到该骨架的网格，足IK親高度回退为脚踝末端最低点")
        elif used_leg_weights:
            ground_z = mesh_ground_z
            self.report({'INFO'},
                        f"足IK親高度取 {mesh_count} 个绑定网格中腿骨权重顶点的最低点"
                        f"（骨架局部 Z={ground_z:.4f}）")
        else:
            ground_z = mesh_ground_z
            self.report({'WARNING'},
                        f"未找到任何腿骨权重顶点，足IK親高度回退为全部顶点最低点"
                        f"（骨架局部 Z={ground_z:.4f}），可能受杂散几何影响")
        # IK骨骼属性定义
        IKbone_properties = {
            "左足IK親": {"head": Vector((edit_bones["左ひざ"].tail.x, edit_bones["左ひざ"].tail.y, ground_z)),
                       "tail": edit_bones["左ひざ"].tail, "parent": "全ての親", "use_connect": False},
            "左足ＩＫ": {"head": edit_bones["左ひざ"].tail,
                      "tail": edit_bones["左ひざ"].tail + Vector((0, bone_length * 0.5, 0)), "parent": "左足IK親", "use_connect": False},
            "左つま先ＩＫ": {"head": edit_bones["左足首"].tail,
                         "tail": edit_bones["左足首"].tail + Vector((0, 0, -bone_length*0.4)), "parent": "左足ＩＫ", "use_connect": False},
            "右足IK親": {"head": Vector((edit_bones["右ひざ"].tail.x, edit_bones["右ひざ"].tail.y, ground_z)),
                       "tail": edit_bones["右ひざ"].tail, "parent": "全ての親", "use_connect": False},
            "右足ＩＫ": {"head": edit_bones["右ひざ"].tail,
                      "tail": edit_bones["右ひざ"].tail + Vector((0, bone_length * 0.5, 0)), "parent": "右足IK親", "use_connect": False},
            "右つま先ＩＫ": {"head": edit_bones["右足首"].tail,
                         "tail": edit_bones["右足首"].tail + Vector((0, 0, -bone_length*0.4)), "parent": "右足ＩＫ", "use_connect": False}
        }

        # 创建IK骨骼
        for bone_name, properties in IKbone_properties.items():
            bone_utils.create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], use_connect=False, parent_name=properties["parent"], use_deform=False)

        # 关键修复：退出编辑模式使pose数据与新骨骼同步后再添加约束。
        # 编辑模式下pose.bones是进入编辑模式前的快照，不含新建的IK目标骨骼
        # （如 左足ＩＫ），此时创建的IK约束subtarget无法正确解析，导致IK不生效。
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # 获取骨骼对象并添加约束（此时pose.bones已包含新建的IK骨骼）
        pose_bones = obj.pose.bones
        required_pose_bones = ['左ひざ', '右ひざ', '左足首', '右足首',
                               '左足ＩＫ', '右足ＩＫ', '左つま先ＩＫ', '右つま先ＩＫ']
        missing_pose_bones = [name for name in required_pose_bones if name not in pose_bones]
        if missing_pose_bones:
            if context.mode != original_mode:
                bpy.ops.object.mode_set(mode=restore_mode)
            self.report({'ERROR'}, f"姿态骨骼同步失败: {', '.join(missing_pose_bones)}")
            return {'CANCELLED'}

        left_hiza = pose_bones["左ひざ"]
        left_kutu = pose_bones["左足首"]
        right_hiza = pose_bones["右ひざ"]
        right_kutu = pose_bones["右足首"]

        # 清除旧约束（幂等：重复执行时避免IK约束叠加导致工作异常）
        for pose_bone in (left_hiza, left_kutu, right_hiza, right_kutu):
            clear_ik_constraints(pose_bone)

        # 为左ひざ添加 IK 和旋转限制约束
        add_ik_constraint(left_hiza, obj, "左足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True,use_ik_limit_y=True,use_ik_limit_z=True)
        add_limit_rotation_constraint(left_hiza, use_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        add_ik_constraint(right_hiza, obj, "右足ＩＫ", 2, 200, ik_min_x=radians(0), ik_max_x=radians(180), use_ik_limit_x=True,use_ik_limit_y=True,use_ik_limit_z=True)
        add_limit_rotation_constraint(right_hiza, use_limit_x=True, min_x=radians(0.5), max_x=radians(180))

        add_ik_constraint(left_kutu, obj, "左つま先ＩＫ", 1, 200)
        add_damped_track_constraint(left_kutu, obj, "左ひざ")

        add_ik_constraint(right_kutu, obj, "右つま先ＩＫ", 1, 200)
        add_damped_track_constraint(right_kutu, obj, "右ひざ")

        # 恢复进入时的模式（context.mode 的值需转换为 mode_set 接受的枚举）
        if context.mode != original_mode:
            bpy.ops.object.mode_set(mode=restore_mode)

        self.report({'INFO'}, "已添加MMD IK约束（重复执行会自动替换旧约束）")
        return {'FINISHED'}