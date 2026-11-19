from mathutils import Vector
import bpy

def context_mode_to_mode_set(context_mode):
    """将 context.mode 的枚举值转换为 bpy.ops.object.mode_set 接受的模式。

    context.mode 返回 'EDIT_ARMATURE' 等带对象类型后缀的上下文模式，
    而 mode_set 只接受 'OBJECT' / 'EDIT' / 'POSE'，直接传回会触发
    TypeError: enum "EDIT_ARMATURE" not found in ('OBJECT', 'EDIT', 'POSE')。

    Args:
        context_mode: context.mode 的值

    Returns:
        str: 'OBJECT' / 'EDIT' / 'POSE' 之一
    """
    if context_mode in ('OBJECT', 'POSE'):
        return context_mode
    if context_mode.startswith('EDIT'):
        return 'EDIT'
    # WEIGHT_PAINT 等无法用 mode_set 恢复的模式，退回 OBJECT
    return 'OBJECT'

def resolve_armature(context, ensure_active=True):
    """解析当前上下文指向的骨架对象。

    活动对象是骨架时直接返回；活动对象是网格时，沿 ARMATURE 修改器回溯
    其绑定的骨架（与面板显示逻辑一致）。

    ensure_active=True 时会把找到的骨架设为活动对象，以保证后续
    bpy.ops（模式切换、变换、选择等）作用在骨架上；面板绘制等只读场景
    应传 False，避免仅打开面板就改变用户的活动对象。

    Returns:
        bpy.types.Object | None: 骨架对象；无法解析时返回 None
    """
    obj = context.active_object
    if obj and obj.type == 'ARMATURE':
        return obj

    armature = None
    if obj and obj.type == 'MESH':
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object:
                try:
                    if mod.object.type == 'ARMATURE' and mod.object.name in bpy.data.objects:
                        armature = mod.object
                        break
                except (ReferenceError, RuntimeError):
                    continue

    if armature and ensure_active and context.active_object is not armature:
        try:
            armature.select_set(True)
            context.view_layer.objects.active = armature
        except (ReferenceError, RuntimeError):
            return None

    return armature


def check_duplicate_bone_fields(fields):
    """检查骨骼字段是否重复指向同一根骨骼。

    Args:
        fields: 可迭代的 (显示名, 骨骼名) 对；骨骼名为空时忽略

    Returns:
        str | None: 冲突提示文本；没有重复时返回 None
    """
    seen = {}
    for label, name in fields:
        if not name:
            continue
        if name in seen:
            return f"{seen[name]}与{label}指向同一根骨骼 '{name}'，请先修正选择"
        seen[name] = label
    return None


def create_or_update_bone(edit_bones, name, head_position, tail_position, use_connect=False, parent_name=None, use_deform=True):
    bone = edit_bones.get(name)
    if bone:
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = use_connect
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform
    else:
        bone = edit_bones.new(name)
        bone.head = head_position
        bone.tail = tail_position
        bone.use_connect = use_connect
        bone.parent = edit_bones.get(parent_name) if parent_name else None
        bone.use_deform = use_deform
    return bone



def apply_armature_transforms(context, armature_obj=None):
    """自动应用骨架和网格对象的变换"""
    try:
        # 确保在对象模式
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 获取骨架对象
        armature = armature_obj or resolve_armature(context, ensure_active=False)
        if not armature or armature.type != 'ARMATURE':
            print("未找到骨架对象")
            return False

        # 选择骨架层级并应用变换
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.select_hierarchy(direction='CHILD', extend=True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        
        # 选择回骨架
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        
        return True

    except Exception as e:
        print(f"应用变换时出错: {str(e)}")
        return False


def calculate_skeleton_height(edit_bones):
    """计算骨架高度
    
    Args:
        edit_bones: 编辑模式下的骨骼集合
        
    Returns:
        float: 骨架高度
    """
    min_z = float('inf')
    max_z = -float('inf')
    for bone in edit_bones:
        min_z = min(min_z, bone.head.z, bone.tail.z)
        max_z = max(max_z, bone.head.z, bone.tail.z)
    return max_z - min_z


def calculate_bone_length(edit_bones):
    """计算骨架高度并返回八分之一骨架高度作为bone_length"""
    # 获取骨架高度
    skeleton_height = calculate_skeleton_height(edit_bones)
    # 定义八分之一骨架高度
    bone_length = skeleton_height * 0.125
    return bone_length


def check_and_scale_skeleton(obj):
    """检测骨架高度并自动缩放
    
    Args:
        obj: 骨架对象
        
    Returns:
        tuple: (是否进行了缩放, 缩放因子, 原始高度)
    """
    # 切换到对象模式应用当前旋转
    bpy.ops.object.mode_set(mode='OBJECT')
    # 应用当前旋转
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    
    # 切换到编辑模式
    bpy.ops.object.mode_set(mode='EDIT')
    edit_bones = obj.data.edit_bones
    
    # 获取骨架高度
    skeleton_height = calculate_skeleton_height(edit_bones)
    
    scale_factor = 1.0
    scaled = False
    
    # 检查高度并计算缩放因子
    if skeleton_height > 10:
        # 计算缩放因子：10m→0.1，100m→0.01，类推
        temp_height = skeleton_height
        while temp_height > 10:
            scale_factor *= 0.1
            temp_height *= 0.1
        
        # 切换到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')
        # 重置缩放
        obj.scale = (1.0, 1.0, 1.0)
        # 缩放
        obj.scale *= scale_factor
        # 清除父级
        obj.parent = None
        # 使用apply_armature_transforms应用变换
        
        context = bpy.context
        apply_armature_transforms(context, obj)
        scaled = True


    
    return scaled, scale_factor, skeleton_height


# ---- 骨骼扭转（roll）规则 ----
# 范围1 · 局部轴骨骼（手臂链 + 扭转骨 + 手指）：左右侧分别用全局 ±Z
#     命中特征：肩/腕/ひじ/手首（手臂链）、捩（扭转骨）、
#               親指/人指/中指/薬指/小指（手指）。
#     左侧(名含 .L 或以「左」开头) → 全局 +Z；右侧(名含 .R 或以「右」开头) → 全局 -Z。
# 范围2 · 其余所有骨骼：按「头部是否高于尾部」用全局 ±Y
#     head 高于 tail（世界 Z 更大）→ 全局 +Y；否则 → 全局 -Y。
# （全局轴均按骨架世界矩阵转到骨架局部空间，处理骨架自身旋转。）

_ARM_HINTS = ("肩", "腕", "ひじ", "手首")                    # 手臂链：肩/上腕/腕/ひじ/手首
_TWIST_HINTS = ("捩",)                                      # 扭转骨（捩骨）
_FINGER_HINTS = ("親指", "人指", "中指", "薬指", "小指")      # 手指
_LOCAL_AXIS_HINTS = _ARM_HINTS + _TWIST_HINTS + _FINGER_HINTS


def _is_left(name):
    """骨骼是否属于左侧（名含 .L 或以「左」开头）。"""
    return (".L" in name) or name.startswith("左")


def _is_right(name):
    """骨骼是否属于右侧（名含 .R 或以「右」开头）。"""
    return (".R" in name) or name.startswith("右")


def _is_local_axis_bone(name):
    """是否局部轴骨骼（手臂链/扭转骨/手指），用全局 ±Z。"""
    return any(h in name for h in _LOCAL_AXIS_HINTS)


# 全局轴 MMD 标准骨骼特征（躯干/头/腿/重心/IK 等），用于「是否为 MMD 骨架」检测。
_MMD_GLOBAL_HINTS = (
    "センター", "グルーブ", "腰", "上半身", "下半身",
    "首", "頭", "足", "ひざ", "足首", "つま先", "足先", "腿",
    "全ての親", "操作中心",
)


def _is_mmd_bone(name):
    """是否为 MMD 标准骨骼（局部轴或全局轴任一命中，或含 IK）。"""
    if _is_local_axis_bone(name):
        return True
    if any(h in name for h in _MMD_GLOBAL_HINTS):
        return True
    if 'IK' in name.upper():
        return True
    return False


def count_mmd_bones(edit_bones):
    """统计可识别的 MMD 标准骨骼数量，用于判定骨架是否为 MMD。"""
    return sum(1 for b in edit_bones if _is_mmd_bone(b.name))


def calculate_auto_bone_roll(edit_bones, armature_obj=None):
    """按骨骼名与几何方向计算扭转（roll），复刻 Blender「Shift+N 重算扭转」的全局轴语义。

    规则：
    - 局部轴骨骼（手臂链/扭转骨/手指）：左侧 → 全局 +Z，右侧 → 全局 -Z。
    - 其余所有骨骼：head 高于 tail（世界 Z 更大）→ 全局 +Y，否则 → 全局 -Y。

    全局轴均按骨架世界矩阵转到骨架局部空间，处理骨架自身旋转。
    返回 (adjusted, local_count, fallback_count)：
        adjusted       实际发生变化的骨骼数
        local_count    按 ±Z 处理的局部轴骨骼数
        fallback_count 按 ±Y 处理的其余骨骼数
    """
    # 世界轴转到骨架局部空间（处理骨架自身旋转，等价于 Shift+N 的「全局」语义）
    if armature_obj is not None:
        inv_rot = armature_obj.matrix_world.to_3x3().inverted()
        mw = armature_obj.matrix_world
    else:
        inv_rot = None
        mw = None

    def to_local(v):
        return (inv_rot @ v) if inv_rot is not None else v

    g_pos_z = to_local(Vector((0.0, 0.0, 1.0)))
    g_neg_z = to_local(Vector((0.0, 0.0, -1.0)))
    g_pos_y = to_local(Vector((0.0, 1.0, 0.0)))
    g_neg_y = to_local(Vector((0.0, -1.0, 0.0)))

    adjusted = 0
    local_count = 0
    fallback_count = 0

    for bone in edit_bones:
        # 零长度骨骼无法定义方向，跳过
        if (bone.tail - bone.head).length < 1e-6:
            continue

        try:
            current_roll = bone.roll
            if _is_local_axis_bone(bone.name):
                # 局部轴骨骼：左侧 +Z，右侧 -Z（复刻 Shift+N 全局 ±Z）
                bone.align_roll(g_neg_z if _is_right(bone.name) else g_pos_z)
                local_count += 1
            else:
                # 其余骨骼：head 高于 tail → +Y，否则 -Y
                if mw is not None:
                    head_w = mw @ bone.head
                    tail_w = mw @ bone.tail
                else:
                    head_w = bone.head
                    tail_w = bone.tail
                bone.align_roll(g_pos_y if head_w.z > tail_w.z else g_neg_y)
                fallback_count += 1

            if abs(bone.roll - current_roll) > 0.001:
                adjusted += 1
        except ReferenceError:
            # 骨骼已被移除，忽略
            continue

    return adjusted, local_count, fallback_count