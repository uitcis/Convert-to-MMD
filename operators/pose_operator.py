import bpy
import math
from mathutils import Matrix
from .. import bone_utils
from ..bone_utils import apply_armature_transforms
from ..tools import apose_validate
# 新增的T-Pose到A-Pose转换操作符
class OBJECT_OT_convert_to_apose(bpy.types.Operator):
    """将骨架转换为 A-Pose 并应用为新的静置姿态"""
    bl_idname = "object.convert_to_apose" 
    bl_label = "Convert to A-Pose"

    def execute(self, context):
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'} 

        scene = context.scene

        # 前置校验（必须在任何副作用之前）：6 个身体参考字段是否都指向
        # 存在的骨骼。原先只校验上半身/首，手臂字段等到进编辑模式后才用
        # 下标直接取，某项为空就抛 KeyError，用户只看到一句
        # 「转换 A-Pose 时出错：'bpy_prop_collection[key]: key "" not found'」。
        # 现在一次性列出所有不可用项（含侧别、部位、状态），再给输入要求。
        issues = apose_validate.collect_issues(
            lambda field: getattr(scene, field, ""), set(obj.data.bones.keys()))
        if issues:
            for line in apose_validate.build_detail_lines(issues):
                print(line)
            self.report({'ERROR'}, apose_validate.build_message(issues))
            return {'CANCELLED'}

        body_names = {
            "上半身": getattr(scene, "upper_body_bone", ""),
            "首": getattr(scene, "neck_bone", ""),
        }

        # 注：字段重复指向（如左右上臂选到同一根骨）已由上面的
        # collect_issues 统一检查并列出，这里不再重复校验。

        # 构造身体坐标系（此时尚未产生任何副作用）
        def _build_body_frame():
            """返回 (up, left, 左右轴来源, 失败原因)。

            up 由上半身→首的 head 连线得出；左右轴只用左/右上臂骨的 head 差值。
            left 为 None 表示左右轴无法确定。
            """
            data_bones = obj.data.bones
            mw3 = obj.matrix_world.to_3x3()
            up_raw = (data_bones[body_names["首"]].head_local -
                      data_bones[body_names["上半身"]].head_local)
            if up_raw.length < 1e-6:
                return up_raw, None, None, "上半身与首位置重合"
            up = (mw3 @ up_raw).normalized()

            la = getattr(scene, "left_upper_arm_bone", "")
            ra = getattr(scene, "right_upper_arm_bone", "")
            if la and ra and la in data_bones and ra in data_bones:
                left = mw3 @ (data_bones[la].head_local -
                              data_bones[ra].head_local)
                left = left - up * left.dot(up)
                if left.length > 1e-6:
                    return up, left.normalized(), f"上臂骨 head({la}/{ra})", None
                reason = (f"左腕('{la}') 与右腕('{ra}') 的 head 位置重合，"
                          f"或两点连线与身体上下轴平行")
            else:
                # 前置校验已保证左右上臂可用，走到这里说明骨架在校验后
                # 被改动过；仍按侧别指出具体哪一项失效。
                bad = []
                if not la:
                    bad.append("左腕（未设置）")
                elif la not in data_bones:
                    bad.append(f"左腕（骨骼 '{la}' 不存在）")
                if not ra:
                    bad.append("右腕（未设置）")
                elif ra not in data_bones:
                    bad.append(f"右腕（骨骼 '{ra}' 不存在）")
                reason = "、".join(bad) if bad else "左右上臂骨不可用"
            return up, None, None, reason

        body_up, body_left, left_source, frame_error = _build_body_frame()
        if body_up.length < 1e-6:
            self.report({'ERROR'},
                        f"无法确定身体上下方向：上半身('{body_names['上半身']}') 与 "
                        f"首('{body_names['首']}') 的 head 位置重合或过于接近，"
                        f"请确认这两个字段指向的是不同的躯干骨骼")
            return {'CANCELLED'}
        if body_left is None:
            self.report({'ERROR'},
                        "无法确定身体左右轴：" + frame_error +
                        "。左右轴由左腕与右腕的 head 差值确定，"
                        "请确认左右上臂骨分别指向身体两侧的骨骼")
            return {'CANCELLED'}

        if not apply_armature_transforms(context, obj):
            self.report({'ERROR'}, "应用骨架变换失败")
            return {'CANCELLED'}
        
        # 获取骨骼名称（前置校验已确认四项都存在）
        arm_bones = {
            "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
            "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
            "left_lower_arm": getattr(scene, "left_lower_arm_bone", ""),
            "right_lower_arm": getattr(scene, "right_lower_arm_bone", ""),          
        }

        # 烘顶点时只临时改动形态键 value 与非 Armature 修改器的显示开关，
        # 不再复制/应用修改器，也不再删除重建形态键。
        saved_sk_values = {}     # 网格名 -> {形态键名: value}
        saved_mod_flags = {}     # 网格名 -> {修改器名: show_viewport}
        baked_coords = {}        # 网格名 -> [局部坐标, ...]

        def _restore_bake_states():
            """恢复烘顶点前临时关闭的形态键 value / 修改器开关（幂等）。"""
            for mesh_name, values in saved_sk_values.items():
                mesh_obj = bpy.data.objects.get(mesh_name)
                if mesh_obj is None or mesh_obj.type != 'MESH':
                    continue
                sk = mesh_obj.data.shape_keys
                if sk:
                    for kb in sk.key_blocks:
                        if kb.name in values:
                            kb.value = values[kb.name]
            for mesh_name, flags in saved_mod_flags.items():
                mesh_obj = bpy.data.objects.get(mesh_name)
                if mesh_obj is None:
                    continue
                for mod in mesh_obj.modifiers:
                    if mod.name in flags:
                        mod.show_viewport = flags[mod.name]

        def _bake_pose_into_vertices():
            """把当前姿态经 Armature 修改器算出的顶点写回 Basis / mesh 顶点。

            形态键 value 先归零，避免表情形变混进 Basis；非 Armature 修改器
            临时关闭，避免把细分/镜像等效果一起烘进去。修改器栈与形态键本体
            全程保留。
            """
            for mesh_obj in meshes_with_armature:
                sk = mesh_obj.data.shape_keys
                values = {}
                if sk:
                    # Basis（索引 0）不参与形变，归零它在 Blender 4.5 上无法恢复
                    for kb in sk.key_blocks[1:]:
                        values[kb.name] = kb.value
                        kb.value = 0.0
                saved_sk_values[mesh_obj.name] = values

                flags = {}
                for mod in mesh_obj.modifiers:
                    if mod.type != 'ARMATURE':
                        flags[mod.name] = mod.show_viewport
                        mod.show_viewport = False
                saved_mod_flags[mesh_obj.name] = flags

            # 关掉形态键/修改器后必须刷新依赖图，否则读到的还是旧顶点
            context.view_layer.update()
            dg = context.evaluated_depsgraph_get()
            for mesh_obj in meshes_with_armature:
                ev = mesh_obj.evaluated_get(dg)
                em = ev.to_mesh()   # 返回对象局部坐标，无需矩阵换算
                try:
                    baked_coords[mesh_obj.name] = [tuple(v.co) for v in em.vertices]
                finally:
                    ev.to_mesh_clear()

            _restore_bake_states()

            for mesh_obj in meshes_with_armature:
                coords = baked_coords.get(mesh_obj.name)
                if not coords:
                    continue
                sk = mesh_obj.data.shape_keys
                if sk:
                    basis = sk.key_blocks[0]
                    for i, co in enumerate(coords):
                        basis.data[i].co = co
                else:
                    for i, co in enumerate(coords):
                        mesh_obj.data.vertices[i].co = co
                mesh_obj.data.update()

        meshes_with_armature = []
        saved_basis = {}
        finished = False
        original_mode = context.mode
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)

        try:
            for mesh_obj in bpy.data.objects:
                if mesh_obj.type == 'MESH':
                    for modifier in mesh_obj.modifiers:
                        if modifier.type == 'ARMATURE' and modifier.object == obj:
                            meshes_with_armature.append(mesh_obj)
                            break

            if not meshes_with_armature:
                self.report({'WARNING'},
                            "未找到绑定到该骨架的网格，将只调整骨骼、不烘顶点"
                            "（可先确认网格上有指向本骨架的 Armature 修改器）")

            # 切换到编辑模式，将upper_arm的尾部连接到lowerarm的头部
            bpy.ops.object.mode_set(mode='EDIT')
            edit_bones = obj.data.edit_bones

            # 防御性复查（前置校验已确认存在；此处防骨架在两步之间被改动）。
            # 标签用面板骨骼名，不用内部字段名，便于用户直接对照。
            label_of = {field: label for field, label, _s, _p, _r
                        in apose_validate.APOSE_FIELDS}
            prop_of_key = {
                "left_upper_arm": "left_upper_arm_bone",
                "right_upper_arm": "right_upper_arm_bone",
                "left_lower_arm": "left_lower_arm_bone",
                "right_lower_arm": "right_lower_arm_bone",
            }
            missing = []
            for key, name in arm_bones.items():
                if not name:
                    missing.append(f"{label_of[prop_of_key[key]]}（未设置）")
                elif name not in edit_bones:
                    missing.append(
                        f"{label_of[prop_of_key[key]]}（骨骼 '{name}' 不存在）")
            if missing:
                bpy.ops.object.mode_set(mode='OBJECT')
                self.report({'ERROR'},
                            "手臂骨骼在编辑模式中不可用：" + "、".join(missing) +
                            "。" + apose_validate.REQUIREMENT_TEXT)
                return {'CANCELLED'}

            left_upper_arm = edit_bones[arm_bones["left_upper_arm"]]
            left_lower_arm = edit_bones[arm_bones["left_lower_arm"]]
            right_upper_arm = edit_bones[arm_bones["right_upper_arm"]]
            right_lower_arm = edit_bones[arm_bones["right_lower_arm"]]

            # 调整尾部位置
            left_upper_arm.tail = left_lower_arm.head
            right_upper_arm.tail = right_lower_arm.head

            # 5. 切换到姿态模式设置A-Pose
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='POSE')

            pose_bones = obj.pose.bones

            # 6. 仅清除手臂链的既有姿态，保留面部等其它骨骼的姿态。
            #    直接重置 matrix_basis，不依赖 PoseBone.select：
            #    4.5 用 Bone.select、5.x 用 PoseBone.select，跨版本行为不一致。
            for arm_bone_name in arm_bones.values():
                if arm_bone_name and arm_bone_name in pose_bones:
                    pose_bones[arm_bone_name].matrix_basis = Matrix.Identity(4)
            context.view_layer.update()

            # 7. 构造身体坐标系（校验阶段已确认可用，此处按变换后的矩阵重算）
            body_up, body_left, left_source, _ = _build_body_frame()
            body_fwd = body_left.cross(body_up).normalized()
            print(f"[A-Pose] 身体坐标系来源：上半身({body_names['上半身']})/首({body_names['首']})，"
                  f"左右轴取自{left_source}")

            edit_bones = obj.data.bones
            converted_bones = []

            # 上臂目标仰角（向下为负）
            upper_arm_target = 36

            def _elevation(vec):
                """方向向量相对世界水平面的仰角（度），向上为正"""
                return math.degrees(math.atan2(vec.z, math.hypot(vec.x, vec.y)))

            def _body_elevation(vec):
                """方向在身体坐标系中的仰角（度），沿 up 为正"""
                return math.degrees(math.asin(max(-1.0, min(1.0, vec.dot(body_up)))))

            def _azimuth_deviation(vec, expect_lat):
                """水平分量相对身体左右轴的偏差（度），正值偏身体前方"""
                lateral = vec.dot(expect_lat)
                forward = vec.dot(body_fwd)
                return math.degrees(math.atan2(forward, lateral))

            def _rotate_bone_to_target(bone_name, bone_type, target_angle):
                """按身体坐标系把上臂转到目标仰角（绕肩关节，与骨骼roll无关）"""
                bone = pose_bones[bone_name]
                bone.rotation_mode = 'XYZ'
                mw = obj.matrix_world.copy()
                head_w = mw @ bone.head
                tail_w = mw @ bone.tail
                current_dir = (tail_w - head_w).normalized()

                # 左右归属按身体坐标系判定，不再依赖世界 X 符号
                lateral = current_dir.dot(body_left)
                if abs(lateral) > 1e-4:
                    side = 1.0 if lateral > 0 else -1.0
                else:
                    side = 1.0 if "left" in bone_type else -1.0

                rad = math.radians(target_angle)
                target_dir = (body_left * (side * math.cos(rad))
                              - body_up * math.sin(rad)).normalized()
                quat = current_dir.rotation_difference(target_dir)

                # 绕肩关节（骨头）在世界空间旋转，再换算回姿态空间
                pivot = (Matrix.Translation(head_w) @ quat.to_matrix().to_4x4()
                         @ Matrix.Translation(-head_w))
                bone.matrix = mw.inverted() @ pivot @ mw @ bone.matrix
                context.view_layer.update()

                new_dir = ((mw @ bone.tail) - (mw @ bone.head)).normalized()
                expect_lat = body_left * side
                print(f"[A-Pose] {bone_name}: 世界仰角 {_elevation(current_dir):.2f}° -> "
                      f"{_elevation(new_dir):.2f}° | 身体仰角 {_body_elevation(current_dir):.2f}° -> "
                      f"{_body_elevation(new_dir):.2f}° | "
                      f"方位偏差 {_azimuth_deviation(new_dir, expect_lat):+.2f}° | "
                      f"前后偏移 {new_dir.dot(body_fwd):+.3f}")
                converted_bones.append(bone_name)

            # 处理上臂
            skipped_sides = []
            for bone_type, bone_name in arm_bones.items():
                if "lower_arm" in bone_type:
                    continue
                if bone_name and bone_name in pose_bones and bone_name in edit_bones:
                    _rotate_bone_to_target(bone_name, bone_type, upper_arm_target)
                else:
                    side_label = "左腕" if "left" in bone_type else "右腕"
                    if not bone_name:
                        skipped_sides.append(f"{side_label}（未设置）")
                    else:
                        skipped_sides.append(
                            f"{side_label}（骨骼 '{bone_name}' 在姿态模式下不可用）")

            if not converted_bones:
                self.report({'WARNING'},
                            "没有可旋转的上臂骨骼：" + "、".join(skipped_sides) +
                            "。" + apose_validate.REQUIREMENT_TEXT)
                return {'CANCELLED'}
            if skipped_sides:
                self.report({'WARNING'},
                            "仅部分上臂完成转换，以下未处理：" +
                            "、".join(skipped_sides))

            # 8. 记录手臂链以外骨骼的局部姿态：后续只把手臂链烘进静置，
            #    避免把面部等其它骨骼的既有姿态一并写进静置姿态。
            arm_pose_names = {name for name in arm_bones.values() if name}
            saved_basis = {
                pb.name: pb.matrix_basis.copy()
                for pb in pose_bones if pb.name not in arm_pose_names
            }
            for pb_name in saved_basis:
                pose_bones[pb_name].matrix_basis = Matrix.Identity(4)
            context.view_layer.update()

            # 9. 把当前姿态烘进网格顶点（形态键 value / 修改器开关自动恢复）
            if meshes_with_armature:
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='OBJECT')
                _bake_pose_into_vertices()

            # 10. 切换回骨骼对象
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='POSE')

            # 11. 应用当前姿态为新的静置姿态（此时其它骨骼姿态已归零，只会烘入手臂链）
            bpy.ops.pose.armature_apply()

            # 12. 恢复手臂链以外骨骼的姿态
            for pb_name, basis in saved_basis.items():
                pb = pose_bones.get(pb_name)
                if pb is not None:
                    pb.matrix_basis = basis
            context.view_layer.update()

            finished = True
            self.report({'INFO'}, "已完成A-Pose转换并应用为新的静置姿态")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"转换 A-Pose 时出错：{str(e)}")
            return {'CANCELLED'}
        finally:
            # 无论成功、取消还是异常，都恢复临时关闭的形态键 value 与修改器开关
            try:
                _restore_bake_states()
            except (ReferenceError, RuntimeError) as e:
                print(f"[A-Pose] 恢复烘顶点状态失败: {e}")
            if not finished:
                for pb_name, basis in saved_basis.items():
                    try:
                        pb = obj.pose.bones.get(pb_name) if obj else None
                        if pb is not None:
                            pb.matrix_basis = basis
                    except (ReferenceError, RuntimeError):
                        pass
                try:
                    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                        bpy.ops.object.mode_set(mode='OBJECT')
                    if obj and obj.name in bpy.data.objects:
                        if context.mode != original_mode:
                            bpy.ops.object.mode_set(mode=restore_mode)
                        context.view_layer.objects.active = obj
                except (ReferenceError, RuntimeError) as e:
                    print(f"[A-Pose] 取消后恢复状态失败: {e}")
