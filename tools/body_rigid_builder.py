"""
身体刚体构建模块（简易模式）

包含：
    1. 基于骨骼权重的圆柱拟合算法（特征值分解）
    2. OBJECT_OT_build_simple_body_rigid 操作符
"""

import math
import traceback

import bpy

from mathutils import Vector, Matrix

from .. import bone_utils

from .physics_utils import (
    _check_memory_and_gc, _solve_eigen_3x3_sym, _build_rotation_matrix,
    MMD_TOOLS_AVAILABLE, FnRigidBody, FnModel
)


# ---------------------------------------------------------------------------
# 简易身体刚体生成（基于骨骼权重）
# ---------------------------------------------------------------------------

def calculate_simple_body_rigid_params(armature, bone_names=None):
    """
    简易身体刚体参数计算（基于骨骼权重）

    圆柱拟合步骤：
        1. 第一步：获取轴线（通过协方差矩阵特征值分解确定方向）
        2. 第二步：获取半径（计算所有顶点到轴线的最大垂直距离）
        3. 第三步：获取圆柱尺寸（计算顶点在轴线方向上的投影范围）
        4. 第四步：圆柱的中心即为刚体位置（计算几何中心）

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

    # 一次性建立“顶点组名 -> [(世界坐标, 权重)]”索引。
    # 原实现每个骨骼都重新遍历全部顶点及其 groups，复杂度为
    # O(骨骼 × 顶点 × 组数)，在数万顶点、数百骨骼的模型上耗时数十秒；
    # 这里只扫描一遍网格，结果（顶点顺序与权重）与原实现完全一致。
    weighted_vertices_by_group = {}
    for mesh_obj in mesh_objs:
        mesh_matrix = mesh_obj.matrix_world
        index_to_name = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
        for vertex in mesh_obj.data.vertices:
            for group in vertex.groups:
                if group.weight > 0.4:
                    group_name = index_to_name.get(group.group)
                    if group_name is not None:
                        weighted_vertices_by_group.setdefault(group_name, []).append(
                            (mesh_matrix @ Vector(vertex.co), group.weight)
                        )

    for bone_idx, bone_name in enumerate(bone_names):
        if not _check_memory_and_gc():
            break

        if bone_name not in armature.data.bones:
            continue

        bone = armature.data.bones[bone_name]

        # 获取骨骼对应顶点组权重顶点（保留权重值）
        weighted_vertices = weighted_vertices_by_group.get(bone_name)

        if not weighted_vertices:
            continue

        vertices_world = [v for v, _ in weighted_vertices]
        weights = [w for _, w in weighted_vertices]
        n = len(vertices_world)

        total_weight = sum(weights)
        if total_weight > 0:
            centroid = sum((v * w for v, w in weighted_vertices), Vector()) / total_weight
        else:
            centroid = sum((v for v in vertices_world), Vector()) / n

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

        # 获取轴线（特征值分解）
        axis_dir = None

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
                eigenvalues, eigenvectors = _solve_eigen_3x3_sym(cov_matrix)

                max_eigen_idx = 0
                max_eigen_val = eigenvalues[0]
                for i in range(1, 3):
                    if eigenvalues[i] > max_eigen_val:
                        max_eigen_val = eigenvalues[i]
                        max_eigen_idx = i

                axis_dir = Vector(eigenvectors[max_eigen_idx])

                bone_head_world = armature.matrix_world @ bone.head_local
                bone_tail_world = armature.matrix_world @ bone.tail_local
                bone_dir = (bone_tail_world - bone_head_world).normalized()

                if axis_dir.dot(bone_dir) < 0:
                    axis_dir = -axis_dir

                if abs(axis_dir.dot(bone_dir)) < 0.5:
                    axis_dir = bone_dir.copy()

                if axis_dir.length >= 0.0001:
                    axis_dir.normalize()
            except Exception:
                pass

        # 回退到骨骼方向
        if axis_dir is None:
            bone_head_world = armature.matrix_world @ bone.head_local
            bone_tail_world = armature.matrix_world @ bone.tail_local
            axis_dir = (bone_tail_world - bone_head_world).normalized()

        # 投影计算：构建正交基
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

        u = (u - u.dot(axis_dir) * axis_dir).normalized()
        v = axis_dir.cross(u).normalized()

        # 圆拟合（最小二乘法）
        proj_x = [v_world.dot(u) for v_world in vertices_world]
        proj_y = [v_world.dot(v) for v_world in vertices_world]

        # 正规方程 (AᵀA)x = Aᵀb：A 是 n×3，AᵀA 是 3×3。
        # mathutils.Matrix 最多只支持 4 行/列，无法构造 n×3 的 A（n 通常远大于 4），
        # 因此这里直接累加 3×3 的系数矩阵与右端项，不再构造 A/AAᵀ。
        s_00 = s_01 = s_02 = s_11 = s_12 = 0.0
        b_0 = b_1 = b_2 = 0.0
        for i in range(n):
            px = proj_x[i]
            py = proj_y[i]
            rhs_i = px * px + py * py
            s_00 += 4.0 * px * px
            s_01 += 4.0 * px * py
            s_02 += 2.0 * px
            s_11 += 4.0 * py * py
            s_12 += 2.0 * py
            b_0 += 2.0 * px * rhs_i
            b_1 += 2.0 * py * rhs_i
            b_2 += rhs_i
        s_22 = float(n)

        # 圆拟合合理性校验的尺度基准：顶点相对质心的最大距离与骨骼世界长度取大。
        # 少顶点、近重合/近共线的退化点集会让正规方程病态，解出的圆心和半径
        # 可能远离骨骼（实测曾把刚体甩到 45m 外）。
        spread = 0.0
        for v_world in vertices_world:
            dist = (v_world - centroid).length
            if dist > spread:
                spread = dist
        bone_head_world = armature.matrix_world @ bone.head_local
        bone_tail_world = armature.matrix_world @ bone.tail_local
        fit_scale = max(spread, (bone_tail_world - bone_head_world).length, 1e-3)

        try:
            normal_mat = Matrix((
                (s_00, s_01, s_02),
                (s_01, s_11, s_12),
                (s_02, s_12, s_22),
            ))
            normal_rhs = Vector((b_0, b_1, b_2))
            x = normal_mat.inverted() @ normal_rhs
            a_fit = x[0]
            b_fit = x[1]
            c_fit = x[2]
            # proj_x/proj_y 是顶点在 u/v 上的绝对投影，解出的 a_fit/b_fit 已是圆心坐标，
            # 不能在此基础上再叠加质心（否则圆心偏移会被翻倍）。
            # 轴向上的位置无约束，沿用质心在轴向上的投影。
            C_fit = a_fit * u + b_fit * v + centroid.dot(axis_dir) * axis_dir

            # 圆的半径满足 r² = a² + b² + c。圆心离质心过远、
            # 或拟合半径远超点集/骨骼尺度，都说明拟合已发散，回退质心。
            radius_sq = a_fit * a_fit + b_fit * b_fit + c_fit
            center_offset = (C_fit - centroid).length
            if not math.isfinite(radius_sq) or radius_sq < 0.0:
                print(f"[Convert-to-MMD] 圆拟合结果无效，已回退质心（骨骼 '{bone_name}'，顶点数 {n}）")
                C_fit = centroid
            elif center_offset > fit_scale * 2.0 or math.sqrt(radius_sq) > fit_scale * 2.0:
                print(f"[Convert-to-MMD] 圆拟合发散，已回退质心（骨骼 '{bone_name}'，顶点数 {n}，"
                      f"圆心偏移 {center_offset:.3f}m，拟合半径 {math.sqrt(radius_sq):.3f}m，"
                      f"点集尺度 {fit_scale:.3f}m）")
                C_fit = centroid
        except Exception as exc:
            # 退化点集（共线/重合）无法解出圆心时回退质心，但必须显式记录，
            # 避免把求解代码本身的错误也静默吞掉。
            print(f"[Convert-to-MMD] 圆拟合失败，已回退质心（骨骼 '{bone_name}'，顶点数 {n}）：{exc}")
            C_fit = centroid

        # 获取半径（点到轴线的最大垂直距离）
        max_radius = 0.0
        for v_world in vertices_world:
            v_rel = v_world - C_fit
            proj_len = v_rel.dot(axis_dir)
            v_rel_proj = proj_len * axis_dir
            distance = (v_rel - v_rel_proj).length
            if distance > max_radius:
                max_radius = distance

        radius = max_radius

        # 圆柱尺寸（投影范围）
        projections = [v.dot(axis_dir) for v in vertices_world]
        min_proj = min(projections)
        max_proj = max(projections)
        bone_length = max_proj - min_proj

        # 圆柱中心
        center_proj = (min_proj + max_proj) / 2
        C_fit_proj = C_fit.dot(axis_dir)
        delta_proj = center_proj - C_fit_proj
        cylinder_center = C_fit + delta_proj * axis_dir

        rotation_matrix = _build_rotation_matrix(axis_dir)

        x_axis = Vector((1, 0, 0))
        y_axis = Vector((0, 1, 0))
        z_axis = Vector((0, 0, 1))

        angle_x = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(x_axis)))))
        angle_y = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(y_axis)))))
        angle_z = math.degrees(math.acos(max(-1.0, min(1.0, axis_dir.dot(z_axis)))))

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
# 简易身体刚体创建操作符
# ---------------------------------------------------------------------------

class OBJECT_OT_build_simple_body_rigid(bpy.types.Operator):
    """构建简易身体刚体（基于骨骼权重）"""
    bl_idname = "object.build_simple_body_rigid"
    bl_label = "构建简易身体刚体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = bone_utils.resolve_armature(context)
            if not armature:
                self.report({'ERROR'}, "请选择骨架对象")
                return {'CANCELLED'}

            if not MMD_TOOLS_AVAILABLE:
                self.report({'ERROR'}, "mmd_tools 未安装，请先安装 mmd_tools 扩展")
                return {'CANCELLED'}

            convert_result = bpy.ops.object.use_mmd_tools_convert()
            if 'CANCELLED' in convert_result:
                self.report({'ERROR'}, "mmd_tools 转换未完成，已中止身体刚体构建")
                return {'CANCELLED'}

            root = FnModel.find_root_object(armature)
            if not root:
                self.report({'ERROR'}, "未找到 MMD 模型根对象，请先使用 mmd_tools 转换模型")
                return {'CANCELLED'}

            created = self._create_simple_body_rigid_bodies(context, armature, root)
            if not created:
                self.report({'WARNING'}, "未生成任何刚体：顶点权重数据不足或已存在同名刚体")
                return {'CANCELLED'}
            self.report({'INFO'}, f"简易身体刚体系统构建完成（共 {created} 个刚体）")
        except Exception as exc:
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

        return created_count


def register():
    bpy.utils.register_class(OBJECT_OT_build_simple_body_rigid)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_build_simple_body_rigid)


if __name__ == "__main__":
    register()
