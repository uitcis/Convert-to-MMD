"""方案 C 的打分与约束求解核心：不依赖 bpy / mathutils，可独立单元测试。

原始贡献分（合计 1.20，最终除以 RAW_TOTAL 归一到 0~1）：

    名称  0.40（精确同义）/ 0.25（包含）/ 0.00~0.15（编辑距离）
    拓扑  0.25（层级深度、链位置、父子关系）
    几何  0.15（左右符号）+ 0.10（高度分位）+ 0.10（方向/长度比例）
    权重  0.05~0.20（影响区域落在预期部位；手指/脚趾取高值）

向量按 duck typing 处理：任何支持 v[0] / v[1] / v[2] 下标的对象均可，
因此 mathutils.Vector 和普通测试用三元组都可直接传入。
"""

import json
import math
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher

try:  # 作为插件包的一部分导入
    from ..bone_map_and_group import mmd_bone_map
except (ImportError, ValueError):  # 作为独立模块导入（单元测试）
    try:
        from bone_map_and_group import mmd_bone_map
    except ImportError:
        mmd_bone_map = {}

FIELD_ORDER = list(mmd_bone_map.keys()) + ["breast_parent_bone"]

# 面板/提示展示用名：内部字段名 -> MMD 日文骨骼名
FIELD_LABELS = dict(mmd_bone_map)
FIELD_LABELS["breast_parent_bone"] = "胸親父级"


def field_label(field):
    """把内部字段名转成对应的 MMD 日文骨骼名，未收录时原样返回。"""
    return FIELD_LABELS.get(field, field)

# 原始分上限
NAME_EXACT = 0.40
NAME_CONTAINS = 0.25
NAME_EDIT_MAX = 0.15
TOPO_MAX = 0.25
SIDE_MAX = 0.15
HEIGHT_MAX = 0.10
DIRECTION_MAX = 0.10
WEIGHT_MAX = 0.20
RAW_TOTAL = (NAME_EXACT + TOPO_MAX + SIDE_MAX + HEIGHT_MAX
             + DIRECTION_MAX + WEIGHT_MAX)  # 1.20

EDIT_MIN_RATIO = 0.60      # 编辑距离低于此值不给分
CONFIDENCE_THRESHOLD = 0.55
MIN_CANDIDATE_SCORE = 0.35
MIRROR_TOLERANCE = 0.08    # 左右镜像误差（相对身高）
LOW_CONF_REPORT_SCORE = 0.45
DERIVED_THRESHOLD = 0.50   # 拓扑派生骨（如胸親父级）的放宽阈值
MAX_CANDIDATES = 6
MAX_SEARCH_NODES = 200000
FILL_BONUS = 0.15          # 回溯目标：鼓励填满字段而非只取高分

PRESET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets"
)

# 父 -> 子，只有两侧都分配时才校验
CHAIN_PAIRS = [
    ("lower_body_bone", "left_thigh_bone"),
    ("lower_body_bone", "right_thigh_bone"),
    ("left_thigh_bone", "left_calf_bone"),
    ("right_thigh_bone", "right_calf_bone"),
    ("left_calf_bone", "left_foot_bone"),
    ("right_calf_bone", "right_foot_bone"),
    ("left_foot_bone", "left_toe_bone"),
    ("right_foot_bone", "right_toe_bone"),
    ("left_shoulder_bone", "left_upper_arm_bone"),
    ("right_shoulder_bone", "right_upper_arm_bone"),
    ("left_upper_arm_bone", "left_lower_arm_bone"),
    ("right_upper_arm_bone", "right_lower_arm_bone"),
    ("left_lower_arm_bone", "left_hand_bone"),
    ("right_lower_arm_bone", "right_hand_bone"),
    ("upper_body_bone", "upper_body2_bone"),
    ("upper_body2_bone", "upper_body3_bone"),
    ("upper_body3_bone", "upper_body4_bone"),
    ("upper_body4_bone", "upper_body5_bone"),
    ("neck_bone", "head_bone"),
]

FINGER_FIELDS = [f for f in FIELD_ORDER
                 if re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_", f)]

# 字段优先级：能靠 _post_complete 拓扑推导的辅助骨是低优先级，冲突时
# 让位给必须独立匹配的真实骨。低优先级仅限 MMD 特有的推导骨——上半身
# 2~5 与胸親父级；四肢/頭/腰虽然在链里有父子关系，但都有独立骨骼，
# 仍需独立匹配。只影响回溯目标函数，不改变候选打分与阈值；排序仍按
# 分数优先，避免低分控制骨抢占主链骨（见 testmiku 修复）。
AUTO_COMPLETE_FIELDS = frozenset(
    f"upper_body{i}_bone" for i in (2, 3, 4, 5)
) | {"breast_parent_bone"}
PRIORITY_BONUS_MUST_MATCH = 0.15   # 无法补全的字段：保留价值奖励


def field_priority(field):
    """字段优先级：2=必须独立匹配（高），1=可拓扑补全（低）。"""
    return 1 if field in AUTO_COMPLETE_FIELDS else 2


def field_bonus(field):
    return PRIORITY_BONUS_MUST_MATCH if field_priority(field) == 2 else 0.0

# 各字段期望的高度区间（0=最低，1=最高）
Z_BANDS = {
    "head_bone": (0.80, 1.00),
    "neck_bone": (0.66, 0.92),
    "upper_body_bone": (0.40, 0.72),
    "upper_body2_bone": (0.48, 0.80),
    "upper_body3_bone": (0.52, 0.85),
    "upper_body4_bone": (0.55, 0.88),
    "upper_body5_bone": (0.58, 0.90),
    "hip_bone": (0.26, 0.56),
    "lower_body_bone": (0.24, 0.56),
    "control_center_bone": (0.20, 0.80),
    "all_parents_bone": (0.00, 1.00),
    "center_bone": (0.20, 0.80),
    "groove_bone": (0.20, 0.80),
    "breast_parent_bone": (0.50, 0.90),
}
for _side in ("left", "right"):
    Z_BANDS.update({
        f"{_side}_shoulder_bone": (0.55, 0.92),
        f"{_side}_upper_arm_bone": (0.30, 0.92),
        f"{_side}_lower_arm_bone": (0.20, 0.90),
        f"{_side}_hand_bone": (0.15, 0.90),
        f"{_side}_thigh_bone": (0.15, 0.60),
        f"{_side}_calf_bone": (0.04, 0.40),
        f"{_side}_foot_bone": (0.00, 0.20),
        f"{_side}_toe_bone": (0.00, 0.16),
        f"{_side}_eye_bone": (0.75, 1.00),
        f"{_side}_chest_bone": (0.45, 0.85),
    })
    for _finger in ("thumb", "index", "middle", "ring", "pinky"):
        for _i in ("0", "1", "2", "3"):
            Z_BANDS[f"{_side}_{_finger}_{_i}"] = (0.10, 0.95)

# 相对身高的期望骨长区间，用于方向/长度比例分
LENGTH_RATIOS = {
    "finger": (0.008, 0.060),
    "toe": (0.008, 0.060),
    "eye": (0.000, 0.035),
    "hand": (0.015, 0.100),
    "foot": (0.020, 0.140),
    "head": (0.050, 0.300),
    "chest": (0.010, 0.120),
    "neck": (0.020, 0.150),
}
DEFAULT_LENGTH_RATIO = (0.010, 0.350)

FINGER_ALIASES = {
    "thumb": [("thumb",), ("pollex",), ("finger", "0")],
    "index": [("index",), ("indexfinger",), ("finger", "1")],
    "middle": [("middle",), ("middlefinger",), ("finger", "2")],
    "ring": [("ring",), ("ringfinger",), ("finger", "3")],
    "pinky": [("pinky",), ("little",), ("pinkie",), ("finger", "4")],
}

ALIAS_TOKENS = {
    "head_bone": [("head",)],
    "neck_bone": [("neck",)],
    "upper_body_bone": [("spine",), ("torso",), ("abdomen",), ("upperbody",)],
    "upper_body2_bone": [("chest",), ("spine1",), ("upperchest",)],
    "upper_body3_bone": [("upperchest",), ("spine2",)],
    "upper_body4_bone": [("spine3",)],
    "upper_body5_bone": [("spine4",)],
    "hip_bone": [("hips",), ("pelvis",), ("hip",)],
    "lower_body_bone": [("hips",), ("pelvis",), ("lowerbody",)],
    "left_shoulder_bone": [("clavicle",), ("shoulder",)],
    "right_shoulder_bone": [("clavicle",), ("shoulder",)],
    "left_upper_arm_bone": [("upperarm",), ("arm",)],
    "right_upper_arm_bone": [("upperarm",), ("arm",)],
    "left_lower_arm_bone": [("forearm",), ("lowerarm",), ("elbow",)],
    "right_lower_arm_bone": [("forearm",), ("lowerarm",), ("elbow",)],
    "left_hand_bone": [("hand",), ("wrist",)],
    "right_hand_bone": [("hand",), ("wrist",)],
    "left_thigh_bone": [("thigh",), ("upleg",), ("upperleg",)],
    "right_thigh_bone": [("thigh",), ("upleg",), ("upperleg",)],
    "left_calf_bone": [("calf",), ("shin",), ("lowerleg",), ("knee",)],
    "right_calf_bone": [("calf",), ("shin",), ("lowerleg",), ("knee",)],
    "left_foot_bone": [("foot",), ("ankle",)],
    "right_foot_bone": [("foot",), ("ankle",)],
    "left_toe_bone": [("toe",), ("ball",)],
    "right_toe_bone": [("toe",), ("ball",)],
    "left_eye_bone": [("eye",)],
    "right_eye_bone": [("eye",)],
    "left_chest_bone": [("breast",), ("chest",), ("bust",)],
    "right_chest_bone": [("breast",), ("chest",), ("bust",)],
    "control_center_bone": [("root",), ("control",), ("center",)],
    "all_parents_bone": [("root",), ("master",), ("parent",)],
    "center_bone": [("center",), ("ctrl",)],
    "groove_bone": [("groove",), ("waist",)],
    "breast_parent_bone": [("chest",), ("spine",)],
}

# 多个「非左右」字段共用的英文词：只给这里指定的主字段精确档，其余走 0.25。
# 目的：避免 hips 同时给腰/下半身、chest 同时给上半身2/左右胸/胸親 而争同一根骨。
AMBIGUOUS_PRIMARY = {
    "center": "center_bone",
    "chest": "upper_body2_bone",
    "hips": "lower_body_bone",     # 下半身是腿链父级，断了损失更大
    "pelvis": "lower_body_bone",
    "root": "all_parents_bone",
    "spine": "upper_body_bone",
    "upperchest": "upper_body3_bone",
}

_PRESET_STATS = None
_NAME_SCORE_CACHE = {}


# ---------------------------------------------------------------- 基础工具

def _vsub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _vlen(v):
    return math.sqrt(sum(x * x for x in v))


def _vdot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _vunit(v):
    length = _vlen(v)
    if length <= 1e-9:
        return None
    return tuple(x / length for x in v)


def _category(field):
    if field == "all_parents_bone":
        return "root"
    if field in ("center_bone", "groove_bone", "control_center_bone",
                 "breast_parent_bone"):
        return "control"
    if field == "hip_bone":
        return "hip"
    if field.startswith("upper_body") or field == "lower_body_bone":
        return "torso"
    if field == "neck_bone":
        return "neck"
    if field == "head_bone":
        return "head"
    if "eye_bone" in field:
        return "eye"
    if "chest_bone" in field:
        return "chest"
    if field in FINGER_FIELDS:
        return "finger"
    for token in ("shoulder", "upper_arm", "lower_arm", "hand",
                  "thigh", "calf", "foot", "toe"):
        if token in field:
            return token
    return "other"


def _field_side(field):
    if field.startswith("left_"):
        return "L"
    if field.startswith("right_"):
        return "R"
    return None


def _normalize(name):
    """归一化骨骼名：全角数字转半角、去常见前缀、去分隔符、小写。"""
    n = name.lower()
    n = n.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    n = re.sub(r"^(mixamorig|bip0?0?1|vrm|armature)[:._ -]*", "", n)
    n = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", "", n)
    return n


def _build_common_names():
    """内置常用名表：字段 -> 归一化后的规范名集合（日文 + 英文）。

    骨架绝大多数是英文命名（Spine/Chest/UpperLeg_L），所以英文常用名
    必须和日文规范名一样拿精确匹配 0.40，否则等于只照顾日文骨架。

    来源：
      - 日文规范名取 FIELD_LABELS（上半身3-5/左右胸/胸親 等预设表为空
        的字段由此受益），另加「胸親」标准写法。
      - 英文常用名取 ALIAS_TOKENS 的单 token 组，覆盖三种常见写法：
        裸词(thigh) / 侧别后缀(Thigh_L) / 侧别前缀(LeftThigh)。

    冲突处理：同一个英文词被多个「非左右」字段共用时（hips/chest/root
    等），若全部升到 0.40 会让它们争抢同一根骨（hip_bone 与 lower_body
    对 Hips 并列 → 下半身被挤空）。这类词只给 AMBIGUOUS_PRIMARY 指定的
    主字段精确档，其余字段仍走 0.25 包含匹配。左右成对字段不算冲突——
    左右靠坐标符号区分，不会争同一根骨。
    """
    table = {field: set() for field in FIELD_ORDER}
    for field, label in FIELD_LABELS.items():
        norm = _normalize(label)
        if norm:
            table.setdefault(field, set()).add(norm)
    norm = _normalize("胸親")
    if norm:
        table.setdefault("breast_parent_bone", set()).add(norm)

    uses = defaultdict(list)
    for field, groups in ALIAS_TOKENS.items():
        for group in groups:
            if len(group) == 1:
                uses[_normalize(group[0])].append(field)

    for token, fields in uses.items():
        if token in AMBIGUOUS_PRIMARY:
            table.setdefault(AMBIGUOUS_PRIMARY[token], set()).add(token)
            # 冲突词若同时被左右成对字段使用，裸词只给主字段（避免中轴
            # Chest 被左右胸抢），但带侧别的 Chest_L/Chest_R 仍归左右胸。
            for field in fields:
                names = table.setdefault(field, set())
                if field.startswith("left_"):
                    names.update((token + "l", "l" + token, "left" + token))
                elif field.startswith("right_"):
                    names.update((token + "r", "r" + token, "right" + token))
            continue
        pair_only = all(f.startswith(("left_", "right_")) for f in fields)
        if len(fields) == 1 or pair_only:
            for field in fields:
                names = table.setdefault(field, set())
                names.add(token)
                if field.startswith("left_"):
                    names.update((token + "l", "l" + token, "left" + token))
                elif field.startswith("right_"):
                    names.update((token + "r", "r" + token, "right" + token))
    return table


COMMON_NAMES = _build_common_names()


def _tokens(name):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"([_.:\- ])+", " ", s)
    return [t.lower() for t in s.split() if t]


def _band_score(band, value):
    if not band:
        return 0.8
    low, high = band
    if low <= value <= high:
        return 1.0
    distance = low - value if value < low else value - high
    return math.exp(-((distance / 0.12) ** 2))


def detect_side_axis(features, up_axis=2):
    """用成对左右骨的实际坐标差推断左右轴，避免硬编码 X。

    识别 left_/right_、l_/r_、.L/.R 等常见命名；找不到配对时回退：
    高度轴不是 X 就用 X，否则用 Z。
    """
    left = {}
    right = {}
    for name, feature in features.items():
        lower = name.lower()
        match = re.match(r"^(left|right)[._ -]", lower)
        if match:
            target = left if match.group(1) == "left" else right
            target[lower[match.end():]] = feature.head
            continue
        match = re.match(r"^([lr])[._ -]", lower)
        if match:
            target = left if match.group(1) == "l" else right
            target[lower[match.end():]] = feature.head
            continue
        if lower.endswith((".l", "_l")):
            left[lower[:-2]] = feature.head
        elif lower.endswith((".r", "_r")):
            right[lower[:-2]] = feature.head

    pairs = [(left[key], right[key]) for key in left if key in right]
    if not pairs:
        return 0 if up_axis != 0 else 2
    differences = [sum(abs(l[i] - r[i]) for l, r in pairs) / len(pairs)
                   for i in range(3)]
    return max(range(3), key=lambda i: differences[i])


# ---------------------------------------------------------------- 预设名称库

def load_preset_stats(preset_dir=None):
    """统计 presets 目录中每个字段出现过的骨骼名。"""
    global _PRESET_STATS
    if _PRESET_STATS is not None and preset_dir is None:
        return _PRESET_STATS
    directory = preset_dir if preset_dir is not None else PRESET_DIR
    stats = {f: {} for f in FIELD_ORDER}
    try:
        filenames = sorted(os.listdir(directory))
    except OSError:
        filenames = []
    for filename in filenames:
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, filename), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for field, value in data.items():
            if field not in stats or not isinstance(value, str):
                continue
            norm = _normalize(value)
            if norm:
                stats[field][norm] = stats[field].get(norm, 0) + 1
    if preset_dir is None:
        _PRESET_STATS = stats
    return stats


def invalidate_preset_cache():
    """预设导入/变更后调用，避免沿用旧的名称统计。"""
    global _PRESET_STATS
    _PRESET_STATS = None
    _NAME_SCORE_CACHE.clear()


def name_contribution(field, bone_name, stats):
    """名称证据：精确同义 0.40 / 包含 0.25 / 编辑距离 0~0.15。"""
    norm = _normalize(bone_name)
    if not norm:
        return 0.0, ""
    key = (field, norm)
    cached = _NAME_SCORE_CACHE.get(key)
    if cached is not None:
        return cached

    table = stats.get(field, {})
    if norm in table:
        result = (NAME_EXACT, "名称精确匹配")
        _NAME_SCORE_CACHE[key] = result
        return result

    # 内置常用名：日文规范名 + 英文单词别名。不依赖预设是否收录该字段，
    # 解决上半身3-5/左右胸/胸親等预设表为空的字段日文名拿不到分的问题。
    if norm in COMMON_NAMES.get(field, ()):
        result = (NAME_EXACT, "常用名精确匹配")
        _NAME_SCORE_CACHE[key] = result
        return result

    tokens = _tokens(bone_name)
    if _alias_hit(field, tokens):
        result = (NAME_CONTAINS, "名称包含匹配")
        _NAME_SCORE_CACHE[key] = result
        return result

    best = 0.0
    for known in table:
        if abs(len(known) - len(norm)) > 6:
            continue
        ratio = SequenceMatcher(None, norm, known).ratio()
        if ratio > best:
            best = ratio
    if best >= EDIT_MIN_RATIO:
        raw = NAME_EDIT_MAX * (best - EDIT_MIN_RATIO) / (1.0 - EDIT_MIN_RATIO)
        result = (raw, f"名称相似 {best:.2f}")
    else:
        result = (0.0, "")
    _NAME_SCORE_CACHE[key] = result
    return result


def _alias_hit(field, tokens):
    token_set = set(tokens)
    groups = list(ALIAS_TOKENS.get(field, []))
    match = re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_(\d)$", field)
    if match:
        finger, digit = match.group(2), match.group(3)
        groups.extend(FINGER_ALIASES.get(finger, []))
        if finger == "thumb":
            wanted = {"0": ("1",), "1": ("2",), "2": ("3",)}.get(digit, ())
        else:
            wanted = (digit,)
        for group in groups:
            if set(group).issubset(token_set) and any(w in token_set for w in wanted):
                return True
        return False
    return any(set(group).issubset(token_set) for group in groups)


# ---------------------------------------------------------------- 四类证据

def topology_contribution(field, feature):
    """拓扑证据：层级深度、链位置、父子关系。"""
    category = _category(field)
    score = 0.5
    if category == "root":
        score = 1.0 if feature.depth == 0 else 0.2
    elif category == "control":
        score = 1.0 if feature.depth <= 3 else 0.5
        # 控制骨通常不蒙皮，带权重的形变骨应让位给身体链字段
        if feature.weight_sum > 0:
            score *= 0.6
    elif category == "hip":
        score = 1.0 if feature.depth <= 3 and feature.child_count >= 2 else 0.6
    elif category == "torso":
        score = 1.0 if feature.child_count >= 1 else (0.5 if field == "upper_body_bone" else 0.6)
    elif category == "neck":
        score = 1.0 if 1 <= feature.child_count <= 3 else 0.55
    elif category == "head":
        score = 1.0
    elif category == "eye":
        score = 1.0 if feature.child_count == 0 and feature.length > 0 else 0.6
    elif category == "chest":
        score = 1.0 if feature.weight_sum > 0 else 0.4
    elif category == "finger":
        score = 1.0 if (feature.child_count <= 1 if field.endswith("_3")
                        else feature.child_count == 1) else 0.7
    elif category == "shoulder":
        score = 1.0 if feature.child_count == 1 else 0.6
    elif category in ("upper_arm", "lower_arm"):
        score = 1.0 if feature.child_count == 1 else 0.55
    elif category == "hand":
        score = 1.0 if feature.child_count >= 1 else 0.65
    elif category in ("thigh", "calf"):
        score = 1.0 if feature.child_count >= 1 else 0.55
    elif category == "foot":
        score = 1.0 if feature.child_count >= 1 else 0.65
    elif category == "toe":
        score = 1.0 if feature.child_count <= 1 else 0.75
    return TOPO_MAX * score, f"拓扑 {score:.2f}"


def geometry_contributions(field, feature, features, ctx):
    """几何证据：左右符号 0.15 + 高度分位 0.10 + 方向/长度比例 0.10。"""
    span = ctx["span"]
    side_axis = ctx["side_axis"]
    up_axis = ctx["up_axis"]

    side = _field_side(field)
    if side is None:
        side_raw, side_reason = 0.5, "中心骨"
    else:
        coord = feature.head[side_axis]
        want_positive = (side == "L")
        if abs(coord) > 1e-6 and (coord > 0) == want_positive:
            reference = 0.05 * span if span > 0 else 1e-6
            side_raw = min(1.0, abs(coord) / reference)
            side_reason = "左右符号正确"
        else:
            side_raw, side_reason = 0.0, "左右符号不符"

    height_raw = _band_score(Z_BANDS.get(field), feature.z_pct)
    height_reason = "高度吻合" if height_raw >= 0.99 else f"高度偏差 {height_raw:.2f}"

    category = _category(field)
    low, high = LENGTH_RATIOS.get(category, DEFAULT_LENGTH_RATIO)
    if span > 0:
        ratio = feature.length / span
        if low <= ratio <= high:
            length_raw = 1.0
        elif ratio < low:
            length_raw = max(0.0, ratio / low) if low > 0 else 1.0
        else:
            length_raw = max(0.0, 1.0 - (ratio - high) / (high * 2))
    else:
        length_raw = 0.5

    if category in ("finger", "toe") and feature.parent in features:
        own = _vunit(_vsub(feature.tail, feature.head))
        parent = features[feature.parent]
        parent_dir = _vunit(_vsub(parent.tail, parent.head))
        direction_raw = max(0.0, _vdot(own, parent_dir)) if own and parent_dir else 0.5
    else:
        direction_raw = 0.5  # 中性，不偏袒任何模型
    direction_raw = 0.5 * length_raw + 0.5 * direction_raw

    parts = {
        "side": SIDE_MAX * side_raw,
        "height": HEIGHT_MAX * height_raw,
        "direction": DIRECTION_MAX * direction_raw,
    }
    reasons = [side_reason, height_reason, f"方向长度 {direction_raw:.2f}"]
    return parts, "、".join(reasons)


def weight_contribution(field, feature, features, ctx):
    """权重证据：影响区域落在预期部位；手指/脚趾加权更高。"""
    if feature.weight_sum <= 0 or feature.weight_centroid is None:
        return 0.0, "无蒙皮权重"
    centroid = feature.weight_centroid
    diagonal = ctx["diagonal"]
    span = ctx["span"]
    proximity = math.exp(-((_vlen(_vsub(centroid, feature.head))
                            / (0.25 * diagonal)) ** 2)) if diagonal > 0 else 0.8
    centroid_z = ((centroid[ctx["up_axis"]] - ctx["z_min"]) / span) if span > 0 else 0.5
    region = _band_score(Z_BANDS.get(field), centroid_z)

    category = _category(field)
    if category in ("finger", "toe"):
        cap = WEIGHT_MAX
    elif category in ("eye", "chest"):
        cap = 0.10
    elif category in ("root", "control"):
        cap = 0.05
    else:
        cap = 0.12
    base = 0.5 * proximity + 0.5 * region
    return cap * base, f"权重质心匹配 {base:.2f}"


def score_candidate(field, feature, features, ctx):
    # 左右符号按 0.15 权重参与几何分，而非硬过滤：即使左右轴判定有偏差，
    # 名称证据仍有机会入选，由镜像约束在成对字段间兜底。
    # 例外：左右胸是成对侧别骨，中轴胸腔骨（Chest/Spine）名字含 chest 会误命中
    # 别名，须硬过滤掉，否则与上半身2抢同一根骨并导致左右胸留空。
    side = _field_side(field)
    if side is not None and _category(field) == "chest":
        coord = feature.head[ctx["side_axis"]]
        if abs(coord) <= 1e-6 or (coord > 0) != (side == "L"):
            return None
    name_raw, name_reason = name_contribution(field, feature.name, ctx["stats"])
    topo_raw, topo_reason = topology_contribution(field, feature)
    # 语义字段缺少命名证据时，单靠高度带会命中头发等无关骨骼
    if name_raw <= 0.0 and _category(field) in ("eye", "chest"):
        return None
    geo_parts, geo_reason = geometry_contributions(field, feature, features, ctx)
    weight_raw, weight_reason = weight_contribution(field, feature, features, ctx)

    parts = {"name": name_raw, "topology": topo_raw, **geo_parts, "weight": weight_raw}
    raw = sum(parts.values())
    score = raw / RAW_TOTAL
    reason = "；".join(r for r in (name_reason, topo_reason, geo_reason, weight_reason) if r)
    return {
        "field": field,
        "bone": feature.name,
        "score": score,
        "raw": raw,
        "parts": parts,
        "reason": reason,
    }


# ---------------------------------------------------------------- 约束

def _is_ancestor(features, ancestor_name, descendant_name):
    if ancestor_name == descendant_name:
        return True
    current = features[descendant_name].parent
    while current:
        if current == ancestor_name:
            return True
        current = features[current].parent if current in features else None
    return False


def chain_ok(field, bone, assignments, features):
    for parent_field, child_field in CHAIN_PAIRS:
        if field == child_field and parent_field in assignments:
            if not _is_ancestor(features, assignments[parent_field]["bone"], bone):
                return False
        if field == parent_field and child_field in assignments:
            if not _is_ancestor(features, bone, assignments[child_field]["bone"]):
                return False
    return True


def mirror_error(field, bone, assignments, features, ctx):
    """返回左右骨相对身高镜像误差；无对侧或无需配对时返回 0。"""
    if field.startswith("left_"):
        pair = "right_" + field[len("left_"):]
    elif field.startswith("right_"):
        pair = "left_" + field[len("right_"):]
    else:
        return 0.0
    if pair not in assignments:
        return 0.0
    other = assignments[pair]["bone"]
    if bone not in features or other not in features:
        return 0.0
    a, b = features[bone].head, features[other].head
    span = ctx["span"]
    if span <= 0:
        return 1.0
    axis = ctx["side_axis"]
    # 左右轴反向误差是主判据，其余两轴的一致性只作半权修正，
    # 避免三轴平均把「同侧误配」稀释到阈值以下。
    error = abs(a[axis] + b[axis])
    for other_axis in range(3):
        if other_axis != axis:
            error += 0.5 * abs(a[other_axis] - b[other_axis])
    return error / span


def _descendants(features, root_name):
    result = []
    stack = [c for c in features[root_name].children if c in features]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(c for c in features[current].children if c in features)
    return result


# ---------------------------------------------------------------- 求解

def _solve_backtrack(candidates, field_order, features, ctx):
    """DFS，目标 = 总分 + 字段奖励 + 优先级奖励（可补全字段为低优先级）。"""
    # 最高候选分优先：先让证据最强的字段挑骨，避免候选少的控制骨
    # （如 center_bone）抢占 Hips 这类主链骨，导致腰/下半身/腿链连锁失败。
    order = sorted(field_order,
                   key=lambda f: (-max((c["score"] for c in candidates.get(f, [])),
                                       default=0.0),
                                  len(candidates.get(f, []))))
    remaining = [0.0] * (len(order) + 1)
    for index in range(len(order) - 1, -1, -1):
        field = order[index]
        best = max((c["score"] for c in candidates.get(field, [])), default=0.0)
        remaining[index] = (remaining[index + 1] + best + FILL_BONUS
                            + field_bonus(field))

    # 先按同一顺序求一个贪心解当保底下界：搜索被节点上限截断时也有结果，
    # 且强下界能让后续剪枝提前生效。
    greedy = {}
    greedy_used = set()
    for field in order:
        for candidate in candidates.get(field, []):
            bone = candidate["bone"]
            if bone in greedy_used:
                continue
            if not chain_ok(field, bone, greedy, features):
                continue
            if mirror_error(field, bone, greedy, features, ctx) > MIRROR_TOLERANCE:
                continue
            greedy[field] = candidate
            greedy_used.add(bone)
            break
    best_value = sum(c["score"] + FILL_BONUS + field_bonus(f)
                     for f, c in greedy.items())
    best_assignment = dict(greedy)
    nodes = [0]

    def dfs(index, assignments, used, total):
        nonlocal best_value, best_assignment
        nodes[0] += 1
        if nodes[0] > MAX_SEARCH_NODES:
            return
        if total + remaining[index] <= best_value:
            return
        if index == len(order):
            if total > best_value:
                best_value = total
                best_assignment.clear()
                best_assignment.update(assignments)
            return

        field = order[index]
        gain = FILL_BONUS + field_bonus(field)
        for candidate in candidates.get(field, []):
            bone = candidate["bone"]
            if bone in used:
                continue
            if not chain_ok(field, bone, assignments, features):
                continue
            if mirror_error(field, bone, assignments, features, ctx) > MIRROR_TOLERANCE:
                continue
            assignments[field] = candidate
            used.add(bone)
            dfs(index + 1, assignments, used, total + candidate["score"] + gain)
            del assignments[field]
            used.remove(bone)
        dfs(index + 1, assignments, used, total)  # 允许留空

    dfs(0, {}, set(), 0.0)
    return best_assignment, nodes[0]


def _post_complete(assignments, candidates, field_order, features, ctx):
    """回溯后的确定性补全：主链、上半身链、胸部父骨。"""
    used = {c["bone"] for c in assignments.values()}

    for parent_field, child_field in CHAIN_PAIRS:
        if child_field in assignments or parent_field not in assignments:
            continue
        if child_field.startswith("upper_body"):
            continue
        parent_bone = assignments[parent_field]["bone"]
        best = None
        for bone_name in _descendants(features, parent_bone):
            if bone_name in used:
                continue
            candidate = score_candidate(child_field, features[bone_name], features, ctx)
            if (not candidate or candidate["score"] < CONFIDENCE_THRESHOLD
                    or not chain_ok(child_field, bone_name, assignments, features)):
                continue
            if best is None or candidate["score"] > best["score"]:
                best = candidate
        if best:
            assignments[child_field] = best
            used.add(best["bone"])

    if "upper_body_bone" in assignments and "neck_bone" in assignments:
        upper_name = assignments["upper_body_bone"]["bone"]
        neck_name = assignments["neck_bone"]["bone"]
        chain = []
        current = features[neck_name].parent
        while current:
            if current == upper_name:
                break
            chain.append(current)
            current = features[current].parent if current in features else None
        chain.reverse()
        for index, field in enumerate(("upper_body2_bone", "upper_body3_bone",
                                       "upper_body4_bone", "upper_body5_bone")):
            if index >= len(chain):
                break
            bone_name = chain[index]
            if field in assignments or bone_name in used:
                continue
            candidate = score_candidate(field, features[bone_name], features, ctx)
            if candidate and candidate["score"] >= CONFIDENCE_THRESHOLD:
                candidate["derived"] = "upper_body_chain"
                assignments[field] = candidate
                used.add(bone_name)

    if "breast_parent_bone" not in assignments:
        anchor = None
        for field in ("upper_body2_bone", "left_chest_bone", "upper_body_bone"):
            if field in assignments:
                anchor = assignments[field]["bone"]
                break
        if anchor and anchor in features:
            current = features[anchor].parent
            best = None
            while current:
                # 胸親是辅助骨：MMD 标准骨架里它常与「上半身/上半身2」共用
                # 同一根骨（Mixamo 的 Spine/Chest 就是这种情况），因此允许
                # 复用主链已占用的骨骼，只要求拓扑上位于锚点的父链。
                candidate = score_candidate("breast_parent_bone", features[current],
                                            features, ctx)
                if candidate and (best is None or candidate["score"] > best["score"]):
                    best = candidate
                current = features[current].parent if current in features else None
            # 辅助骨用略低的派生阈值，避免 0.54 这种边界分把明显的骨留空
            if best and best["score"] >= DERIVED_THRESHOLD:
                best["derived"] = "chest_parent_chain"
                assignments["breast_parent_bone"] = best


def explain_missing(field, candidates, assignments, features, ctx):
    """说明一个高分字段为何未入选，替换笼统的「占用或约束冲突」。"""
    field_candidates = candidates.get(field, [])
    if not field_candidates:
        return "无有效候选"
    top = field_candidates[0]
    bone = top["bone"]
    owner = next((f for f, c in assignments.items() if c["bone"] == bone), None)
    if owner:
        return f"候选 {field_label(bone)} 已被 {field_label(owner)} 占用"
    if not chain_ok(field, bone, assignments, features):
        return "主链父子约束冲突"
    error = mirror_error(field, bone, assignments, features, ctx)
    if error > MIRROR_TOLERANCE:
        return f"左右镜像误差 {error:.2f} 超限"
    return "回溯搜索中未入选"


def solve(field_order, features, span, diagonal, z_min, up_axis, side_axis,
          stats=None, preset_dir=None):
    """完整求解，返回 (assignments, low_conf, stats)。

    assignments 的每项含 score / parts / reason / derived 字段。
    """
    if not features:
        return {}, [], {}
    if stats is None:
        stats = load_preset_stats(preset_dir) if preset_dir else load_preset_stats()
    ctx = {
        "span": span, "diagonal": diagonal, "z_min": z_min,
        "up_axis": up_axis, "side_axis": side_axis, "stats": stats,
    }

    candidates = {}
    best_scores = {}
    for field in field_order:
        field_candidates = []
        for feature in features.values():
            candidate = score_candidate(field, feature, features, ctx)
            if candidate and candidate["score"] >= MIN_CANDIDATE_SCORE:
                field_candidates.append(candidate)
        field_candidates.sort(key=lambda c: c["score"], reverse=True)
        if field_candidates:
            best_scores[field] = field_candidates[0]["score"]
        candidates[field] = field_candidates[:MAX_CANDIDATES]

    assignments, nodes = _solve_backtrack(candidates, field_order, features, ctx)
    assignments = dict(assignments)
    _post_complete(assignments, candidates, field_order, features, ctx)

    low_conf = []
    reported = set()
    for left_field in (f for f in field_order if f.startswith("left_")):
        right_field = "right_" + left_field[len("left_"):]
        if left_field not in assignments or right_field not in assignments:
            continue
        error = mirror_error(left_field, assignments[left_field]["bone"],
                             assignments, features, ctx)
        if error > MIRROR_TOLERANCE:
            drop = (assignments[left_field] if assignments[left_field]["score"]
                    <= assignments[right_field]["score"] else assignments[right_field])
            assignments.pop(drop["field"], None)
            low_conf.append((drop["field"], drop["score"], "左右镜像误差过大"))
            reported.add(drop["field"])

    for field in field_order:
        if field in assignments or field in reported:
            continue
        best = best_scores.get(field, 0.0)
        if best >= LOW_CONF_REPORT_SCORE:
            reason = (explain_missing(field, candidates, assignments, features, ctx)
                      if best >= CONFIDENCE_THRESHOLD else "置信度低于阈值")
            low_conf.append((field, best, reason))

    filled = {f: c for f, c in assignments.items()
              if c["score"] >= CONFIDENCE_THRESHOLD
              or (c.get("derived") and c["score"] >= DERIVED_THRESHOLD)}
    for field in list(assignments):
        if field not in filled and field not in reported:
            low_conf.append((field, assignments[field]["score"], "置信度低于阈值"))

    result_stats = {
        "bone_count": len(features),
        "filled": len(filled),
        "low_conf": len(low_conf),
        "average": (sum(c["score"] for c in filled.values()) / len(filled)
                    if filled else 0.0),
        "search_nodes": nodes,
    }
    return filled, low_conf, result_stats
