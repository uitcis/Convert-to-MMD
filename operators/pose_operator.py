import bpy
import math
from mathutils import Matrix
from .. import bone_utils
from ..bone_utils import apply_armature_transforms
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

        # 前置校验：四根身体参考骨必须已设置且存在，缺任意一根直接取消
        body_fields = (
            ("上半身", "upper_body_bone"),
            ("首", "neck_bone"),
            ("左肩", "left_shoulder_bone"),
            ("右肩", "right_shoulder_bone"),
        )
        missing = []
        body_names = {}
        for label, prop_name in body_fields:
            name = getattr(context.scene, prop_name, "")
            body_names[label] = name
            if not name:
                missing.append(f"{label}（未设置）")
            elif name not in obj.data.bones:
                missing.append(f"{label}（骨骼 '{name}' 不存在）")
        if missing:
            self.report({'ERROR'},
                        "请先设置身体参考骨骼，当前缺少：" + "、".join(missing))
            return {'CANCELLED'}

        # 前置校验：身体参考骨不得重复指向同一根骨
        conflict = bone_utils.check_duplicate_bone_fields(body_names.items())
        if conflict:
            self.report({'ERROR'}, conflict)
            return {'CANCELLED'}

        # 身体参考骨位置不能退化，避免目标方向为零向量
        up_check = (obj.data.bones[body_names["首"]].head_local -
                    obj.data.bones[body_names["上半身"]].head_local)
        left_check = (obj.data.bones[body_names["左肩"]].tail_local -
                      obj.data.bones[body_names["右肩"]].tail_local)
        if up_check.length < 1e-6 or left_check.length < 1e-6:
            self.report({'ERROR'}, "身体参考骨骼位置异常，请检查上半身/首与左肩/右肩的选择")
            return {'CANCELLED'}

        if not apply_armature_transforms(context, obj):
            self.report({'ERROR'}, "应用骨架变换失败")
            return {'CANCELLED'}
        scene = context.scene
        
        # 获取骨骼名称
        arm_bones = {
            "left_upper_arm": getattr(scene, "left_upper_arm_bone", ""),
            "right_upper_arm": getattr(scene, "right_upper_arm_bone", ""),
            "left_lower_arm": getattr(scene, "left_lower_arm_bone", ""),
            "right_lower_arm": getattr(scene, "right_lower_arm_bone", ""),          
        }

        # 检查是否有设置骨骼
        if not any(arm_bones.values()):
            self.report({'ERROR'}, "请先在UI中设置要转换的骨骼")
            return {'CANCELLED'}
        #作用：备份所有网格的形态键，包括基础键
        def backup_shape_keys(mesh_obj):
            backup = {}
            if mesh_obj.data.shape_keys and mesh_obj.data.shape_keys.key_blocks:
                basis = mesh_obj.data.shape_keys.key_blocks[0]
                for key_block in mesh_obj.data.shape_keys.key_blocks[1:]:
                    affected = {}
                    for i, v in enumerate(key_block.data):
                        if v.co != basis.data[i].co:
                            affected[i] = v.co - basis.data[i].co
                    backup[key_block.name] = {
                        'affected': affected,
                        'relative_key': key_block.relative_key.name if key_block.relative_key else None,
                        'slider_min': key_block.slider_min,
                        'slider_max': key_block.slider_max,
                        'mute': key_block.mute,
                        'value': key_block.value
                    }
            if mesh_obj.data.shape_keys:
                keys_to_remove = list(mesh_obj.data.shape_keys.key_blocks)
                for key_block in reversed(keys_to_remove):
                    mesh_obj.shape_key_remove(key_block)
            return backup

        def restore_shape_keys(mesh_obj, backup):
            if not backup:
                return
            context.view_layer.objects.active = mesh_obj
            bpy.ops.object.shape_key_add(from_mix=False)
            new_basis = mesh_obj.data.shape_keys.key_blocks[0]
            for key_name, key_data in backup.items():
                new_key = mesh_obj.shape_key_add(name=key_name)
                for i, delta in key_data['affected'].items():
                    new_key.data[i].co = new_basis.data[i].co + delta
                new_key.slider_min = key_data['slider_min']
                new_key.slider_max = key_data['slider_max']
                new_key.mute = key_data['mute']
                new_key.value = key_data['value']
                if key_data['relative_key'] and key_data['relative_key'] in mesh_obj.data.shape_keys.key_blocks:
                    new_key.relative_key = mesh_obj.data.shape_keys.key_blocks[key_data['relative_key']]

        meshes_with_armature = []
        shape_key_backups = {}
        for mesh_obj in bpy.data.objects:
            if mesh_obj.type == 'MESH':
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj:
                        shape_key_backups[mesh_obj.name] = backup_shape_keys(mesh_obj)
                        meshes_with_armature.append(mesh_obj)
                        break

        if not meshes_with_armature:
            self.report({'WARNING'}, "未找到有上臂权重的网格，跳过网格姿态调整")

        # 切换到编辑模式，将upper_arm的尾部连接到lowerarm的头部
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones
        
        # 获取骨骼位置（先验证骨骼是否存在）
        missing = [f"{k}='{v}'" for k, v in arm_bones.items() if v and v not in edit_bones]
        if missing:
            bpy.ops.object.mode_set(mode='OBJECT')
            self.report({'ERROR'}, f"编辑模式中未找到以下骨骼：{'; '.join(missing)}")
            return {'CANCELLED'}
        
        left_upper_arm = edit_bones[arm_bones["left_upper_arm"]]
        left_lower_arm = edit_bones[arm_bones["left_lower_arm"]]
        right_upper_arm = edit_bones[arm_bones["right_upper_arm"]]
        right_lower_arm = edit_bones[arm_bones["right_lower_arm"]]
        
        # 调整尾部位置
        left_upper_arm.tail = left_lower_arm.head
        right_upper_arm.tail = right_lower_arm.head

        # 5. 为每个网格复制骨骼修改器，但保留原始修改器
        for mesh_obj in meshes_with_armature:
            for modifier in mesh_obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object == obj:
                    # 复制修改器
                    new_modifier = mesh_obj.modifiers.new(name=modifier.name + "_copy", type='ARMATURE')
                    new_modifier.object = modifier.object
                    new_modifier.use_vertex_groups = modifier.use_vertex_groups
                    new_modifier.use_bone_envelopes = modifier.use_bone_envelopes
                    break

        # 6. 切换到姿态模式设置A-Pose
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        pose_bones = obj.pose.bones

        # 7. 仅清除手臂链的既有姿态，保留面部等其它骨骼的姿态
        bpy.ops.pose.select_all(action='DESELECT')
        for arm_bone_name in arm_bones.values():
            if arm_bone_name and arm_bone_name in pose_bones:
                pose_bones[arm_bone_name].select = True
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.select_all(action='DESELECT')
        context.view_layer.update()

        # 8. 构造身体坐标系（前置校验已保证四根参考骨存在且不重复）
        def _build_body_frame():
            """返回 (up, left)，均为世界空间单位向量"""
            data_bones = obj.data.bones
            mw3 = obj.matrix_world.to_3x3()
            up = mw3 @ (data_bones[scene.neck_bone].head_local -
                        data_bones[scene.upper_body_bone].head_local)
            # 肩骨取 tail 端（肩关节），避免锁骨两端都靠近脊柱时轴过短
            left = mw3 @ (data_bones[scene.left_shoulder_bone].tail_local -
                          data_bones[scene.right_shoulder_bone].tail_local)
            up.normalize()
            left = (left - up * left.dot(up)).normalized()
            return up, left

        body_up, body_left = _build_body_frame()
        body_fwd = body_left.cross(body_up).normalized()
        print(f"[A-Pose] 身体坐标系来源：骨骼({scene.upper_body_bone}/"
              f"{scene.neck_bone}/{scene.left_shoulder_bone}/{scene.right_shoulder_bone})")

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
        for bone_type, bone_name in arm_bones.items():
            if "lower_arm" in bone_type:
                continue
            if bone_name and bone_name in pose_bones and bone_name in edit_bones:
                _rotate_bone_to_target(bone_name, bone_type, upper_arm_target)

        if not converted_bones:
            self.report({'WARNING'}, "没有找到匹配的骨骼可以转换")
            return {'CANCELLED'}

        # 9. 更新视图以确保姿态已应用
        context.view_layer.update()

        # 10. 应用第二个修改器（复制的修改器）来调整网格姿态
        try:
            for mesh_obj in meshes_with_armature:
                context.view_layer.objects.active = mesh_obj
                bpy.ops.object.mode_set(mode='OBJECT')
                for modifier in mesh_obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == obj and "_copy" in modifier.name:
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
                        break
                if mesh_obj.name in shape_key_backups:
                    restore_shape_keys(mesh_obj, shape_key_backups[mesh_obj.name])
        except RuntimeError as e:
            self.report({'ERROR'}, f"应用修改器时出错：{str(e)}")
            return {'CANCELLED'}

        # 11. 切换回骨骼对象
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')

        # 12. 应用当前姿态为新的静置姿态
        bpy.ops.pose.armature_apply()

        # 13. 清理临时创建的网格
        for mesh_obj in meshes_with_armature:
            if mesh_obj.get("is_temp_mesh"):
                bpy.data.objects.remove(mesh_obj, do_unlink=True)

        self.report({'INFO'}, f"已完成A-Pose转换并应用为新的静置姿态")
        return {'FINISHED'}