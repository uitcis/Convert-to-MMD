import bpy
import math
from mathutils import Vector
from .. import bone_utils


class OBJECT_OT_complete_missing_bones(bpy.types.Operator):
    """重建 MMD 标准骨骼（补建缺失骨骼并重定位已有标准骨骼）"""
    bl_idname = "object.complete_missing_bones"
    bl_label = "重建标准骨骼"

    def connect_finger_bones(self, edit_bones):
        """连接手指骨骼的头尾"""
        # 定义手指骨骼链
        finger_chains = [
            # 左手手指
            ["左親指０", "左親指１", "左親指２"],
            ["左人指１", "左人指２", "左人指３"],
            ["左中指１", "左中指２", "左中指３"],
            ["左薬指１", "左薬指２", "左薬指３"],
            ["左小指１", "左小指２", "左小指３"],
            # 右手手指
            ["右親指０", "右親指１", "右親指２"],
            ["右人指１", "右人指２", "右人指３"],
            ["右中指１", "右中指２", "右中指３"],
            ["右薬指１", "右薬指２", "右薬指３"],
            ["右小指１", "右小指２", "右小指３"]
        ]
        
        # 连接每个手指骨骼链
        for chain in finger_chains:
            # 检查链中的所有骨骼是否都存在
            if all(bone in edit_bones for bone in chain):
                # 依次连接手指骨骼的头尾
                for i in range(len(chain) - 1):
                    current_bone = edit_bones[chain[i]]
                    next_bone = edit_bones[chain[i + 1]]
                    # 将当前骨骼的尾部设置为下一个骨骼的头部
                    current_bone.tail = next_bone.head

    def execute(self, context):
        """执行补全缺失骨骼操作

        Returns:
            dict: Blender operator 返回状态
        """
        obj = bone_utils.resolve_armature(context)
        if not obj:
            self.report({'ERROR'}, "没有选择骨架")
            return {'CANCELLED'}

        # 确保当前处于编辑模式 (EDIT mode)
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = obj.data.edit_bones

        # === 输入验证阶段 ===
        # 验证必需的骨骼存在
        required_bones = ["首", "頭", "左肩", "左腕", "左ひじ", "左足首",
                          "右肩", "右腕", "右ひじ", "右足首"]
        missing_bones = [name for name in required_bones if name not in edit_bones]
        if missing_bones:
            self.report({'ERROR'}, f"缺失必需骨骼: {', '.join(missing_bones)}")
            return {'CANCELLED'}

        # 获取需要修改的骨骼
        left_foot_bone = edit_bones.get("左足")
        right_foot_bone = edit_bones.get("右足")
        upper_body_bone = edit_bones.get("上半身")
        lower_body_bone = edit_bones.get("下半身")

        # === 校验阶段（必须在改动父级/位置之前完成，取消时不留下半改状态）===
        if not upper_body_bone:
            self.report({'ERROR'}, "上半身骨骼不存在")
            return {'CANCELLED'}

        # 获取 上半身 骨骼的坐标
        upper_body_head = upper_body_bone.head.copy()
        upper_body_tail = upper_body_bone.tail.copy()

        # 计算骨架高度和bone_length
        bone_length = bone_utils.calculate_bone_length(edit_bones)

        # 验证 bone_length 有效性
        if bone_length <= 0 or bone_length > 10:  # 10m 为合理上限
            self.report({'ERROR'}, f"计算出的骨骼长度无效: {bone_length:.3f}")
            return {'CANCELLED'}

        # === 校验通过，构造标准骨骼属性（此阶段尚未改动任何数据）===
        # 重要：下面用局部快照替代 edit_bones[...].head/tail 的直接引用。
        # edit_bones 的 Vector 是实时视图；而后面创建备份时会切到 OBJECT 再重进
        # EDIT（第 277/295 行），edit_bones 随之重建，旧引用会失效并变成 NaN/0。
        # 若把引用直接存进 bone_properties，写回时就会把骨骼 head/tail 改到
        # 原点或 1e14 级错误位置。这里先把所有需要的坐标 copy 成独立快照。
        _head = {name: eb.head.copy() for name, eb in edit_bones.items()}
        _tail = {name: eb.tail.copy() for name, eb in edit_bones.items()}

        # === 膝盖预弯：保证髋-膝-踝夹角至少 179.5°（即弯曲不少于 0.5°）===
        # MMD 的腿 IK 靠单侧角度限制定弯向；Blender 侧没有 pole target，
        # rest 姿态完全共线时 solver 缺少明确的弯曲提示。这里检查实际夹角，
        # 对共线/弯曲不足的膝盖，沿角色前方（本坐标系 -Y）平移 head，
        # 直到夹角恰好 180° - 0.5°。原本已有足够弯曲的保持不动。
        KNEE_BEND_DEG = 0.5
        _target_angle = 180.0 - KNEE_BEND_DEG
        _knee_bend_heads = {}
        for _side in ("左", "右"):
            _hip = _head.get(f"{_side}足")
            _knee = _head.get(f"{_side}ひざ")
            _ankle = _head.get(f"{_side}足首")
            if _hip is None or _knee is None or _ankle is None:
                continue
            _upper = (_knee - _hip).length
            _lower = (_ankle - _knee).length
            if _upper < 1e-6 or _lower < 1e-6:
                continue

            def _angle_at(_d):
                _k = _knee.copy()
                _k.y -= _d
                _a = _hip - _k
                _b = _ankle - _k
                _denom = _a.length * _b.length
                if _denom < 1e-12:
                    return 0.0
                _cos = max(-1.0, min(1.0, _a.dot(_b) / _denom))
                return math.degrees(math.acos(_cos))

            _cur = _angle_at(0.0)
            if _cur <= _target_angle + 1e-4:
                print(f"[Convert-to-MMD] {_side}膝已有弯曲 {180.0 - _cur:.2f}° ≥ {KNEE_BEND_DEG:.1f}°，保持原样")
                continue
            _lo, _hi = 0.0, min(_upper, _lower) * 0.5
            for _ in range(40):
                _mid = (_lo + _hi) * 0.5
                if _angle_at(_mid) > _target_angle:
                    _lo = _mid
                else:
                    _hi = _mid
            _d = (_lo + _hi) * 0.5
            _new_knee = _knee.copy()
            _new_knee.y -= _d
            _knee_bend_heads[f"{_side}ひざ"] = _new_knee
            print(f"[Convert-to-MMD] {_side}膝预弯: 夹角 {_cur:.3f}° -> {_angle_at(_d):.3f}°, "
                  f"head.y {_knee.y:.4f} -> {_new_knee.y:.4f} (前移 {_d*1000:.2f}mm)")

        # 先检测上半身链骨骼（上半身2, 上半身3, ...）
        upper_chain_bones = []
        for i in range(2, 6):
            name = f"上半身{i}"
            if edit_bones.get(name):
                upper_chain_bones.append(name)

        last_upper_body = upper_chain_bones[-1] if upper_chain_bones else "上半身"

        # 定义基本骨骼的属性（带输入验证）
        try:
            bone_properties = {

            "全ての親": {"head": Vector((0, 0, 0)), "tail": Vector((0, 0, bone_length)), "parent": None, "use_deform": False, "use_connect": False},
            "センター": {"head": Vector((0, 0, bone_length * 2)), "tail": Vector((0, 0, bone_length*1.1)), "parent": "全ての親", "use_deform": False, "use_connect": False},
            "グルーブ": {"head": Vector((0, 0, bone_length * 3.2)), "tail": Vector((0, 0, bone_length * 4)), "parent": "センター", "use_deform": False, "use_connect": False},
            "腰": {"head": Vector((0, upper_body_head.y + bone_length * 0.5, upper_body_head.z - bone_length * 0.5)), "tail": Vector((0, upper_body_head.y, upper_body_head.z)), 
                "parent": "グルーブ", "use_deform": False, "use_connect": False},
            "上半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)),
                "tail": Vector((0, upper_body_tail.y, upper_body_head.z+bone_length)), 
                "parent": "腰", "use_connect": False},
            "首": {
                "head": _head["首"],
                "tail": _head["頭"],
                "parent": last_upper_body,
                "use_connect": False
            },
            "頭": {
                "head": _head["頭"],
                "tail": Vector((0, _head["頭"].y, _head["頭"].z+bone_length * 0.25)),
                "parent": "首",
                "use_connect": False
            },                                  
            # 上肢骨骼链
            "左肩": {
                "head": _head["左肩"],
                "tail": _head["左腕"],
                "parent": last_upper_body,
                "use_connect": False
            },
            "左腕": {
                "head": _head["左腕"],
                "tail": _head["左ひじ"],
                "parent": "左肩",
                "use_connect": True
            },
            "左ひじ": {
                "head": _head["左ひじ"],
                "tail": _head["左手首"] if "左手首" in edit_bones else _tail["左ひじ"],
                "parent": "左腕",
                "use_connect": True
            },
        
            "右肩": {
                "head": _head["右肩"],
                "tail": _head["右腕"],
                "parent": last_upper_body,
                "use_connect": False
            },
            "右腕": {
                "head": _head["右腕"],
                "tail": _head["右ひじ"],
                "parent": "右肩",
                "use_connect": True
            },
            "右ひじ": {
                "head": _head["右ひじ"],
                "tail": _head["右手首"] if "右手首" in edit_bones else _tail["右ひじ"],
                "parent": "右腕",
                "use_connect": True
            }, 
            
            "下半身": {"head": Vector((0, upper_body_head.y, upper_body_head.z)), "tail": Vector((0, upper_body_head.y, upper_body_head.z - bone_length)), "parent": "腰", "use_connect": False},
            "左足": {
                "head": _head["左足"],
                "tail": _knee_bend_heads.get("左ひざ", _head["左ひざ"]),
                "parent": "下半身",
                "use_connect": False
            },
            "右足": {
                "head": _head["右足"],
                "tail": _knee_bend_heads.get("右ひざ", _head["右ひざ"]),
                "parent": "下半身",
                "use_connect": False
            },
            "左ひざ": {
                "head": _knee_bend_heads.get("左ひざ", _head["左ひざ"]),
                "tail": _head["左足首"],
                "parent": "左足",
                "use_connect": False
            },
            "右ひざ": {
                "head": _knee_bend_heads.get("右ひざ", _head["右ひざ"]),
                "tail": _head["右足首"],
                "parent": "右足",
                "use_connect": False
            },
            "左足首": {
                "head": _head["左足首"],
                "tail": Vector((_head["左足首"].x, _head["左足首"].y - bone_length*0.3, 0)),
                "parent": "左ひざ",
                "use_connect": False
            },
            "右足首": {
                "head": _head["右足首"],
                "tail": Vector((_head["右足首"].x, _head["右足首"].y - bone_length*0.3, 0)),
                "parent": "右ひざ",
                "use_connect": False
            },
            "左足先EX": {
                "head": _tail["左足首"],
                "tail": Vector((_tail["左足首"].x, _tail["左足首"].y - bone_length*0.5, 0)),
                "parent": "左足首",
                "use_connect": False
            },
            "右足先EX": {
                "head": _tail["右足首"],
                "tail": Vector((_tail["右足首"].x, _tail["右足首"].y - bone_length*0.5, 0)),
                "parent": "右足首",
                "use_connect": False
            }
        }  # bone_properties 结束
        except KeyError as e:
            self.report({'ERROR'}, f"骨骼属性构建失败，缺少必需骨骼: {e}")
            print(f"[Convert-to-MMD] 骨骼属性构建错误: {e}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"骨骼属性构建失败: {e}")
            print(f"[Convert-to-MMD] 骨骼属性构建异常: {e}")
            return {'CANCELLED'}

        if upper_chain_bones:
            for idx, bone_name in enumerate(upper_chain_bones):
                next_bone_name = upper_chain_bones[idx + 1] if idx + 1 < len(upper_chain_bones) else None

                if next_bone_name:
                    # 非最后一节：尾部指向下一节骨骼的头部
                    bone_properties[bone_name] = {
                        "head": Vector((0, _head[bone_name].y, _head[bone_name].z)),
                        "tail": Vector((0, _head[next_bone_name].y, _head[next_bone_name].z)),
                        "parent": upper_chain_bones[idx - 1] if idx > 0 else "上半身",
                        "use_connect": False
                    }
                else:
                    # 最后一节：尾部指向首骨骼头部
                    bone_properties[bone_name] = {
                        "head": Vector((0, _head[bone_name].y, _head[bone_name].z)),
                        "tail": Vector((0, _head["首"].y, _head["首"].z)),
                        "parent": upper_chain_bones[idx - 1] if idx > 0 else "上半身",
                        "use_connect": False
                    }

        # === 变更预览：列出将被移动/重挂的已有骨骼 ===
        move_lines = []
        new_bone_names = []
        for bone_name, properties in bone_properties.items():
            existing = edit_bones.get(bone_name)
            if existing is None:
                new_bone_names.append(bone_name)
                continue
            planned_head = (existing.head.copy() if bone_name in ("左足先EX", "右足先EX")
                            else properties["head"])
            head_move = (existing.head - planned_head).length
            tail_move = (existing.tail - properties["tail"]).length
            parent_now = existing.parent.name if existing.parent else None
            parent_new = properties.get("parent")
            connect_now = existing.use_connect
            connect_new = properties.get("use_connect", False)
            if (head_move > 1e-4 or tail_move > 1e-4
                    or parent_now != parent_new or connect_now != connect_new):
                move_lines.append(
                    f"{bone_name}: 头 {head_move:.3f}m、尾 {tail_move:.3f}m、"
                    f"父级 {parent_now or '无'}→{parent_new or '无'}"
                    + ("、连接状态变化" if connect_now != connect_new else ""))

        if move_lines:
            self.report({'WARNING'},
                        f"将移动/重挂 {len(move_lines)} 根已有骨骼，明细如下")
            for i in range(0, len(move_lines), 4):
                self.report({'INFO'}, "；".join(move_lines[i:i + 4]))
            for line in move_lines:
                print(f"[重建标准骨骼] {line}")
        if new_bone_names:
            self.report({'INFO'},
                        f"将新建 {len(new_bone_names)} 根骨骼: {', '.join(new_bone_names)}")

        # === 创建骨架备份（与重命名保持一致，先建新备份再替换旧的）===
        bpy.ops.object.mode_set(mode='OBJECT')
        backup_data = obj.data.copy()
        backup_data.name = f"{obj.data.name}_backup_tmp"
        backup_obj = bpy.data.objects.new(f"{obj.name}_backup_tmp", backup_data)
        bpy.context.collection.objects.link(backup_obj)
        backup_obj.matrix_world = obj.matrix_world
        backup_obj.hide_viewport = True
        backup_obj.hide_render = True

        old_backup_name = f"{obj.name}_backup"
        if old_backup_name in bpy.data.objects:
            try:
                bpy.data.objects.remove(bpy.data.objects[old_backup_name], do_unlink=True)
            except Exception as e:
                print(f"[重建标准骨骼] 删除旧备份失败: {e}")
        backup_obj.name = f"{obj.name}_backup"
        backup_data.name = f"{obj.data.name}_backup"
        self.report({'INFO'}, f"已创建骨架备份: {backup_obj.name}")
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = obj.data.edit_bones

        # === 开始修改父子关系 ===
        left_foot_bone = edit_bones.get("左足")
        right_foot_bone = edit_bones.get("右足")
        upper_body_bone = edit_bones.get("上半身")
        lower_body_bone = edit_bones.get("下半身")
        if left_foot_bone:
            left_foot_bone.use_connect = False
            left_foot_bone.parent = None
        if right_foot_bone:
            right_foot_bone.use_connect = False
            right_foot_bone.parent = None
        if upper_body_bone and upper_body_bone.parent:
            upper_body_bone.use_connect = False
            upper_body_bone.parent = None
        if lower_body_bone and lower_body_bone.parent:
            lower_body_bone.use_connect = False
            lower_body_bone.parent = None

        # 按顺序检查并创建或更新骨骼
        for bone_name, properties in bone_properties.items():
            # 如果是足先EX且已经存在，保持其头位置不变
            if bone_name in ["左足先EX", "右足先EX"] and bone_name in edit_bones:
                # 保持原有的头位置，只更新尾部和其他属性
                original_head = edit_bones[bone_name].head.copy()
                bone_utils.create_or_update_bone(edit_bones, bone_name, original_head, properties["tail"], properties.get("use_connect", False), properties["parent"], properties.get("use_deform", True))
            else:
                # 正常创建或更新骨骼
                bone_utils.create_or_update_bone(edit_bones, bone_name, properties["head"], properties["tail"], properties.get("use_connect", False), properties["parent"], properties.get("use_deform", True))
        
        # 如果存在足先EX骨骼，将足首的尾部指向足先EX的头部
        if "左足先EX" in edit_bones:
            # 更新左足首的尾部到左足先EX的头部
            edit_bones["左足首"].tail = edit_bones["左足先EX"].head
        if "右足先EX" in edit_bones:
            # 更新右足首的尾部到右足先EX的头部
            edit_bones["右足首"].tail = edit_bones["右足先EX"].head


        # 连接手指骨骼的头尾
        self.connect_finger_bones(edit_bones)

        # 调用新规则设置骨骼扭转（几何/按名，复刻 Shift+N 全局 ±Z/±Y）
        # 放在连接手指之后，使手指 roll 基于连接后的真实头尾方向计算
        bone_utils.calculate_auto_bone_roll(edit_bones, armature_obj=obj)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_complete_missing_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_complete_missing_bones)


if __name__ == "__main__":
    register()
