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
        # 独立导入时本模块位于 tools/，bone_map_and_group 在项目根，
        # 需要把项目根加入 sys.path 才能找到。否则 mmd_bone_map 为空，
        # FIELD_ORDER 会静默退化成只剩 breast_parent_bone。
        import sys as _sys
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
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
# 侧向分的「符号正确」基础档：符号不符仍是 0，只是不再因贴近中轴
# 而额外受罚（锁骨根、内踝这类骨本来就靠中轴）。
SIDE_BASE = 0.7

SIDE_MAX = 0.15
HEIGHT_MAX = 0.10
DIRECTION_MAX = 0.10
WEIGHT_MAX = 0.20
RAW_TOTAL = (NAME_EXACT + TOPO_MAX + SIDE_MAX + HEIGHT_MAX
             + DIRECTION_MAX + WEIGHT_MAX)  # 1.20

EDIT_MIN_RATIO = 0.60      # 编辑距离低于此值不给分
CONFIDENCE_THRESHOLD = 0.55
MIN_CANDIDATE_SCORE = 0.35
SPARE_CANDIDATE_SCORE = 0.15  # 兜底候选下限（仅用于回溯未选中时照填）
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
# 中心骨的高度序约束（下侧字段的骨必须低于上侧字段的骨）。
#
# 只约束**确实是链式关系**的字段：上半身 → 上半身2 → 首 → 頭。
#
# 注意：下半身与上半身在 MMD 里是**兄弟**（都挂在腰下），
# 不是父子，缩放骨的位置可能让「下半身」比「上半身」还低
# （实测 DNF 的 GDP Pelvis Scl 就低于 G TorsoBase），
# 故不能拿来做高度序约束，否则会误杀正确候选。
CENTER_HEIGHT_CHAINS = (
    ("upper_body_bone", "upper_body2_bone"),
    ("upper_body2_bone", "neck_bone"),
    ("neck_bone", "head_bone"),
)

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


def _finger_joint_pairs():
    """同一根手指内任意两节的父子对：近端节必须是远端节的祖先。

    这是**所有**人形手都成立的解剖约束，与命名、骨架风格无关：
    一根手指的骨架必然是 hand → 指根 → 中节 → 末节的单链。
    没有这条约束时，名称兜底会把同一字段的三节填到三条不同链上
    （实测：几何形态不规范的 4 指骨架里，拇指 0/1/2 节分别落在
    Finger0/Finger2/Finger3 三条链上，成了「拼凑手指」）。

    取**所有**配对而非仅相邻配对：祖先关系可传递，约束等价；而当中间
    某节没填上时（如 pinky 只有 1、3 节），相邻配对会失效，全配对仍能
    拦住「1 节在 A 链、3 节在 B 链」的跨链错配。

    按字段名的节号自动分组，不假定指头数量，也不假定每指节数。
    """
    groups = {}
    for field in FINGER_FIELDS:
        side, finger, joint = field.split("_")
        groups.setdefault((side, finger), []).append(int(joint))
    pairs = []
    for (side, finger), joints in groups.items():
        joints.sort()
        for i, lo in enumerate(joints):
            for hi in joints[i + 1:]:
                pairs.append((f"{side}_{finger}_{lo}", f"{side}_{finger}_{hi}"))
    return pairs


CHAIN_PAIRS.extend(_finger_joint_pairs())
_FINGER_FIELD_SET = frozenset(FINGER_FIELDS)


def _build_chain_index():
    """字段 -> ((作为哪一侧, 对端字段), ...)，供 chain_ok 快速查询。"""
    index = {}
    for parent_field, child_field in CHAIN_PAIRS:
        index.setdefault(parent_field, []).append((True, child_field))
        index.setdefault(child_field, []).append((False, parent_field))
    return index


_CHAIN_INDEX = _build_chain_index()

# 字段优先级：能靠 _post_complete 拓扑推导的辅助骨是低优先级，冲突时
# 让位给必须独立匹配的真实骨。低优先级仅限 MMD 特有的推导骨——上半身
# 2~5 与胸親父级；四肢/頭/腰虽然在链里有父子关系，但都有独立骨骼，
# 仍需独立匹配。只影响回溯目标函数，不改变候选打分与阈值；排序仍按
# 分数优先，避免低分控制骨抢占主链骨（见 testmiku 修复）。
AUTO_COMPLETE_FIELDS = frozenset(
    f"upper_body{i}_bone" for i in (2, 3, 4, 5)
) | {"breast_parent_bone"}

# 不参与自动匹配的字段：完全由主链拓扑推导得出，不进回溯、不占候选骨。
#
# 上半身2~5 是 MMD 在「上半身」与「首」之间插入的过渡骨，多数骨架
# 没有对应骨骼；少数有（如 Gley 的 Spine3）但命名千差万别。让它们
# 参与回溯会抢走真实骨——实测 upper_body4 曾抢走「左肩」，
# 导致整条手臂链崩掉。改为只走推导：从 neck 沿父链回溯到 upper_body
# 之间的中间骨依次填入。
NO_AUTO_MATCH_FIELDS = frozenset(
    f"upper_body{i}_bone" for i in (2, 3, 4, 5)
)
PRIORITY_BONUS_MUST_MATCH = 0.15   # 无法补全的字段：保留价值奖励


def field_priority(field):
    """字段优先级：2=必须独立匹配（高），1=可拓扑补全（低）。"""
    return 1 if field in AUTO_COMPLETE_FIELDS else 2


# 核心骨（MMD 变形必需的面板标签带 * 号）：上半身、首、頭、肩、腕、
# ひじ、手首、足、ひざ、足首。
#
# 这些骨在 MMD 里是标准骨骼，缺了会影响变形；同层竞争时它们应优先
# 拿到候选骨。反之「操作中心 / 全ての親 / センター / グルーブ / 腰 /
# 下半身 / 目 / 足先EX」是扩展骨骼，可让位。
CORE_BONE_FIELDS = frozenset((
    "upper_body_bone", "neck_bone", "head_bone",
    "left_shoulder_bone", "right_shoulder_bone",
    "left_upper_arm_bone", "right_upper_arm_bone",
    "left_lower_arm_bone", "right_lower_arm_bone",
    "left_hand_bone", "right_hand_bone",
    "left_thigh_bone", "right_thigh_bone",
    "left_calf_bone", "right_calf_bone",
    "left_foot_bone", "right_foot_bone",
))


def is_core_bone(field):
    """是否 MMD 必需的核心骨（面板标签带 *）。"""
    return field in CORE_BONE_FIELDS


# 优先级分档（数值小的先处理、先占候选骨）：
#   0 核心骨     —— 面板带 * 的 MMD 必需骨，缺了影响变形
#   1 第二档     —— 下半身：躯干主体，比其它扩展骨重要
#   2 扩展骨     —— 操作中心 / 全ての親 / センター / グルーブ / 腰 /
#                    目 / 足先EX：能填就填，可让位
PRIORITY_TIER_CORE = 0
PRIORITY_TIER_SECOND = 1
PRIORITY_TIER_EXTEND = 2

# 第二档字段：下半身
SECOND_TIER_FIELDS = frozenset(("lower_body_bone",))


def priority_tier(field):
    """字段的优先级档位。"""
    if is_core_bone(field):
        return PRIORITY_TIER_CORE
    if field in SECOND_TIER_FIELDS:
        return PRIORITY_TIER_SECOND
    return PRIORITY_TIER_EXTEND


# 求解顺序：按解剖层级「从中心到末端」推进。
# 用户 2026-11-27 提出的顺序——先中心骨骼，再上肢，然后手掌、手指，
# 再下肢，最后脚。
#
# 为什么按这个顺序而不是「候选分最高优先」：
#   骨骼归属有明确的解剖层级，末端骨（手指、脚趾）数量多、长得像，
#   若让它们先挑骨，会抢走本该属于上肢/下肢的骨头。改成从中心向外
#   推进后：中心骨先定 → 上肢拿走臂骨 → 手掌手指只剩手指骨可用 →
#   下肢 → 脚趾，天然避免跨层级抢骨。
SOLVE_STAGE_ORDER = (
    "center",   # 中心骨骼：操作中心、全ての親、センター、グルーブ、腰
    "torso",    # 躯干：下半身、上半身、首、頭、左右胸
    "arm",      # 上肢：肩 → 腕 → 肘
    "hand",     # 手：手首 → 手指根部
    "fingertip",  # 手指：由根部向末端逐节推算
    "leg",      # 下肢：大腿 → 小腿
    "foot",     # 脚：足首 → 足趾
    "derived",  # 可拓扑推导的辅助骨：上半身2~5、胸親父级
)

# 各层级的字段归类
_SOLVE_STAGE_FIELDS = {
    "center": ("all_parents_bone", "center_bone", "groove_bone",
               "control_center_bone", "hip_bone"),
    "torso": ("lower_body_bone", "neck_bone", "head_bone",
              "breast_parent_bone",
              "left_chest_bone", "right_chest_bone"),
    "arm": ("left_shoulder_bone", "right_shoulder_bone",
            "left_upper_arm_bone", "right_upper_arm_bone",
            "left_lower_arm_bone", "right_lower_arm_bone"),
    "hand": ("left_hand_bone", "right_hand_bone"),
    "leg": ("left_thigh_bone", "right_thigh_bone",
            "left_calf_bone", "right_calf_bone"),
    "foot": ("left_foot_bone", "right_foot_bone",
             "left_toe_bone", "right_toe_bone"),
}


def finger_segment(field):
    """手指字段的节序号；拇指从 0 起，其余手指从 1 起。非手指返回 None。"""
    match = re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_(\d)$", field)
    if not match:
        return None
    return int(match.group(3))


# 中心骨内部的解剖顺序：自下而上一条链，父字段先于子字段处理，
# 这样高度序约束（chain_ok）在子字段判定时父字段已赋值。
CENTER_BONE_ORDER = (
    "all_parents_bone", "center_bone", "groove_bone", "hip_bone",
    "lower_body_bone", "upper_body_bone", "upper_body2_bone",
    "upper_body3_bone", "upper_body4_bone", "upper_body5_bone",
    "neck_bone", "head_bone",
    "left_chest_bone", "right_chest_bone",
)


def center_bone_rank(field):
    """中心骨链内的序号，数值小的先处理；不在链上的返回大值。"""
    try:
        return CENTER_BONE_ORDER.index(field)
    except ValueError:
        return len(CENTER_BONE_ORDER)


def solve_stage(field):
    """字段所属的求解层级；不在表中的按就近归类。"""
    if field in FINGER_FIELDS:
        # 手指统一归到 fingertip 层，层内再按节号从根部向末端推算
        return "fingertip"
    for stage, fields in _SOLVE_STAGE_FIELDS.items():
        if field in fields:
            return stage
    # 上半身2~5 与胸親父级是可拓扑推导的辅助骨：它们在标准骨架里
    # 没有独立骨骼，靠主链推导。放最后处理，避免抢走真实骨
    # （早期版本里 upper_body4 抢走了「左肩」，导致整条手臂链崩掉）。
    if field in AUTO_COMPLETE_FIELDS:
        return "derived"
    if field.startswith("upper_body"):
        return "torso"
    return "torso"


def solve_stage_rank(field):
    """求解层级序号，数值小的先处理。"""
    try:
        return SOLVE_STAGE_ORDER.index(solve_stage(field))
    except ValueError:
        return len(SOLVE_STAGE_ORDER)


CORE_BONE_BONUS = 0.12        # 核心骨（MMD 必需，面板带 *）的目标加成
SECOND_TIER_BONUS = 0.05      # 第二档（下半身）的目标加成
# 中心骨偏离身体中轴的容差（相对身高）。
#
# 实测三个模型的真实脊柱骨偏移只有 0.01~0.04%（170cm 身高约 0.2~0.7mm），
# 而最近的左右侧骨是肩骨 3.27%、髋骨 4.85%。原先取 3% 等于把阈值压在
# 肩骨边上（只差 0.27 个百分点），换个肩窄些的模型就会放过肩骨。
# 收到 1%：仍比真实脊柱骨宽 25 倍（容得下姿态化/不对称骨架的偏移），
# 又离肩骨有 3 倍余量。
MIDLINE_TOLERANCE = 0.01


def field_bonus(field):
    """回溯目标函数里的字段奖励。

    两层含义：
      - 可推导字段（upper_body2~5、胸親）不给奖励，让位给真实骨；
      - 核心骨（面板带 * 的 MMD 必需骨）额外加成——缺了会影响变形，
        扩展骨骼（センター/グルーブ/腰 等）可以让位。
    """
    bonus = PRIORITY_BONUS_MUST_MATCH if field_priority(field) == 2 else 0.0
    tier = priority_tier(field)
    if tier == PRIORITY_TIER_CORE:
        bonus += CORE_BONE_BONUS
    elif tier == PRIORITY_TIER_SECOND:
        bonus += SECOND_TIER_BONUS
    return bonus

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

# 强语义别名：命中它基本就确定是该字段，给精确档（0.40）。
#
# 区别于普通别名：普通别名是「包含即算」的泛化词（如 "arm"——小臂
# forearm 也含 arm），只能给包含档 0.25；强语义别名带限定词
# （upperarm / forearm），命中即确定。
#
# 不做这个区分时，DNF 的 "G UpperArm L"（规范化后 gupperarml，
# 与别名 upperarm 不全等）只能拿 0.25，输给拓扑分更高的缩放骨，
# 结果腕* 拿到 ForeArm（偏成小臂）、ひじ* 拿到 Elbow。
STRONG_ALIAS_TOKENS = {
    "head_bone": ("head",),
    "neck_bone": ("neck",),
    "upper_body_bone": ("spine", "torso", "upperbody"),
    "upper_body2_bone": ("chest",),   # upperchest 归 upper_body3（见 AMBIGUOUS_PRIMARY）
    "hip_bone": ("hips", "pelvis"),
    "lower_body_bone": ("lowerbody",),
    "left_shoulder_bone": ("shoulder",),
    "right_shoulder_bone": ("shoulder",),
    "left_upper_arm_bone": ("upperarm",),
    "right_upper_arm_bone": ("upperarm",),
    "left_lower_arm_bone": ("forearm", "lowerarm"),
    "right_lower_arm_bone": ("forearm", "lowerarm"),
    "left_hand_bone": ("hand", "wrist"),
    "right_hand_bone": ("hand", "wrist"),
    "left_thigh_bone": ("thigh", "upleg", "upperleg"),
    "right_thigh_bone": ("thigh", "upleg", "upperleg"),
    "left_calf_bone": ("calf", "shin", "lowerleg"),
    "right_calf_bone": ("calf", "shin", "lowerleg"),
    "left_foot_bone": ("foot", "ankle"),
    "right_foot_bone": ("foot", "ankle"),
    "left_toe_bone": ("toe",),
    "right_toe_bone": ("toe",),
    "left_eye_bone": ("eye",),
    "right_eye_bone": ("eye",),
    "left_chest_bone": ("breast", "bust"),
    "right_chest_bone": ("breast", "bust"),
    "groove_bone": ("groove",),
}

# 链式邻居：每个环节的「上一节」与「下一节」。
# 用于父子关系判定——关系反了（把子骨当父骨）直接否决候选。
# 链上所有环节（用于「候选骨自身属于别的环节」的判定）
_CHAIN_CATEGORIES = ("shoulder", "upper_arm", "lower_arm", "hand",
                     "finger", "thigh", "calf", "foot", "toe", "torso",
                     "neck", "head")

# 躯干环节的语义别名（脊柱/胸腔一系）。上半身~上半身5、首、頭 都算
# 躯干链上的环节，用宽松的集合才能覆盖各种 rig 的命名
# （mixamorig 的 Spine1/Spine2、Gley 的 Spine3、DNF 的 G Chest）。
_TORSO_WORDS = ("spine", "torso", "upperbody", "chest")

# 各字段的链式邻居：(上一节类别, 下一节类别)。
# 覆盖上肢（肩→上臂→小臂→手→指）、下肢（大腿→小腿→脚→趾）、
# 躯干（上半身→首→頭）。
FIELD_CHAIN_NEIGHBORS = {
    "shoulder_bone": (None, "upper_arm"),
    "upper_arm_bone": ("shoulder", "lower_arm"),
    "lower_arm_bone": ("upper_arm", "hand"),
    "hand_bone": ("lower_arm", "finger"),
    "thigh_bone": (None, "calf"),
    "calf_bone": ("thigh", "foot"),
    "foot_bone": ("calf", "toe"),
    "upper_body_bone": (None, "torso"),
    "lower_body_bone": (None, "thigh"),
    "neck_bone": ("torso", "head"),
    "head_bone": ("neck", None),
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
# 纯函数结果缓存。候选生成阶段这几个函数被调用数十万次，而输入
# （骨名）的取值空间只有骨数那么多——同一根骨名会被 64 个字段各问
# 一遍，每次都重跑正则拆分/归一化。实测 Tifa_rig（1792 骨）：
# _tokens 87 万次、re.sub 296 万次，占 solve 总耗时约 20%。
_NORM_CACHE = {}
_TOKENS_CACHE = {}
_SUPPORT_BONE_CACHE = {}
_CATEGORY_MATCH_CACHE = {}
_RATIO_CACHE = {}
# 缓存的输入是骨名，跨模型会累加；超限整体清空即可，不清也不会算错。
_CACHE_LIMIT = 40000


def _trim_caches():
    """缓存规模过大时清空，避免长会话里跨模型无限增长。"""
    if len(_NORM_CACHE) <= _CACHE_LIMIT:
        return
    for cache in (_NORM_CACHE, _TOKENS_CACHE, _SUPPORT_BONE_CACHE,
                  _CATEGORY_MATCH_CACHE, _RATIO_CACHE,
                  _NAME_SCORE_CACHE):
        cache.clear()


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
    cached = _NORM_CACHE.get(name)
    if cached is not None:
        return cached
    n = name.lower()
    n = n.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    n = re.sub(r"^(mixamorig|bip0?0?1|vrm|armature)[:._ -]*", "", n)
    n = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", "", n)
    _NORM_CACHE[name] = n
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
    """拆词结果。返回 tuple——可缓存，调用方只读不改性。

    切分规则与列表版完全一致（驼峰 / 字母数字 / 分隔符），
    仅返回类型从 list 换成 tuple 以便进缓存。
    """
    cached = _TOKENS_CACHE.get(name)
    if cached is not None:
        return cached
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"([_.:\- ])+", " ", s)
    result = tuple(t.lower() for t in s.split() if t)
    _TOKENS_CACHE[name] = result
    return result


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

    配对统一走 _named_side_pairs——它支持前缀（LeftArm）、中间
    （Bip001-L-Finger0）、后缀（arm.L / arm_L）三类写法。这里曾有一份
    只认前缀与后缀的独立解析，中间式骨架（3ds Max Biped 系导出）配对
    为空，于是回退到 X 轴：实测 Vipe 的第一人称骨架左右轴其实是 Y，
    侧向分为 0，左肩拿到右锁骨、中心骨整片空掉。

    找不到配对时回退：高度轴不是 X 就用 X，否则用 Z。
    """
    pairs = [(features[left_name].head, features[right_name].head)
             for left_name, right_name in _named_side_pairs(
                 features, include_middle=True)
             if left_name in features and right_name in features]
    if not pairs:
        return 0 if up_axis != 0 else 2
    differences = [sum(abs(l[i] - r[i]) for l, r in pairs) / len(pairs)
                   for i in range(3)]
    return max(range(3), key=lambda i: differences[i])


# 左右侧别前缀规则：(正则, 左侧标记, 右侧标记, 是否大小写敏感)
# 支持前缀式（左腕 / left_arm / l_forearm / LeftArm）与后缀式（arm.L）。
_SIDE_PREFIX_PATTERNS = (
    (re.compile(r"^(left|right)[._ -]"), "left", "right", False),
    (re.compile(r"^([lr])[._ -]"), "l", "r", False),
    (re.compile(r"^([左右])"), "左", "右", False),
    # 驼峰无分隔符：LeftArm / RightArm（大小写不敏感匹配，
    # 但用原始名切出 key 以保留驼峰边界）
    (re.compile(r"^(left|right)(?=[A-Z])", re.I), "left", "right", True),
)


def _named_side_pairs(features, include_middle=False):
    """找出命名成对的左右骨，返回 [(左骨名, 右骨名), ...]。

    识别 left_/right_、l_/r_、.L/.R、左/右、LeftArm 等常见命名。

    include_middle=True 时额外认中间式（Bip001-L-Finger0）。只有轴判定
    用它：Biped 系骨架全篇是中间式，不认就配不出对；而镜像兜底不用它，
    是因为中间式的键要重组前缀与后缀，与后缀式的键可能撞车，改变兜底
    选骨（实测 TP 骨架填充从 58 掉到 43）。
    """
    left = {}
    right = {}
    for name in features:
        lower = name.lower()
        matched = False
        for pattern, left_token, right_token, case_sensitive in _SIDE_PREFIX_PATTERNS:
            match = pattern.match(name if case_sensitive else lower)
            if not match:
                continue
            token = match.group(1)
            key = name[match.end():] if case_sensitive else lower[match.end():]
            key = key.lower()
            if token.lower() == left_token:
                left[key] = name
            else:
                right[key] = name
            matched = True
            break
        if matched:
            continue
        if include_middle:
            # 中间式：Bip001-L-Finger0 / arm_L_01 / arm.L.001
            match = re.match(r"^(.+?)[._: -]([lr])[._: -](.+)$", lower)
            if match:
                key = f"{match.group(1)}~{match.group(3)}"
                (left if match.group(2) == "l" else right)[key] = name
                continue
        # 后缀式：arm.L / arm_L / G Clavicle L。用独立前缀标记，避免与
        # 前缀式的同名键（如 LeftArm 与 arm.L 的键都是 "arm"）互相覆盖。
        # 空格分隔是 3ds Max 系骨架的常态（DNF 全篇 G Thigh L / G
        # Clavicle R），不认它整副骨架配不出一对：中轴会回退到「侧向
        # 跨度中点」，被单侧武器/披风拉偏——暗刃实测偏 0.109（5.5%
        # 身高），head / neck / upper_body 三个核心骨全被挤出中轴容差。
        tail = re.search(r"[ ._\-]([lr])$", lower)
        if tail:
            key = "~" + lower[:tail.start()]
            (left if tail.group(1) == "l" else right)[key] = name
    return [(left[key], right[key]) for key in left if key in right]


# 中心骨字段：必须落在脊柱主链上
SPINE_BONE_FIELDS = frozenset((
    "all_parents_bone", "center_bone", "groove_bone", "hip_bone",
    "lower_body_bone", "upper_body_bone", "upper_body2_bone",
    "upper_body3_bone", "upper_body4_bone", "upper_body5_bone",
    "neck_bone", "head_bone",
))


def detect_spine_chain(features, up_axis=2):
    """找出脊柱主链：从骨架根骨出发，沿「最高的子骨」连续向下。

    每层有多个子骨时（躯干分出四肢），脊柱是那个继续向上的——
    子树顶端最高的那个。这样得到的是脊柱而非四肢分支。

    比「离中轴多远」可靠：髋关节距中轴约身高的 5%，纯距离阈值
    很难卡准；而脊柱链是拓扑事实。

    两条补充判据（都是真实模型踩出来的）：
      - **多根骨架**（xps 转出的常见形态：一根空的 Body 占位骨 + 一根
        真正的 G Root）只从第一个根走会走进空占位骨，整条链只剩它
        自己，中心骨字段因此全空。改为遍历全部根，取子树最深的那条。
      - **悬空道具骨**（HIT2 手里飘在头顶上方的 Orb_BONE，up=178 而
        躯干顶只有 154）自身最高，但它下面没有任何延伸，选它链就断。
        所以先排除**不能继续延伸**的叶子，必要时按 1% 身高内的高度差
        用子树深度决胜——骨盆层选「脊柱」而不是「裙摆」，差的正是
        这 0.09。
    """
    if not features:
        return set()
    children = {}
    roots = []
    for name, feature in features.items():
        if feature.parent:
            children.setdefault(feature.parent, []).append(name)
        else:
            roots.append(name)
    if not roots:
        return set()

    _cache = {}

    def subtree_info(name):
        """(子树最高处的归一化高度, 子树最深深度)。"""
        if name in _cache:
            return _cache[name]
        node = features[name]
        top = node.z_pct
        deepest = node.depth
        stack = list(children.get(name, []))
        seen = {name}
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            child = features.get(current)
            if child is None:
                continue
            top = max(top, child.z_pct)
            deepest = max(deepest, child.depth)
            stack.extend(children.get(current, []))
        _cache[name] = (top, deepest)
        return _cache[name]

    # 从「子树最深」的根骨出发：多根骨架里，真正的身体根能一直延伸到
    # 末梢，占位空骨下面什么都没有。平手时取最低的（身体根通常贴地）。
    current = max(roots, key=lambda n: (subtree_info(n)[1],
                                        -features[n].head[up_axis]))
    chain = set()
    seen = set()
    while current and current not in seen:
        seen.add(current)
        chain.add(current)
        kids = children.get(current, [])
        if not kids:
            break
        # 先排除叶子：悬空的法球/武器挂点自身可能最高，但一走就断。
        extendable = [k for k in kids
                      if features[k].child_count > 0]
        pool = extendable or kids
        # 1% 身高内的高度差视为并列，用子树深度决胜（脊柱比裙摆长）。
        # 仍平手时按骨名排序取第一个——Blender 内嵌 Python 的集合遍历
        # 顺序每进程随机，排序键必须完全确定。
        best = max(subtree_info(k)[0] for k in pool)
        near = [k for k in pool if best - subtree_info(k)[0] <= 0.01]
        near.sort(key=lambda k: (-subtree_info(k)[1], k))
        current = near[0]
    return chain


def detect_midline(features, side_axis=None):
    """估计身体中轴在侧轴上的位置。

    用命名成对的左右骨的中点求均值——比「侧向跨度的中点」稳：
    不对称骨架（举起一只手、侧身）里跨度中点会明显偏移。
    没有配对骨时回退到侧向跨度的中点。
    """
    if not features:
        return 0.0
    if side_axis is None:
        side_axis = 0
    pairs = _named_side_pairs(features)
    if pairs:
        midpoints = []
        for left_name, right_name in pairs:
            a = features[left_name].head[side_axis]
            b = features[right_name].head[side_axis]
            midpoints.append((a + b) * 0.5)
        if midpoints:
            return sum(midpoints) / len(midpoints)
    values = sorted(feature.head[side_axis] for feature in features.values())
    return (values[0] + values[-1]) * 0.5 if values else 0.0


def detect_symmetry(features, span, side_axis=None, up_axis=2):
    """判断骨架本身是否左右对称，返回 (是否对称, 最大配对误差)。

    非对称骨架（举单手、侧身、左右骨骼数量不同）不能套用镜像约束：
    此时左右对应骨本就不该对称，用镜像误差否决候选会错杀正确配对。

    判据：统计命名成对的左右骨的镜像误差，只要**存在一对**超过
    镜像容差，就判定骨架非对称——只要有一处明显不对称，整个骨架
    就不能用镜像硬约束。中位数会掩盖这种局部不对称，故不用。
    """
    if not features or span <= 0:
        return True, 0.0
    pairs = _named_side_pairs(features)
    if len(pairs) < 3:
        # 配对太少，无法判定；保守起见不启用镜像约束
        return False, 0.0
    if side_axis is None:
        side_axis = 0
    worst = 0.0
    for left_name, right_name in pairs:
        a = features[left_name].head
        b = features[right_name].head
        error = abs(a[side_axis] + b[side_axis])
        for axis in range(3):
            if axis != side_axis:
                error += 0.5 * abs(a[axis] - b[axis])
        worst = max(worst, error / span)
    return worst <= MIRROR_TOLERANCE, worst


# ------------------------------------------------------- 手指几何身份推断

# 手指推断的几何参数
FINGER_CHAIN_MIN = 2         # 一根手指至少 2 节骨才成链
# 「该骨下挂的指链数」上限。用途只有一个：排除明显不是手的部位
# （眼球挂十几条、马尾挂几十条小骨链）。它**不是**指头数量的上限，
# 也不是 MMD 类别数的上限——骨架上挂几条链由几何决定。
# 取值宽松（人手最多 5 指，留出分叉展开的余量），少指/多指模型都不受影响。
MAX_PALM_CHAINS = 8
FINGER_LEN_RATIO = 0.060     # 单节指骨长度 / 身高 的上限
THUMB_ANGLE_DEG = 25.0       # 拇指与四指平均方向的最小夹角
FINGER_PARALLEL_DEG = 40.0   # 判定「彼此平行」的夹角容差

# MMD 的手指类别：拇指 + 食指/中指/无名指/小指，共 5 类。
# 这是**映射目标**，不是对骨架的假定：
#   - 骨架手指数 ≤ 5：全部映射，从拇指侧起依次对应
#     index → middle → ring → pinky，不足的自然留空；
#   - 骨架手指数 > 5：取离拇指最近的 5 类，多余的舍去（异常骨架）。
FINGER_ORDER = ("index", "middle", "ring", "pinky")
MMD_FINGER_COUNT = len(FINGER_ORDER) + 1   # 含拇指，共 5 类


def _collect_finger_chains(features, palm, max_len):
    """收集挂在这根手掌骨下的细长骨链（每条链从第 1 节到末端）。

    必须支持**分叉**：有些骨架的手掌不是直接挂五根手指，而是先经过
    一块「掌骨」（如握拳时的 Fist），由它再分出两根手指
    （D 指、E 指都挂在 Fist 下）。若只沿单一子链走，会丢掉其中一根。

    做法：从手掌的直接子骨出发，若该子骨自身还挂着多根细长骨，
    则它下面是分叉点，每个分支各成一条链。
    """
    chains = []

    def walk(node_name, chain):
        """沿当前骨向下走，收集所有末端路径。

        分叉点（挂着多根细长骨的骨，如握拳掌骨 Fist）本身不是手指节，
        它下面的每个分支各成一条链，故不把分叉点加进链里。
        """
        node = features.get(node_name)
        if node is None:
            return
        children = [c for c in node.children
                    if c in features and features[c].length <= max_len]
        if not children:
            if len(chain) >= FINGER_CHAIN_MIN:
                chains.append(chain)
            return
        if len(children) > 1:
            # 分叉点：不进链，从各分支继续
            for child in children:
                walk(child, [child])
            return
        walk(children[0], chain + [children[0]])

    for child_name in palm.children:
        child = features.get(child_name)
        if child is None or child.length > max_len:
            continue
        walk(child_name, [child_name])

    # 根骨长度过滤：与同手掌最长链的根骨长度可比才算指骨。
    # 小指天然比拇指短（Gley 实测 0.47），故阈值取 0.35；
    # 烘焙辅助链、挂点这类极短小骨（Gley 的 Bake 链 0.14）会被排除。
    if len(chains) >= 2:
        longest = max(features[chain[0]].length for chain in chains)
        if longest > 1e-9:
            chains = [chain for chain in chains
                      if features[chain[0]].length >= longest * 0.35]
    return chains


def _find_palm_bones(features, span):
    """找出手掌骨：拥有多条「指状」细长骨子链的骨。

    判据（不依赖命名）：
      - 直接挂着 >= 3 条细长骨链（子骨自身不长、且往下还有细长骨节）；
      - 这些子链的根骨彼此靠近（聚在手掌末端的一小片区域），
        以排除头发/布料/武器挂点这类同样挂着多条细链但根部分散的辅助骨；
      - 手掌位于身体末端：其自身在骨架中的深度很深（手臂/腿的末端），
        以排除胸腔、头部、骨盆这些位于身体中段的挂点。

    这样手指链天然以手掌的子骨为起点，手掌本身不会被算进手指链，
    节序号也不会错位。
    """
    if span <= 0:
        return set()
    max_len = FINGER_LEN_RATIO * span
    max_depth = max((f.depth for f in features.values()), default=0)
    if max_depth <= 0:
        return set()
    # 脊柱链只有在真的走到头顶时才可信——半身/单手骨架（测试用的合成
    # 骨架、只有上半身的扫描件）里它会被臂骨带偏，此时不启用下面的
    # 「挂在脊柱上的不是手」过滤。
    spine = detect_spine_chain(features)
    if max((features[n].z_pct for n in spine), default=0.0) < 0.8:
        spine = set()
    palms = set()
    for name, feature in features.items():
        chains = _collect_finger_chains(features, feature, max_len)
        # 链数下限：至少要有 3 条才谈得上手指。
        # 上限只用于排除「明显不是手」（眼球、马尾挂几十条链），
        # 不作为指头数量的假定。
        if len(chains) < 3 or len(chains) > MAX_PALM_CHAINS:
            continue
        # 手掌在骨架末端：自身深度够大。比例取 0.30——xps 转出的骨架
        # 常多一根占位根骨（DNF 本体里 02A Body 与 G Root 并列为根），
        # 全身深度各 +1，手掌的比例就从 0.36 掉到 0.33，原来的 0.35
        # 会把手掌整个刷掉，连带躯干字段全空。
        if feature.depth < max_depth * 0.30:
            continue
        # 分叉必须发生在**手掌这一层**：手直接挂着 3 根以上细长骨，
        # 而前臂只挂手掌一根（它的 6 条链是穿过手掌数出来的），两者
        # 深度只差一层、方向完全一致，只有这条能分开。DNF 的拇指/无名
        # 指另挂在 Fist 下，手掌仍直挂 A/B/C 三根，故门槛取 3 不取 5。
        direct = [c for c in feature.children
                  if c in features and features[c].length <= max_len]
        if len(direct) < 3:
            continue
        roots = [features[chain[0]] for chain in chains]
        # 根部聚集度：各链根都应靠近手掌骨（手掌末端的同一小片区域），
        # 以排除头发/布料/武器挂点这类根部分散的辅助骨。
        # 手指张开时根距可达手掌长的数倍，故容差放宽到 4 倍手掌长。
        reach = max(feature.length, max_len * 0.5) * 4.0
        spread = 0.0
        for i in range(len(roots)):
            for j in range(i + 1, len(roots)):
                distance = _vlen(_vsub(roots[i].head, roots[j].head))
                spread = max(spread, distance)
        if spread > reach:
            continue
        # 方向一致性：真手指里除拇指外其余近乎平行，且存在唯一偏离者
        # （拇指）。头发、眼球这类挂点的子链方向杂乱，据此排除。
        # 这里用「能带出最多平行链的方向 + 偏离者数量」来判，
        # 不依赖链的数量。
        directions = []
        for chain in chains:
            direction = _chain_head_dir(features, chain)
            if direction is not None:
                directions.append(direction)
        if len(directions) < 3:
            continue
        best_parallel = 0
        for reference in directions:
            aligned = sum(1 for d in directions
                          if _vdot(d, reference) >= math.cos(
                              math.radians(FINGER_PARALLEL_DEG)))
            best_parallel = max(best_parallel, aligned)
        if best_parallel < 2:
            continue  # 连两条都平行不了，方向杂乱，不是手
        # 手掌的父骨是前臂，不在脊柱上。帽子、胸腔装饰、裙摆这些
        # 「挂几条细链又聚在一小片」的部位全挂在脊柱链的骨（头、胸、
        # 骨盆）下面——漫游实测 GU Hat 8 条帽穗挂 Head 下、GDP Chest
        # Scl 15 条胸饰挂 Chest 下，它们通过前面所有几何判据，会把
        # 手指推断带偏到衣领骨上。
        if feature.parent in spine:
            continue
        palms.add(name)
    return palms


def _chain_head_dir(features, chain):
    """链条从根到梢的方向（用根骨与末骨 head 之差）。"""
    root = features.get(chain[0])
    tip = features.get(chain[-1])
    if root is None or tip is None:
        return None
    direction = _vsub(tip.head, root.head)
    if _vlen(direction) < 1e-9:
        return None
    return _vunit(direction)


def infer_finger_roles(features, span, side_axis=None, up_axis=2):
    """按物理位置推断手指身份，返回 {骨名: (手指类型, 节序号)}。

    解剖学依据（不依赖名称）：
      - 拇指独立向掌侧偏出，与其余四指方向成明显夹角；
      - 拇指指向偏离「模型前方轴」，而四指沿手掌法线伸展；
      - 四指（食指→小指）沿手掌横向依次排列，彼此近乎平行；
      - 食指紧邻拇指，其余三指依次远离。

    分组方式：按手掌骨聚合——同一根手掌骨挂着的细长骨链就是一只手。
    这样头发、眼球、武器挂点等杂链不会混进手指判定。

    返回的节序号：拇指从 0 起（thumb_0 掌骨节），其余手指从 1 起。
    """
    if not features or span <= 0:
        return {}

    if side_axis is None:
        side_axis = 0
    # 前方轴：除高度轴与左右轴之外的第三个轴
    front_axis = next((i for i in range(3)
                       if i not in (up_axis, side_axis)), None)

    # 按手掌骨分组收集手指链
    palms = _find_palm_bones(features, span)
    if not palms:
        return {}, {}, {}
    max_len = FINGER_LEN_RATIO * span
    by_palm = {}
    for palm_name in palms:
        palm = features.get(palm_name)
        if palm is None:
            continue
        chains = _collect_finger_chains(features, palm, max_len)
        if chains:
            by_palm[palm_name] = chains

    result = {}
    sides = {}
    domains = {}
    # 按键名排序遍历：_find_palm_bones 返回的是 set，而 Blender 内嵌
    # Python 的字符串哈希每进程随机（PYTHONHASHSEED 不生效），直接遍历
    # 会让同侧多根候选手掌骨的覆盖顺序随机，进而使结果不可复现
    # （实测 DNF 同一模型在不同进程给出 54/58 两种解）。
    for palm_name in sorted(by_palm):
        chains = by_palm[palm_name]
        # 不限指头数量：由 _infer_one_hand 按几何自动判定能填几根，
        # 这里只挡掉明显过少（连三根都不到，不可能是手）。
        if len(chains) < 3:
            continue
        assigned = _infer_one_hand(features, chains, side_axis, front_axis)
        if not assigned:
            continue
        # 左右侧别由手掌骨的位置决定（side_axis 正坐标为左，与字段约定
        # 一致），不能从骨名猜——骨名的侧别可能在前缀、中间或后缀，
        # 各家 rig 写法不一（DNF 是 `GD Fng A1 L`、Gley 是
        # `Bip001-L-Finger0`、还有 `LeftArm` / `腕.L` 等）。
        palm = features.get(palm_name)
        side = None
        if palm is not None:
            side = "left" if palm.head[side_axis] >= 0 else "right"
        for bone_name in assigned:
            result[bone_name] = assigned[bone_name]
            if side:
                sides[bone_name] = side
        if side:
            # 上肢域：手掌骨及其全部子孙骨。手指骨必然长在这条分支上，
            # 域外的骨（躯干、腿、头发、眼球）一律不能当手指候选。
            # 同侧可能识别出多根「手掌状」骨（如 DNF 的 GD Hand Scl L
            # 与 GD Fist L），域取并集而非后写覆盖，否则填哪一根会
            # 取决于遍历顺序。
            domains.setdefault(side, set()).update(
                _subtree_bones(features, palm_name))
    return result, sides, domains


def _compute_limb_domains(features, palm_names):
    """算出四肢域与躯干域。

    四肢域 = 手掌骨、���首骨及其全部子孙（含手指、脚趾）。
    躯干域 = 骨架里不属于四肢域的骨——躯干字段的候选不能是四肢骨，
    否则「下半身」会拿到手臂骨这种明显错误的结果。
    """
    limb = set()
    for palm_name in palm_names:
        limb |= _subtree_bones(features, palm_name)
    torso = set(features.keys()) - limb
    return limb, torso


def _compute_arm_domains(features, palm_names, span, side_axis):
    """上肢域：手掌骨自身，加上沿父链往上的手臂骨（手指链不含）。

    手指域只含手掌子树——上臂、小臂、锁骨都是手掌的**祖先**，不在其中，
    所以手臂字段没有域可依。不设域时上臂会退而求其次拿到任意「同侧、
    同高度」的骨：实测蒂法把头发骨 DEF-Hair_E_05.L 填进上臂（0.385，
    名称证据为零），镜把头发物理骨填进小腿和手。

    也不能一路走到根：那样躯干、头发、头饰全都成了合法候选。截断条件
    取「骨根贴近身体中轴」——锁骨的根就在中轴附近，那里正是上肢与
    躯干的交界，对任意命名体系都成立。

    Returns:
        dict: {"left"/"right": 骨名集合}；识别不出手掌时为空 dict
    """
    domains = {}
    tolerance = max(span * MIDLINE_TOLERANCE, 1e-6)
    for palm_name in sorted(palm_names):
        palm = features.get(palm_name)
        if palm is None:
            continue
        side = "left" if palm.head[side_axis] >= 0 else "right"
        domain = domains.setdefault(side, set())
        # 只收手掌骨自身与它的祖先链，**不收**手掌子树：子树是手指与
        # 掌骨附属骨（DNF 的 GDU Bake L 5、蒂法的 DEF-Knuckle_Root.L），
        # 收进来会让「肩」「上臂」拿到手掌骨，整条链反向断裂。
        domain.add(palm_name)
        node = palm_name
        while True:
            current = features.get(node)
            if current is None:
                break
            parent = features.get(current.parent) if current.parent else None
            if parent is None:
                break
            if abs(parent.head[side_axis]) <= tolerance:
                # 交界骨本身（锁骨/胸骨）可能就贴在中轴附近，它仍是
                # 合法的「肩」候选（DNF 的 G Clavicle L 就是这样，漏了
                # 它会让肩字段整根空掉）。收下它，但不再继续往上走，
                # 否则脊柱、胸、头都会进上肢域。
                domain.add(parent.name)
                break
            domain.add(parent.name)
            node = parent.name
    return domains


def _subtree_bones(features, root_name):
    """收集某根骨及其全部子孙骨的名称集合。"""
    result = set()
    stack = [root_name]
    while stack:
        name = stack.pop()
        if name in result:
            continue
        result.add(name)
        node = features.get(name)
        if node is None:
            continue
        stack.extend(node.children)
    return result


def _infer_one_hand(features, chains, side_axis, front_axis=None):
    """对单只手的 5 根手指链做身份推断。"""
    # 1) 计算每根链的方向
    infos = []
    for chain in chains:
        direction = _chain_head_dir(features, chain)
        root = features.get(chain[0])
        if direction is None or root is None:
            continue
        infos.append({"chain": chain, "dir": direction, "head": root.head})
    if len(infos) < 3:
        return {}

    # 2) 找其余手指的主方向：取「最大平行子集」的方向。
    #    做法：逐条链尝试当参考，收集与它近乎平行的链，取这批链方向的
    #    均值作主方向。用均值而非单条链的方向——单条链的方向会因
    #    个体差异让主方向偏移，进而把偏离者判错。
    best_dir = None
    best_parallel = -1
    for info in infos:
        group = [other for other in infos
                 if _vdot(info["dir"], other["dir"])
                 >= math.cos(math.radians(FINGER_PARALLEL_DEG))]
        if len(group) > best_parallel:
            best_parallel = len(group)
            # 均值方向（单位化）
            mean = tuple(sum(g["dir"][i] for g in group) / len(group)
                         for i in range(3))
            length = math.sqrt(sum(x * x for x in mean))
            best_dir = (mean[0] / length, mean[1] / length, mean[2] / length) \
                if length > 1e-9 else info["dir"]
    # 判据（不假定指头数量）：主方向要能带出至少 2 条平行链，
    # 否则无法区分「拇指 + 其余」的结构，直接放弃。
    if best_dir is None or best_parallel < 2:
        return {}

    # 3) 拇指 = 唯一偏离主方向的链。
    #    偏离者可能不止一根（如握拳时多指内收），此时取偏离程度最大者；
    #    若一根都不偏离（手指完全并拢），退用「偏离前方轴最大」来定——
    #    其余手指沿掌心法线伸展，拇指则明显偏向侧方
    #    （用户观察：-Y 方向的那根是大拇指）。
    def deviation(info):
        """与主方向的夹角（度）。"""
        cosine = max(-1.0, min(1.0, _vdot(info["dir"], best_dir)))
        return math.degrees(math.acos(cosine))

    thumbs = [info for info in infos
              if deviation(info) > THUMB_ANGLE_DEG]
    if not thumbs:
        if front_axis is None:
            return {}
        def front_offset(info):
            return abs(info["dir"][front_axis])
        ranked = sorted(infos, key=front_offset, reverse=True)
        if front_offset(ranked[0]) - front_offset(ranked[-1]) < 0.15:
            return {}   # 各指偏离程度接近，无法判定
        thumbs = [ranked[0]]
    # 偏离者多于一根时取偏离最大的（最可能是拇指）
    thumb = max(thumbs, key=deviation)
    others = [info for info in infos if info is not thumb]
    if not others:
        return {}

    # 4) 排其余手指：沿「垂直于主方向、且在手掌平面内」的横向轴排序。
    #    解剖学上食指紧邻拇指，拇指与小指分居手的两端。故：
    #    先用三维距离找出紧邻拇指的那根作为食指，再沿「远离拇指」的
    #    方向依次排出 中指 → 无名指 → 小指。
    spread_axis = _spread_axis([info["head"] for info in others], best_dir)
    if spread_axis is None:
        return {}

    def lateral(info):
        """在横向轴上的投影值（相对拇指）。"""
        return _vdot(_vsub(info["head"], thumb["head"]), spread_axis)

    def distance_to_thumb(info):
        return _vlen(_vsub(info["head"], thumb["head"]))

    # 紧邻拇指的一根 = 三维距离最小者，即食指
    index_info = min(others, key=distance_to_thumb)
    rest = [info for info in others if info is not index_info]
    # 其余三根沿横向轴排：与食指同侧的一侧为「远离拇指」
    index_side = 1.0 if lateral(index_info) >= 0 else -1.0
    same_side = [info for info in rest if lateral(info) * index_side >= 0]
    opposite = [info for info in rest if lateral(info) * index_side < 0]
    same_side.sort(key=lambda info: abs(lateral(info)))
    opposite.sort(key=lambda info: abs(lateral(info)))
    ordered = [index_info] + same_side + opposite
    # 骨架指头数可能多于 MMD 的四指类（异常骨架），只取离拇指最近的
    # 前 len(FINGER_ORDER) 根，多余的舍去——MMD 本身也只有这四类。
    ordered = ordered[:len(FINGER_ORDER)]

    roles = {}
    for index, info in enumerate(ordered):
        finger = FINGER_ORDER[index]
        # 四指字段从 1 起编号（index_1 是掌骨节），故链条索引 0 → 节号 1
        for chain_index, bone_name in enumerate(info["chain"]):
            roles[bone_name] = (finger, chain_index + 1)
    # 拇指字段从 0 起编号（thumb_0 是掌骨节），链条索引 0 → 节号 0
    for chain_index, bone_name in enumerate(thumb["chain"]):
        roles[bone_name] = ("thumb", chain_index)
    return roles


def _principal_axis(points):
    """求点集分布的主方向（第一主成分），返回单位向量。

    用协方差矩阵 + 幂迭代法求最大特征值对应的特征向量，无需 numpy。
    主方向即点分布方差最大的方向——四指沿此轴依次排开。
    """
    if len(points) < 2:
        return None
    center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
    cov = [[0.0] * 3 for _ in range(3)]
    for point in points:
        d = (point[0] - center[0], point[1] - center[1], point[2] - center[2])
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    # 幂迭代：取任意非零向量反复乘协方差矩阵并归一化
    vector = (1.0, 0.37, 0.11)
    for _ in range(64):
        nxt = tuple(sum(cov[i][j] * vector[j] for j in range(3))
                    for i in range(3))
        length = math.sqrt(sum(x * x for x in nxt))
        if length < 1e-12:
            return None
        nxt = (nxt[0] / length, nxt[1] / length, nxt[2] / length)
        if (abs(nxt[0] - vector[0]) < 1e-9 and abs(nxt[1] - vector[1]) < 1e-9
                and abs(nxt[2] - vector[2]) < 1e-9):
            vector = nxt
            break
        vector = nxt
    return vector


def _spread_axis(points, exclude_dir):
    """求一组点分布最宽的横向轴（尽量垂直于 exclude_dir）。

    以点集主方向为基准；若主方向与 exclude_dir 夹角过小（说明点沿
    指骨方向排布而非横向），则退回到正交基中跨度最大者。
    """
    if len(points) < 2:
        return None
    axis = _principal_axis(points)
    if axis is None:
        return None
    # 主方向需与指骨主方向基本正交，否则说明排布方向就是指骨方向
    if abs(_vdot(axis, exclude_dir)) < 0.85:
        return axis
    # 构造两个正交基
    ref = (0.0, 0.0, 1.0)
    if abs(_vdot(exclude_dir, ref)) > 0.9:
        ref = (0.0, 1.0, 0.0)
    u = _vunit(_vsub(ref, tuple(exclude_dir[i] * _vdot(ref, exclude_dir)
                                for i in range(3))))
    v = _vunit(_vsub(exclude_dir, tuple(u[i] * _vdot(exclude_dir, u)
                                       for i in range(3))))
    span_u = 0.0
    span_v = 0.0
    for point in points:
        span_u = max(span_u, abs(_vdot(point, u)))
        span_v = max(span_v, abs(_vdot(point, v)))
    return u if span_u >= span_v else v


def finger_geo_contribution(field, feature, finger_roles):
    """手指几何证据：依据物理位置推断出的手指身份与字段要求比对。

    返回 (ratio, reason)：
      ratio = 1.0  身份与节序都吻合；
             = 0.5  手指类型对但节序不符，或类型推断与字段要求冲突
                     （冲突时给中性分而非 0，避免几何推断在特殊骨架
                       （三指模型、握拳）失准时反而比纯名称匹配更差）；
             = None 没有几何推断结果（不作为证据）。
    """
    if _category(field) != "finger":
        return None, ""
    role = finger_roles.get(feature.name)
    if role is None:
        return None, ""
    finger, segment = role
    match = re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_(\d)$", field)
    if not match:
        return None, ""
    want_finger = match.group(2)
    want_segment = int(match.group(3))
    # 节号口径：拇指字段从 0 起（thumb_0 掌骨节），其余手指从 1 起
    # （index_1 掌骨节）。推断结果已按同一口径给出，直接比对。
    if finger != want_finger:
        return 0.5, f"几何推断为 {finger}，与字段要求 {want_finger} 不符"
    if segment == want_segment:
        return 1.0, f"几何推断 {finger} 第 {segment} 节"
    return 0.5, f"几何推断 {finger} 第 {segment} 节（节序不符）"


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
        # 强语义别名命中 → 精确档（带限定词，基本可确定是该字段）。
        # 但辅助骨（Scl/Twist/Socket…）只给包含档：它们是同一部位的
        # 缩放/扭曲骨，不是链上的主骨，给同分会让它们靠其他项的噪声
        # 险胜主骨，进而使下一节变成兄弟骨、整条链断裂。
        if _strong_alias_hit(field, tokens) and not _is_support_bone_name(bone_name):
            result = (NAME_EXACT, "名称语义匹配")
            _NAME_SCORE_CACHE[key] = result
            return result
        result = (NAME_CONTAINS, "名称包含匹配")
        _NAME_SCORE_CACHE[key] = result
        return result

    best = 0.0
    for known in table:
        if abs(len(known) - len(norm)) > 6:
            continue
        # ratio 按 (骨名, 已知名) 缓存：同一个已知名会出现在多个字段的
        # 预设表里（spine/hips/chest 这类），同一根骨名被各字段分别
        # 问一遍时会重复算同一个 (norm, known)。比值是纯函数，缓存安全。
        key_ratio = (norm, known)
        ratio = _RATIO_CACHE.get(key_ratio)
        if ratio is None:
            ratio = SequenceMatcher(None, norm, known).ratio()
            _RATIO_CACHE[key_ratio] = ratio
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
    """别名命中判定。

    tokens 是按驼峰/数字拆开的词，如 "G UpperArm L" → ['g','upper','arm','l']。
    但别名表里写的是 "upperarm"、"forearm" 这类**连写**形式，
    单个 token 匹配不上——于是 "G UpperArm L" 只能靠 "arm" 拿包含分，
    输给了拓扑分更高的缩放骨（实测 DNF 的腕* 拿到 ForeArm、偏成小臂）。

    故除了 token 集合，还要用**相邻 token 的拼接**再判一次。
    """
    token_set = set(tokens)
    # 相邻 token 两两拼接，覆盖驼峰连写形式
    joined = set(tokens)
    for index in range(len(tokens) - 1):
        joined.add(tokens[index] + tokens[index + 1])
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
            if (set(group).issubset(joined)
                    and any(w in joined for w in wanted)):
                return True
        return False
    return any(set(group).issubset(joined) for group in groups)


def _category_alias_words(category):
    """某类别的强语义别名集合（含左右两侧）。"""
    if category == "torso":
        return set(_TORSO_WORDS)
    words = set()
    for key in (f"left_{category}_bone", f"right_{category}_bone"):
        words.update(STRONG_ALIAS_TOKENS.get(key, ()))
    return words


def _bone_matches_category(bone_name, category):
    """骨名是否明确属于某一节（肩/上臂/小臂/手/指…）。

    只认强语义别名——命名不规范的骨匹配不上时返回 False，
    此时不触发否决（宁可放过，不可错杀）。

    辅助骨（Scl/Twist/Shape/Socket…）一律不算：它们是挂在肢体上的
    控制器/缩放骨，位置和命名都不代表链结构。实测 Gley 的正确上臂骨
    `Bip001-L-UpperArm` 下挂着肩部控制器 `Bn_Shape_Shoulder_L`，
    若把辅助骨当证据，会误判成「子骨是肩骨」而否掉整根主骨。
    """
    if _is_support_bone_name(bone_name):
        return False
    key = (bone_name, category)
    cached = _CATEGORY_MATCH_CACHE.get(key)
    if cached is not None:
        return cached
    if category == "finger":
        tokens = _tokens(bone_name)
        joined = set(tokens)
        for index in range(len(tokens) - 1):
            joined.add(tokens[index] + tokens[index + 1])
        for groups in FINGER_ALIASES.values():
            for group in groups:
                if set(group).issubset(joined):
                    _CATEGORY_MATCH_CACHE[key] = True
                    return True
        _CATEGORY_MATCH_CACHE[key] = False
        return False
    wanted = _category_alias_words(category)
    if not wanted:
        _CATEGORY_MATCH_CACHE[key] = False
        return False
    tokens = _tokens(bone_name)
    joined = set(tokens)
    for index in range(len(tokens) - 1):
        joined.add(tokens[index] + tokens[index + 1])
    result = any(word in joined for word in wanted)
    _CATEGORY_MATCH_CACHE[key] = result
    return result


def _shadowed_by_main_bone(field, feature, features):
    """辅助骨在同一父骨下有正牌主骨时，应让位给主骨。

    实测 DNF 的趾：`G Toe L`（名称 0.40）与 `GD Toe Scl L`（名称 0.25）
    是**兄弟骨**，都挂在 `GD Foot Scl L` 下。缩放骨靠蒙皮权重分（0.20）
    补回 0.15 的名称差，抢走了趾字段。

    判据只看父子层级：同一父骨下既然已有「同名非辅助骨」，那就是该环节
    的主骨，辅助骨只是它的跟随骨（缩放/扭曲），不该被填。
    """
    if not _is_support_bone_name(feature.name):
        return False
    parent = features.get(feature.parent) if feature.parent else None
    if parent is None:
        return False
    category = _category(field)
    for sibling_name in parent.children:
        if sibling_name == feature.name:
            continue
        if _is_support_bone_name(sibling_name):
            continue
        if _bone_matches_category(sibling_name, category):
            return True
    return False


def chain_relation_violated(field, feature, features):
    """父子关系是否明确反了——反了就该否决候选。

    判据（用名称语义，只在能明确识别时判定）：
      - 本环节的候选骨，其父骨若明确属于「下一节」（如上臂骨的父骨
        是小臂），说明父子颠倒；
      - 其子骨若明确属于「上一节」（如小臂骨的孩子是上臂），同样颠倒。

    实测 DNF：GD ForeArmLow Scl L 被填给上臂字段，正是因为它的父骨
    是小臂——父子反了。
    """
    category = _category(field)
    # 邻居表按字段基础名查（如 left_upper_arm_bone → upper_arm_bone）
    base = re.sub(r"^(left|right)_", "", field)
    neighbors = FIELD_CHAIN_NEIGHBORS.get(base)
    if not neighbors:
        return False
    # 1) 候选骨自身明确属于**别的环节** → 否决。
    #    如上臂字段拿到小臂骨（ForeArm L）——名称已说明它是小臂。
    for other in _CHAIN_CATEGORIES:
        if other == category:
            continue
        if _bone_matches_category(feature.name, other):
            return True
    parent_category, child_category = neighbors
    # 名称已强命中的骨，不再用父子骨语义推翻它。
    #
    # 有些 rig 把肩部形变骨挂在上臂**之下**（实测 Vipe：正确的上臂骨
    # Bip001-L-UpperArm001 的子骨叫 Bip001-L-Shoulder001），按「子骨
    # 属于上一节」判定会把正确的上臂骨整根否决，上臂只能退而求其次
    # 拿到大腿的扭转骨，整条手臂链断裂。这类骨架里父子关系是设计
    # 差异而非错配，名称强证据优先；真错配（上臂字段拿到 ForeArm）
    # 由上面第 1 条自身类别判定兜住，不依赖父子语义。
    if _strong_alias_hit(field, _tokens(feature.name)):
        return False
    if parent_category:
        parent_name = feature.parent
        parent = features.get(parent_name) if parent_name else None
        if parent is not None and _bone_matches_category(parent.name,
                                                          child_category):
            return True
    if child_category:
        for child_name in feature.children:
            child = features.get(child_name)
            if child is None:
                continue
            if _bone_matches_category(child.name, parent_category):
                return True
    return False


# 辅助骨的名称限定词：带这些词的骨是缩放/扭曲/挂点骨，不是链上的主骨。
#
# 实测 DNF：小臂字段选中 `GD ForeArmLow Scl L`（0.815）而非主骨
# `G ForeArm L`（0.813），差距只有 0.002——缩放骨的拓扑分低 0.11，
# 却被高度/方向分的微小差异补回来。小臂一旦拿到缩放骨，手骨
# （挂在同一父骨下）就成了它的**兄弟**而非子骨，整条链断裂。
#
# 只收「明确表示辅助」的词。不能收 up/low/end 这类：`LeftUpLeg`
# 的 token 里就有 up，收进来会把大腿主骨误降权。
# 辅助骨名称限定词。`shape` 单独列出：Gley 的 Bn_Shape_* 是控制骨族，
# 不参与变形，却常与主骨同名（Bn_Shape_Bip001_Calf_L 抢走「ひざ」）。
# 不能收 up/low/end —— `LeftUpLeg` 的 token 里就有 up，会误伤大腿主骨。
SUPPORT_BONE_TOKENS = frozenset((
    "scl", "scale", "twist", "socket", "dummy", "helper", "offset",
    "shape",
))


# 语义命名：兜底候选要不要卡「名称证据」的前提。
#
# 名称分为 0 的候选只剩左右/高度/方向这类位置证据，无法区分上臂与
# 头发（蒂法实测），所以语义骨架必须卡。但「左大臂 / 左小臂」这种
# 全中文骨架压根没有可用的肢体别名——它的拓扑满分档同样靠名称判定
# （_has_child_of 查子骨别名），一起卡会把整条腿臂链卡空、字段整体
# 错位一级。
#
# 判据只看**肢体字段**：躯干别名（上半身/首/頭）在中文骨架里常有，
# 但它们不参与链式判断，不能作为「这是语义骨架」的证据。
_LIMB_PROBE_FIELDS = (
    "left_upper_arm_bone", "left_lower_arm_bone", "left_hand_bone",
    "left_thigh_bone", "left_calf_bone", "left_foot_bone",
)


def _has_limb_semantics(features, stats):
    """骨架里是否有任何一根骨带**有效**的肢体别名证据。

    阈值取包含档：编辑距离给的零头分（「左手」对 hand 得 0.075）不算
    证据，否则部分命名的骨架会被误判成语义骨架，回头把几何候选全卡死。
    """
    for feature in features.values():
        for field in _LIMB_PROBE_FIELDS:
            if name_contribution(field, feature.name, stats)[0] >= NAME_CONTAINS:
                return True
    return False


def _is_support_bone_name(bone_name):
    """骨名是否带辅助骨限定词（缩放/扭曲/挂点）。"""
    cached = _SUPPORT_BONE_CACHE.get(bone_name)
    if cached is not None:
        return cached
    tokens = _tokens(bone_name)
    joined = set(tokens)
    for index in range(len(tokens) - 1):
        joined.add(tokens[index] + tokens[index + 1])
    result = any(word in joined for word in SUPPORT_BONE_TOKENS)
    _SUPPORT_BONE_CACHE[bone_name] = result
    return result


def _strong_alias_hit(field, tokens):
    """是否命中强语义别名（带限定词、命中即可确定字段）。

    多字段共用的词（spine/hips/chest 等）只给 AMBIGUOUS_PRIMARY 指定的
    主字段精确档，其余仍走包含档——否则同一根骨会同时抢多个字段。
    """
    strong = STRONG_ALIAS_TOKENS.get(field)
    if not strong:
        return False
    joined = set(tokens)
    for index in range(len(tokens) - 1):
        joined.add(tokens[index] + tokens[index + 1])
    # 骨名若命中「指向别的字段的降级词」，说明它明确属于那个字段，
    # 不能因为同时含本字段的泛化词（如 UpperChest 含 chest）就拿精确档。
    for word in joined:
        primary = AMBIGUOUS_PRIMARY.get(word)
        if primary is not None and primary != field:
            return False
    for word in strong:
        if word in joined:
            return True
    return False


# ---------------------------------------------------------------- 四类证据

# 肢体链上「下一节」的类别：上臂 → 小臂 → 手；大腿 → 小腿 → 脚
_NEXT_CATEGORY = {
    "shoulder": "upper_arm",
    "upper_arm": "lower_arm",
    "lower_arm": "hand",
    "hand": "finger",
    "thigh": "calf",
    "calf": "foot",
    "foot": "toe",
}


def _has_child_of(feature, features, category):
    """子骨里是否有「下一节」类别的骨。

    用名称语义判断（名称含下一节的强语义别名），不依赖具体 rig 的
    命名风格。
    """
    nxt = _NEXT_CATEGORY.get(category)
    if nxt is None:
        return feature.child_count >= 1
    if nxt == "finger":
        # 下一节是手指：STRONG_ALIAS_TOKENS 里没有 finger 这个键
        # （手指按 thumb/index/… 分字段），查它会永远落空，手掌因此
        # 拿不到满档拓扑分。改走类别判定，认「finger/thumb/index…」。
        return any(_bone_matches_category(child_name, "finger")
                   for child_name in feature.children)
    wanted = STRONG_ALIAS_TOKENS.get(f"left_{nxt}_bone", ())
    for child_name in feature.children:
        child = features.get(child_name)
        if child is None:
            continue
        tokens = _tokens(child.name)
        joined = set(tokens)
        for index in range(len(tokens) - 1):
            joined.add(tokens[index] + tokens[index + 1])
        if any(word in joined for word in wanted):
            return True
    return False


def topology_contribution(field, feature, features=None):
    """拓扑证据：层级深度、链位置、父子关系。"""
    if features is None:
        features = {}
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
        # 同 upper_arm：判「子骨里有没有上臂」而不是子骨数量。
        # Gley 的肩主骨 Bip001-L-Clavicle 挂着上臂 + 若干辅助骨，
        # 按数量只拿 0.6，被叶子状的控制骨 Bn_Shape_Shoulder_L 反超。
        score = 1.0 if _has_child_of(feature, features, category) else 0.6
    elif category in ("upper_arm", "lower_arm"):
        # 判据是「子骨里有下一节类型的骨」，而不是子骨数量：
        # 上臂挂着若干缩放骨时子骨数 > 1，但其中就含小臂；
        # 只看数量会让叶子状的缩放骨反超真实骨
        # （实测 DNF 的腕* 因此拿到 UpperArmMid 这类缩放骨）。
        score = 1.0 if _has_child_of(feature, features, category) else 0.55
    elif category == "hand":
        # 手掌的子骨里应有手指；只有缩放骨不算
        score = 1.0 if _has_child_of(feature, features, category) else 0.65
    elif category in ("thigh", "calf"):
        score = 1.0 if feature.child_count >= 1 else 0.55
    elif category == "foot":
        # 脚的子骨里应有脚趾；只有缩放骨不算
        score = 1.0 if _has_child_of(feature, features, category) else 0.65
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
            # 符号正确就该拿大部分分：侧向证据的核心作用是**区分左右**
            # （防止左右交叉），而不是「离中轴越远越好」。
            # 按纯距离算时，锁骨根这类本来就贴中轴的骨只拿 0.07，
            # 把本该正确的肩骨压到 0.69（实测 Gley），只能靠名称硬撑。
            reference = 0.05 * span if span > 0 else 1e-6
            side_raw = (SIDE_BASE
                        + (1.0 - SIDE_BASE) * min(1.0, abs(coord) / reference))
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

    # 手指身份的几何推断：若能从物理位置推出这根骨是哪根手指，
    # 则用它覆盖方向项——这比父子方向一致性更能定住手指归属。
    # 注意：推断只影响打分，不排除候选。特殊骨架（握拳、多指畸形）
    # 可能让推断失准，此时退化为「不给几何分」，仍由名称证据决定，
    # 不会因为推断错误而把正确的候选排除掉。
    finger_note = ""
    geo_ratio, geo_reason = finger_geo_contribution(
        field, feature, ctx.get("finger_roles") or {})
    if geo_ratio is not None:
        if geo_ratio == 0.0:
            direction_raw = 0.0
        else:
            direction_raw = geo_ratio
        finger_note = geo_reason

    parts = {
        "side": SIDE_MAX * side_raw,
        "height": HEIGHT_MAX * height_raw,
        "direction": DIRECTION_MAX * direction_raw,
    }
    reasons = [side_reason, height_reason, f"方向长度 {direction_raw:.2f}"]
    if finger_note:
        reasons.append(finger_note)
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
    # 执行顺序约定：**所有与名称无关的硬否决先做完，最后才算名称证据**。
    # name_contribution 要跑编辑距离，是整条流水线最贵的一步（实测占
    # solve 总耗时 40% 以上）；而脊柱链 / 中轴距离 / 手指域 / 手臂域这些
    # 否决只是集合成员测试和坐标比较。否决之间是 AND 关系，谁先谁后
    # 不影响结果，但先判便宜的能把绝大多数「明显不相关」的骨挡在
    # 名称计算之外（大骨架里 70% 以上的骨是被域过滤掉的）。
    #
    # 左右符号按 0.15 权重参与几何分，而非硬过滤：即使左右轴判定有偏差，
    # 名称证据仍有机会入选，由镜像约束在成对字段间兜底。
    # 例外：左右胸是成对侧别骨，中轴胸腔骨（Chest/Spine）名字含 chest 会误命中
    # 别名，须硬过滤掉，否则与上半身2抢同一根骨并导致左右胸留空。
    category = _category(field)
    side = _field_side(field)
    if side is not None and category == "chest":
        coord = feature.head[ctx["side_axis"]]
        if abs(coord) <= 1e-6 or (coord > 0) != (side == "L"):
            return None
    # 几何推断出的手指骨只归手指字段：非手指字段（手臂、腿、躯干等）
    # 若拿手指骨当候选，回溯会把手臂字段抢到手指骨上，导致
    # 手指字段无骨可用、出现半截手指。
    finger_roles = ctx.get("finger_roles") or {}
    if category != "finger" and feature.name in finger_roles:
        return None
    # 反向约束（手指字段）：
    #   ① 骨必须长在同侧的上肢分支上——手指骨必然是手掌骨的后代，
    #      域外的骨（躯干、腿、头发、眼球、武器挂点）一律排除；
    #   ② 还需有明确依据：名称命中手指别名，或被几何推断确认为手指。
    # 躯干类字段的候选不能在四肢域内：躯干骨与四肢骨虽同属一棵子树，
    # 但「下半身」拿到手掌骨是明显错误（实测 DNF 会这样）。
    # 域的划分见 _compute_limb_domains：四肢域 = 手掌及其子树 +
    # 沿父链到分叉点（锁骨/肩）之间的骨。
    if field in SPINE_BONE_FIELDS:
        # 脊柱链约束：中心骨必须是脊柱上的骨，偏离的左右肢体骨
        # （大腿、手臂）不该被填进来。用拓扑而非距离判定——髋关节
        # 距中轴约身高的 5%，纯距离阈值很难卡准。
        spine_chain = ctx.get("spine_chain")
        if spine_chain and feature.name not in spine_chain:
            return None
        span = ctx.get("span") or 0.0
        axis = ctx.get("midline")
        if span > 0 and axis is not None:
            offset = abs(feature.head[ctx["side_axis"]] - axis)
            if offset > span * MIDLINE_TOLERANCE:
                return None
        # 高度带硬约束：脊柱上但位置不对的骨（如头顶末端骨填进
        # 「下半身」）也要排除——高度带本来就是这些字段的解剖依据。
        band = Z_BANDS.get(field)
        if band:
            low, high = band
            if not (low <= feature.z_pct <= high):
                return None
    if category in ("torso", "center", "hip"):
        torso_domain = ctx.get("torso_domain")
        if torso_domain and feature.name not in torso_domain:
            return None

    # 上肢字段的候选必须在同侧上肢域内。域 = 手掌骨子树 + 沿父链向上的
    # 手臂骨（到贴近中轴处停），见 _compute_arm_domains。没有这条约束时，
    # 上臂/小臂/手的候选会退化成「同侧、同高度的任意骨」——蒂法实测把
    # 头发骨填进上臂，镜把头发物理骨填进小腿和手。
    if category in ("shoulder", "upper_arm", "lower_arm", "hand"):
        arm_domains = ctx.get("arm_domains") or {}
        arm_side = "left" if side == "L" else "right"
        domain = arm_domains.get(arm_side)
        if domain and feature.name not in domain:
            return None

    if category == "finger":
        domain = (ctx.get("finger_domains") or {}).get(
            "left" if field.startswith("left_") else "right")
        if domain is not None and feature.name not in domain:
            return None

    # 父子关系反了 → 否决：把子骨当父骨（如上臂字段拿到小臂骨）
    # 是结构性错误，不是分数高低问题，直接排除。
    if chain_relation_violated(field, feature, features):
        return None
    # 同父下有正牌主骨时，辅助骨让位
    if _shadowed_by_main_bone(field, feature, features):
        return None

    name_raw, name_reason = name_contribution(field, feature.name, ctx["stats"])
    # 语义字段缺少命名证据时，单靠高度带会命中头发、脚趾等无关骨骼。
    # 阈值用 NAME_CONTAINS(0.25) 而不是 >0——编辑距离给的零头分
    # （如「LeftToe_End」对 eye 得 0.01）不算有效证据。
    if name_raw < NAME_CONTAINS and category in ("eye", "chest"):
        return None
    if category == "finger" and not (name_raw > 0.0
                                     or feature.name in finger_roles):
        return None

    topo_raw, topo_reason = topology_contribution(field, feature, features)
    geo_parts, geo_reason = geometry_contributions(field, feature, features, ctx)
    if geo_parts is None:
        # 几何推断判定该骨的手指身份与字段冲突，排除此候选
        return None
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


def height_order_ok(field, bone, assignments, features, ctx):
    """中心骨的高度序是否成立：上侧字段的骨必须高于下侧字段的骨。

    这是独立于名称的几何证据——命名混乱的骨架也能靠位置定位。
    """
    up_axis = ctx.get("up_axis", 2)
    span = ctx.get("span") or 0.0
    # 容差：骨架很扁或两骨几乎同高时不算违反
    tolerance = span * 0.01 if span > 0 else 0.0
    here = features.get(bone)
    if here is None:
        return True
    for lower_field, upper_field in CENTER_HEIGHT_CHAINS:
        if field == upper_field and lower_field in assignments:
            other = features.get(assignments[lower_field]["bone"])
            if other is None:
                continue
            if here.head[up_axis] <= other.head[up_axis] + tolerance:
                return False
        elif field == lower_field and upper_field in assignments:
            other = features.get(assignments[upper_field]["bone"])
            if other is None:
                continue
            if here.head[up_axis] >= other.head[up_axis] - tolerance:
                return False
    return True


def chain_ok(field, bone, assignments, features, ctx=None):
    """字段候选是否满足拓扑与高度序约束。

    按字段预索引约束（_CHAIN_INDEX），只检查与该字段相关的几条，
    不遍历整张 CHAIN_PAIRS——回溯每个搜索节点都要调这里，
    约束表从 19 条涨到 39 条后，全表遍历会让大骨架（DNF 715 骨）
    提前撞上 MAX_SEARCH_NODES 搜索上限而退化。
    """
    for as_parent, other_field in _CHAIN_INDEX.get(field, ()):
        entry = assignments.get(other_field)
        if entry is None:
            continue
        other_bone = entry["bone"]
        if as_parent:
            # field 是父：bone 必须是 other 的祖先
            if not _is_ancestor(features, bone, other_bone):
                return False
        else:
            # field 是子：bone 必须挂在 other 之下
            if not _is_ancestor(features, other_bone, bone):
                return False
    if ctx is not None and not height_order_ok(field, bone, assignments,
                                              features, ctx):
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
    # 求解顺序：先按解剖层级「从中心到末端」推进（中心 → 躯干 → 上肢
    # → 手/手指 → 下肢 → 脚），同层级内再按候选分从高到低。
    #
    # 层级顺序的意义：
    #   - 中心骨先定，不会被四肢字段抢走；
    #   - 上肢先于手/手指，臂骨不会被手指字段误认（手指骨细长、
    #     数量多，若先挑骨容易抢走臂骨）；
    #   - 父字段先于子字段，chain_ok 的父子约束才能生效
    #     （手首先于手指、上半身先于上半身2）。
    def sort_key(field):
        segment = finger_segment(field)
        return (
            # 核心骨（面板带 * 的 MMD 必需骨）**跨层级**优先拿候选骨。
            # 必须放在层级之前：只做「同层内优先」不够——扩展骨
            # （センター/グルーブ/腰/下半身）在 center/torso 层，
            # 比 足*/ひざ* 的 leg 层先处理，会抢先挑走大腿小腿，
            # 结果核心骨空着、扩展骨填上了（实测 mixamorig 骨架）。
            priority_tier(field),
            # 再按解剖层级「从中心到末端」
            solve_stage_rank(field),
            # 中心骨链内按解剖顺序（自下而上），父字段先于子字段，
            # 高度序约束才能在子字段判定时生效
            center_bone_rank(field),
            # 手指层内按节号递增：先根部落位，再向末端推算
            segment if segment is not None else 0,
            -max((c["score"] for c in candidates.get(field, [])),
                 default=0.0),
            len(candidates.get(field, [])))

    order = sorted(field_order, key=sort_key)
    # 没有候选的字段一点分都拿不到（DFS 里根本不会给它赋值），
    # 不能计入上界。否则上界虚高：一个空字段白送 FILL_BONUS(0.15)
    # + field_bonus(核心骨 0.12)，60 个字段就是 11 分，
    # 而最优解通常只有 10~20 分 —— 剪枝条件 total+remaining<=best
    # 永远不成立，退化成全树遍历。实测仅 10 根骨的服装骨架
    # （DashBikini_Bottom）也会跑满 200k 节点上限。
    # 顺带把空字段剔出 order：它们无论如何都填不上，留在搜索路径上
    # 只是白白增加 2^空字段数 的节点深度。
    order = [f for f in order if candidates.get(f)]
    count = len(order)
    gains = []
    for field in order:
        best = max(c["score"] for c in candidates[field])
        gains.append(best + FILL_BONUS + field_bonus(field))

    # 上界不能逐字段求和：同一根骨只能分给一个字段。若剩余 L 个字段
    # 的候选骨并集只有 U 根（L > U），实际最多填 U 个字段。
    # 服装/头发这类骨架常是十几个字段抢三五根骨（Flex_Bra 16 骨、
    # Nyao Tail 23 骨），简单求和得上界 15 分而最优解只有 4 分，
    # 虚高 4 倍 → 剪枝永不触发，200k 节点跑满。
    remaining = [0.0] * (count + 1)
    suffix_bones = [frozenset()] * (count + 1)
    for index in range(count - 1, -1, -1):
        suffix_bones[index] = (
            suffix_bones[index + 1]
            | frozenset(c["bone"] for c in candidates[order[index]]))
        pool = sorted(gains[index:], reverse=True)
        capacity = min(len(pool), len(suffix_bones[index]))
        remaining[index] = sum(pool[:capacity])

    # 先按同一顺序求一个贪心解当保底下界：搜索被节点上限截断时也有结果，
    # 且强下界能让后续剪枝提前生效。
    greedy = {}
    greedy_used = set()
    for field in order:
        for candidate in candidates.get(field, []):
            bone = candidate["bone"]
            if bone in greedy_used:
                continue
            if not chain_ok(field, bone, greedy, features, ctx):
                continue
            # 镜像约束只对左右对称的骨架生效：非对称骨架（举单手、
            # 侧身等）的左右对应骨本就不该对称，硬否决会错杀正确配对。
            if (ctx.get("symmetric", True)
                    and mirror_error(field, bone, greedy, features, ctx)
                    > MIRROR_TOLERANCE):
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
            if not chain_ok(field, bone, assignments, features, ctx):
                continue
            if (ctx.get("symmetric", True)
                    and mirror_error(field, bone, assignments, features, ctx)
                    > MIRROR_TOLERANCE):
                continue
            assignments[field] = candidate
            used.add(bone)
            dfs(index + 1, assignments, used, total + candidate["score"] + gain)
            del assignments[field]
            used.remove(bone)
        dfs(index + 1, assignments, used, total)  # 允许留空

    dfs(0, {}, set(), 0.0)
    return best_assignment, nodes[0]


def _refine_center_by_height(assignments, candidates, features, ctx):
    """用相对位置校正中心骨：高度序不成立时按位置重新指派。

    解剖依据（与名称无关）：躯干自下而上——下半身 → 上半身 →
    上半身2 → 首 → 頭；上半身一定在下半身上方。

    名称匹配失败或错配时，靠这套相对位置关系仍能把中心骨摆对。
    """
    up_axis = ctx.get("up_axis", 2)
    span = ctx.get("span") or 0.0
    tolerance = span * 0.01 if span > 0 else 0.0

    def height_of(field):
        candidate = assignments.get(field)
        if candidate is None:
            return None
        feature = features.get(candidate["bone"])
        return feature.head[up_axis] if feature is not None else None

    changed = True
    rounds = 0
    while changed and rounds < len(CENTER_HEIGHT_CHAINS):
        changed = False
        rounds += 1
        for lower_field, upper_field in CENTER_HEIGHT_CHAINS:
            lower_h = height_of(lower_field)
            upper_h = height_of(upper_field)
            if lower_h is None or upper_h is None:
                continue
            if lower_h < upper_h - tolerance:
                continue  # 高度序成立
            # 违反：把较高那个字段改指到更高的候选骨
            for field, other_field in ((upper_field, lower_field),
                                       (lower_field, upper_field)):
                pool = candidates.get(field) or []
                best = None
                for candidate in pool:
                    feature = features.get(candidate["bone"])
                    if feature is None:
                        continue
                    if field == upper_field:
                        if feature.head[up_axis] <= lower_h + tolerance:
                            continue
                    else:
                        if feature.head[up_axis] >= upper_h - tolerance:
                            continue
                    if best is None or candidate["score"] > best["score"]:
                        best = candidate
                if best is not None:
                    assignments[field] = best
                    changed = True
                    break


# 躯干语义关键词：主链上的过渡骨（脊柱/胸腔）常含这些词，
# 而马尾、牙齿、挂件等辅助骨不含。
_TORSO_SEMANTIC_TOKENS = ("spine", "chest", "torso", "ribcage", "sternum",
                           "body", "上半身", "胸", "背", "spine")


def _is_torso_semantic(bone_name):
    """骨名是否带躯干语义（脊柱/胸腔类过渡骨）。"""
    lower = bone_name.lower()
    return any(token in lower for token in _TORSO_SEMANTIC_TOKENS)


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
                    or not chain_ok(child_field, bone_name, assignments, features, ctx)):
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
        # 中间链里挑出「躯干语义」的骨（Spine/Chest/上半身 等），
        # 排除马尾、牙齿、挂件这类挂在同一区间的辅助骨。
        preferred = [b for b in chain
                     if _is_torso_semantic(b)]
        fallback = [b for b in chain if b not in preferred]
        ordered_chain = preferred + fallback
        for index, field in enumerate(("upper_body2_bone", "upper_body3_bone",
                                       "upper_body4_bone", "upper_body5_bone")):
            if index >= len(ordered_chain):
                break
            bone_name = ordered_chain[index]
            if field in assignments or bone_name in used:
                continue
            candidate = score_candidate(field, features[bone_name], features, ctx)
            if candidate is None:
                continue
            # 推导不依赖打分门槛：骨在主链上就是依据。分数只用于
            # 决定是否高置信显示。
            candidate["derived"] = "upper_body_chain"
            if candidate["score"] < CONFIDENCE_THRESHOLD:
                candidate["low_confidence"] = True
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
            best_free = None
            while current:
                # 胸親是辅助骨：MMD 标准骨架里它常与「上半身/上半身2」共用
                # 同一根骨（Mixamo 的 Spine/Chest 就是这种情况），因此允许
                # 复用主链已占用的骨骼，只要求拓扑上位于锚点的父链。
                candidate = score_candidate("breast_parent_bone", features[current],
                                            features, ctx)
                if candidate:
                    if current not in used:
                        if best_free is None or candidate["score"] > best_free["score"]:
                            best_free = candidate
                    elif best is None or candidate["score"] > best["score"]:
                        best = candidate
                current = features[current].parent if current in features else None
            # 优先用未被占用的骨，避免与上半身2 等字段指向同一根骨；
            # 实在没有才复用（Mixamo 骨架的常态）。
            chosen = best_free or best
            # 辅助骨用略低的派生阈值，避免 0.54 这种边界分把明显的骨留空
            if chosen and chosen["score"] >= DERIVED_THRESHOLD:
                chosen["derived"] = "chest_parent_chain"
                assignments["breast_parent_bone"] = chosen

    # 最后用相对位置校正中心骨的高度序
    try:
        _refine_center_by_height(assignments, candidates, features, ctx)
    except Exception:
        pass


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
    if not chain_ok(field, bone, assignments, features, ctx):
        return "主链父子约束冲突"
    if ctx.get("symmetric", True):
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
    _trim_caches()
    if stats is None:
        stats = load_preset_stats(preset_dir) if preset_dir else load_preset_stats()
    ctx = {
        "span": span, "diagonal": diagonal, "z_min": z_min,
        "up_axis": up_axis, "side_axis": side_axis, "stats": stats,
    }

    # 骨架左右对称性：非对称骨架不能套用镜像约束，否则会错杀正确的
    # 左右配对（举单手、侧身等姿态下左右对应骨本就不该对称）。
    try:
        symmetric, symmetry_error = detect_symmetry(
            features, span, side_axis, up_axis)
    except Exception:
        symmetric, symmetry_error = True, 0.0
    ctx["symmetric"] = symmetric
    ctx["symmetry_error"] = symmetry_error
    # 骨架是否用了肢体语义命名：决定兜底候选是否必须带名称证据
    try:
        ctx["limb_semantics"] = _has_limb_semantics(features, stats)
    except Exception:
        ctx["limb_semantics"] = True
    # 身体中轴与脊柱主链：中心骨必须在脊柱上且贴近中轴
    try:
        ctx["midline"] = detect_midline(features, side_axis)
        ctx["spine_chain"] = detect_spine_chain(features, up_axis)
    except Exception:
        ctx["midline"] = 0.0
        ctx["spine_chain"] = set()
    # 左右配对表：兜底填充时优先用「对侧已填骨的同名配对骨」——
    # 左右对称的骨在位置上互为镜像，这是比分数更硬的物理证据。
    try:
        pair_of = {}
        for left_name, right_name in _named_side_pairs(features):
            pair_of[left_name] = right_name
            pair_of[right_name] = left_name
        ctx["side_pair_of"] = pair_of
    except Exception:
        ctx["side_pair_of"] = {}

    # 手指身份的几何推断：一次性算出手指骨 → (类型, 节序) 的映射，
    # 供后续打分作为独立于名称的位置证据。
    try:
        roles, finger_sides, finger_domains = infer_finger_roles(
            features, span, side_axis, up_axis)
        ctx["finger_roles"] = roles
        ctx["finger_sides"] = finger_sides
        ctx["finger_domains"] = finger_domains
    except Exception:
        ctx["finger_roles"] = {}
        ctx["finger_sides"] = {}
        ctx["finger_domains"] = {}

    # 躯干域单独算：不能被手指推断的失败牵连（域失效时约束形同虚设）
    try:
        palm_names = list(_find_palm_bones(features, span))
        _limb, torso = _compute_limb_domains(features, palm_names)
        ctx["torso_domain"] = torso
        ctx["arm_domains"] = _compute_arm_domains(
            features, palm_names, span, side_axis)
    except Exception:
        ctx["torso_domain"] = set()
        ctx["arm_domains"] = {}

    candidates = {}
    best_scores = {}
    # 兜底候选池：分数较低但仍可用的候选，专供「回溯未选中时照填」
    # 使用，不参与回溯搜索，避免低分候选挤占主链骨。
    spare_candidates = {}
    for field in field_order:
        field_candidates = []
        field_spares = []
        for feature in features.values():
            candidate = score_candidate(field, feature, features, ctx)
            if not candidate:
                continue
            # 候选必须有「名称」或「满档拓扑」支持（语义骨架才卡，见
            # _semantic_coverage）。名称分为 0 时剩下的只有左右 / 高度 /
            # 方向这类位置证据，总分天花板约 0.46——足够跨过正式候选线，
            # 却完全无法区分上臂与头发。蒂法实测上臂被填成头发骨
            # DEF-Hair_E_05.L（0.385，名称 0），整条手臂链反向断裂；
            # 镜的腿和手被十几根头发物理骨占满。
            strict = ctx.get("limb_semantics", True)
            parts = candidate["parts"]
            has_evidence = (not strict
                            or parts.get("name", 0.0) > 0.0
                            or parts.get("topology", 0.0) >= TOPO_MAX - 1e-9)
            if candidate["score"] >= MIN_CANDIDATE_SCORE:
                if has_evidence:
                    field_candidates.append(candidate)
            elif candidate["score"] >= SPARE_CANDIDATE_SCORE:
                if has_evidence:
                    field_spares.append(candidate)
        field_candidates.sort(key=lambda c: c["score"], reverse=True)
        field_spares.sort(key=lambda c: c["score"], reverse=True)
        if field_candidates:
            best_scores[field] = field_candidates[0]["score"]
        candidates[field] = field_candidates[:MAX_CANDIDATES]
        # 正式候选 + 兜底候选合并，兜底在后
        spare_candidates[field] = (field_candidates[:MAX_CANDIDATES]
                                   + field_spares[:MAX_CANDIDATES])

    # 几何推断出的手指身份是**强证据**，直接预填，不走回溯。
    # 走回溯的话，低分匹配可能顶掉正确的手指骨，造成半截手指
    # （拇指第 1 节拿到小指骨、拇指第 3 节空着）。
    # 预填后回溯会把这些骨视为已占用，不会再抢。
    prefilled = {}
    finger_roles = ctx.get("finger_roles") or {}
    finger_sides = ctx.get("finger_sides") or {}
    if finger_roles and finger_sides:
        for field in field_order:
            segment = finger_segment(field)
            if segment is None:
                continue
            side = "left" if field.startswith("left_") else "right"
            wanted_finger = field.split("_")[1]
            # 推断结果的节序号已按字段口径给出（拇指从 0 起、其余从 1 起），
            # 直接与字段节号比对，不再做偏移。
            for bone_name, (finger, bone_segment) in finger_roles.items():
                if (finger_sides.get(bone_name) == side
                        and finger == wanted_finger
                        and bone_segment == segment):
                    candidate = next((c for c in candidates.get(field, [])
                                      if c["bone"] == bone_name), None)
                    if candidate is None:
                        candidate = score_candidate(field, features[bone_name],
                                                   features, ctx)
                    if candidate is not None:
                        prefilled[field] = candidate
                    break

    # 上半身2~5 不参与回溯（只走拓扑推导），避免抢走真实骨
    match_fields = [f for f in field_order if f not in NO_AUTO_MATCH_FIELDS]
    assignments, nodes = _solve_backtrack(candidates, match_fields, features,
                                          ctx)
    assignments = dict(assignments)
    # 预填的手指覆盖回溯结果（回溯可能给同一字段选了别的骨）
    for field, candidate in prefilled.items():
        bone = candidate["bone"]
        # 若回溯把这根骨分给了别的字段，把那个字段腾出来
        for other_field, other in list(assignments.items()):
            if other_field != field and other["bone"] == bone:
                assignments.pop(other_field)
        assignments[field] = candidate
    _post_complete(assignments, candidates, field_order, features, ctx)

    low_conf = []
    reported = set()
    # 镜像误差过大时丢弃较不可信的一侧——仅对左右对称的骨架成立。
    # 非对称骨架（举单手、侧身等）的左右骨本就不该对称，不能据此丢弃。
    if ctx.get("symmetric", True):
        for left_field in (f for f in field_order if f.startswith("left_")):
            right_field = "right_" + left_field[len("left_"):]
            if left_field not in assignments or right_field not in assignments:
                continue
            error = mirror_error(left_field, assignments[left_field]["bone"],
                                 assignments, features, ctx)
            if error <= MIRROR_TOLERANCE:
                continue
            # 先试**交换左右**再决定丢弃：镜像误差大有两种原因——
            # 一侧选错了骨（该丢），或左右整体判定反了（该交换）。
            # 交换后误差明显更小，说明是左右交叉，交换即可纠正；
            # 直接丢弃会把本可救回的一侧白白空出来。
            left_entry = dict(assignments[left_field])
            right_entry = dict(assignments[right_field])
            left_entry["field"], right_entry["field"] = left_field, right_field
            swapped = dict(assignments)
            swapped[left_field], swapped[right_field] = right_entry, left_entry
            swapped_error = mirror_error(left_field,
                                         swapped[left_field]["bone"],
                                         swapped, features, ctx)
            if swapped_error < error:
                assignments[left_field] = left_entry
                assignments[right_field] = right_entry
                error = swapped_error
                for entry in (left_entry, right_entry):
                    entry["low_confidence"] = True
                if error <= MIRROR_TOLERANCE:
                    continue
            drop = (assignments[left_field]
                    if assignments[left_field]["score"]
                    <= assignments[right_field]["score"]
                    else assignments[right_field])
            assignments.pop(drop["field"], None)
            low_conf.append((drop["field"], drop["score"],
                             "左右镜像误差过大"))
            reported.add(drop["field"])

    # 低置信度的赋值照常保留（用户要求「填上 + 标红警告」），只是标记出来
    # 供面板高亮。原先这里是直接丢弃，字段留空交给用户手填。
    filled = {}
    for field, candidate in assignments.items():
        score = candidate["score"]
        derived_ok = candidate.get("derived") and score >= DERIVED_THRESHOLD
        if score < CONFIDENCE_THRESHOLD and not derived_ok:
            candidate["low_confidence"] = True
            low_conf.append((field, score, "置信度低于阈值"))
        filled[field] = candidate

    # 回溯未选中的字段也照填（用户要求「全部填上 + 标红」）：
    # 从候选里挑一根骨填入，避免面板上留下空白行。
    # 只挑尚未被占用的候选骨——同一根骨不能映射到多个字段
    # （MMD 要求字段与骨骼一一对应）。若候选全被占用，
    # 说明该部位确实缺少独立骨骼（如三指模型凑不出 5 指 30 节），
    # 此时保持留空并在低置信度列表中说明，由用户手动指定。
    used_bones = {c["bone"] for c in filled.values()}

    # 先按几何推断出的手指角色**成组**填充：一条手指链的各节骨要
    # 一起分配给同一根手指的对应字段，不能拆散——否则会出现
    # 「食指第 3 节有值、第 1 节空着」这种半截手指。
    finger_roles = ctx.get("finger_roles") or {}
    if finger_roles:
        # 按 (左右, 手指类型) 把骨节分组
        groups = {}
        finger_sides = ctx.get("finger_sides") or {}
        for bone_name, (finger, segment) in finger_roles.items():
            side = finger_sides.get(bone_name)
            if side is None:
                continue
            groups.setdefault((side, finger), []).append((segment, bone_name))
        for (side, finger), items in groups.items():
            items.sort()
            # 该手指对应的字段（拇指从 0 起编号，其余从 1 起）
            base = 0 if finger == "thumb" else 1
            pending = []
            for segment, bone_name in items:
                field = f"{side}_{finger}_{segment - base}"
                if field not in field_order:
                    continue
                if field in filled or field in reported:
                    continue
                if bone_name in used_bones:
                    continue
                pending.append((field, bone_name, segment))
            # 只有整条链都能分配时才填，避免半截手指
            if len(pending) != len(items):
                for field, _bone, _seg in pending:
                    if field not in filled:
                        low_conf.append((field, 0.0,
                                         "该手指骨节不完整，未成组填入"))
                continue
            for field, bone_name, _segment in pending:
                candidate = next((c for c in (spare_candidates.get(field) or [])
                                  if c["bone"] == bone_name), None)
                if candidate is None:
                    candidate = {
                        "field": field, "bone": bone_name, "score": 0.0,
                        "raw": 0.0, "parts": {},
                        "reason": "几何推断：按手指位置填入",
                    }
                chosen = dict(candidate)
                chosen["low_confidence"] = True
                filled[field] = chosen
                used_bones.add(bone_name)
                low_conf.append((field, chosen["score"], "按手指位置填入，请核对"))

    for field in field_order:
        if field in filled or field in reported:
            continue
        if field in NO_AUTO_MATCH_FIELDS:
            # 不参与自动匹配的字段（上半身2~5）只走拓扑推导，
            # 推导不出就留空，不用候选池硬填——否则会填进马尾、
            # 牙齿这类中间的辅助骨。
            low_conf.append((field, 0.0, "未参与自动匹配（由主链推导）"))
            continue
        field_candidates = spare_candidates.get(field) or []
        if not field_candidates:
            # 连候选都没有（如眼/胸这类需要名称证据的字段）：
            # 仍要提示，让用户知道这里没找到，而不是静默留空。
            low_conf.append((field, 0.0, "未找到可用候选"))
            continue
        free_list = [c for c in field_candidates if c["bone"] not in used_bones]
        if not free_list:
            reason = explain_missing(field, candidates, filled, features, ctx)
            low_conf.append((field, field_candidates[0]["score"], reason))
            continue
        # 兜底也要尊重父子层级：回溯阶段 chain_ok 把这些骨否决掉才留空，
        # 若兜底再按分数硬填回去，等于把约束绕过（实测 Gley/DNF 的链断裂
        # 全出自这条路径）。故优先挑通过 chain_ok 的候选，
        # 都不符时才退而求其次，并在理由里明确标出拓扑不符。
        free = next((c for c in free_list
                     if chain_ok(field, c["bone"], filled, features, ctx)), None)
        topological_ok = free is not None
        # 镜像优先：对侧字段已填的骨若有同名配对骨，那根骨的位置就是
        # 对侧骨的镜像，比按分数挑更可靠（左右对称是物理事实）。
        if free is not None and field.startswith(("left_", "right_")):
            other_field = ("right_" + field[len("left_"):]
                           if field.startswith("left_")
                           else "left_" + field[len("right_"):])
            other = filled.get(other_field)
            if other is not None:
                mirror_name = ctx.get("side_pair_of", {}).get(other["bone"])
                if mirror_name is not None:
                    mirror = next((c for c in free_list
                                   if c["bone"] == mirror_name), None)
                    if (mirror is not None
                            and chain_ok(field, mirror["bone"], filled,
                                         features, ctx)):
                        free = mirror
        if free is None:
            # 手指节例外：同指各节必须是一条连续链，填一条别的链上的
            # 指骨只会让 MMD 变形错乱（实测畸形骨架里拇指第 3 节被填到
            # 另一根手指的根骨上），比留空更糟。其余字段仍按「照填 + 标红」
            # 处理，让用户看到候选而不是空着。
            if field in _FINGER_FIELD_SET:
                low_conf.append((field, free_list[0]["score"],
                                 "与同指其它节不同链，未填入"))
                continue
            free = free_list[0]
        chosen = dict(free)
        chosen["low_confidence"] = True
        reason = explain_missing(field, candidates, filled, features, ctx)
        if not topological_ok:
            reason = f"拓扑关系不符（{reason}）"
        filled[field] = chosen
        used_bones.add(chosen["bone"])
        low_conf.append((field, chosen["score"], reason))

    # 平均置信度只统计稳妥填写（不含低置信度项），避免拉低整体评价
    solid = [c for c in filled.values() if not c.get("low_confidence")]
    result_stats = {
        "bone_count": len(features),
        "filled": len(filled),
        "solid": len(solid),
        "low_conf": len(low_conf),
        "average": (sum(c["score"] for c in solid) / len(solid)
                    if solid else 0.0),
        "search_nodes": nodes,
    }
    return filled, low_conf, result_stats
