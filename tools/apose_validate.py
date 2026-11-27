"""A-Pose 输入校验与提示文案（纯 Python，不依赖 bpy）。

A-Pose 转换需要 6 个身体参考字段全部有效，缺一项就没法建立完整的身体
坐标系或对齐手臂链。原先的校验分散在 operator 里、且只覆盖「空/不存在」
两种状态的一部分：

  - 只校验了上半身/首，手臂字段留到进入编辑模式后才用下标直接取，
    某项为空时抛 KeyError，用户看到的是
    「转换 A-Pose 时出错：'bpy_prop_collection[key]: key "" not found'」；
  - 「未设置」与「骨骼不存在」不区分，也不说明是哪一侧、哪个部位；
  - 提示里用的是内部字段名（left_lower_arm），不是面板上的骨骼名。

本模块把「检查」与「措辞」集中到一处，返回结构化结果，便于测试，
也便于 operator 一次性列出全部问题而不是一次报一个。

用语约定（与面板一致）：left=s 侧别，part=部位，
label 是 MMD 面板上的骨骼名（左腕/左ひじ/上半身…）。
"""

# (字段名, 面板骨骼名, 侧别, 部位, 在 A-Pose 里的作用)
APOSE_FIELDS = (
    ("upper_body_bone", "上半身", "center", "躯干", "确定身体上下方向"),
    ("neck_bone", "首", "center", "躯干", "确定身体上下方向"),
    ("left_upper_arm_bone", "左腕", "left", "上臂", "确定身体左右轴并旋转"),
    ("right_upper_arm_bone", "右腕", "right", "上臂", "确定身体左右轴并旋转"),
    ("left_lower_arm_bone", "左ひじ", "left", "小臂", "对齐上臂末端"),
    ("right_lower_arm_bone", "右ひじ", "right", "小臂", "对齐上臂末端"),
)

SIDE_LABELS = {"left": "左侧", "right": "右侧", "center": "躯干"}

# 状态说明：空值 / 指向的骨骼在骨架里找不到
KIND_EMPTY = "empty"
KIND_MISSING = "missing"
KIND_DUPLICATE = "duplicate"

REQUIREMENT_TEXT = (
    "A-Pose 需要这 6 项都指向存在的骨骼：上半身、首（定上下方向）、"
    "左腕/右腕（定左右轴并旋转）、左ひじ/右ひじ（对齐上臂末端）"
)


def collect_issues(getter, existing_bones):
    """收集全部不可用的字段。

    Args:
        getter: 取字段值，可为 dict 或 scene（用 .get 不通用，故传函数）
        existing_bones: 骨架里实际存在的骨骼名集合

    Returns:
        list[dict]：每项含 field / label / side / part / role / kind / value
    """
    existing = existing_bones
    issues = []
    seen = {}
    for field, label, side, part, role in APOSE_FIELDS:
        value = (getter(field) or "").strip()
        if not value:
            issues.append({
                "field": field, "label": label, "side": side, "part": part,
                "role": role, "kind": KIND_EMPTY, "value": "",
            })
            continue
        if value not in existing:
            issues.append({
                "field": field, "label": label, "side": side, "part": part,
                "role": role, "kind": KIND_MISSING, "value": value,
            })
            continue
        # 同一根骨被多个字段占用：上层坐标系会退化（左右轴为 0），
        # 属于配置错误，同样要提前拦下。
        first = seen.get(value)
        if first is not None:
            issues.append({
                "field": field, "label": label, "side": side, "part": part,
                "role": role, "kind": KIND_DUPLICATE, "value": value,
                "other_label": first,
            })
            continue
        seen[value] = label
    return issues


def describe_issue(issue):
    """把单个问题写成一句可直接展示的话。"""
    side_label = SIDE_LABELS.get(issue["side"], "")
    # 躯干类字段的侧别与部位同名，避免出现「躯干躯干」
    where = (side_label if side_label == issue["part"]
             else f"{side_label}{issue['part']}")
    if issue["kind"] == KIND_EMPTY:
        return f"{issue['label']}（{where}，未设置）"
    if issue["kind"] == KIND_MISSING:
        return f"{issue['label']}（{where}，骨骼 '{issue['value']}' 不存在）"
    return (f"{issue['label']}（{where}，与{issue['other_label']}"
            f"指向同一根骨骼 '{issue['value']}'）")


def build_message(issues, requirement=REQUIREMENT_TEXT):
    """拼成一条可放进 report 的提示：先列问题，再给出输入要求。"""
    if not issues:
        return ""
    parts = [describe_issue(issue) for issue in issues]
    head = (f"无法执行 A-Pose，{len(parts)} 项骨骼不可用："
            if len(parts) > 1 else "无法执行 A-Pose：")
    return head + "、".join(parts) + "。" + requirement


def build_detail_lines(issues, requirement=REQUIREMENT_TEXT):
    """多行明细（打印到控制台/信息面板，便于逐条核对）。"""
    lines = ["[A-Pose] 前置校验未通过："]
    for issue in issues:
        lines.append(f"  - {describe_issue(issue)}（用于{issue['role']}）")
    lines.append(f"  要求：{requirement}")
    return lines
