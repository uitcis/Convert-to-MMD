"""自动骨骼映射：名称、拓扑、几何、权重四类证据加权打分 + 全局约束求解。

结果写回 scene 上的骨骼字段，因此可直接复用现有的重命名、重建骨骼、
IK、导出预设等流程。
"""

import bpy
import json
import math
import os
import re
from difflib import SequenceMatcher

from mathutils import Vector

from ..bone_map_and_group import mmd_bone_map

FIELD_ORDER = list(mmd_bone_map.keys()) + ["breast_parent_bone"]

# 四类证据的权重（总分 1.0）
EVIDENCE_WEIGHTS = {
    "name": 0.40,
    "topology": 0.20,
    "geometry": 0.25,
    "weight": 0.15,
}

CONFIDENCE_THRESHOLD = 0.55   # 低于该置信度的字段留空
MIN_CANDIDATE_SCORE = 0.35    # 不参与求解的最低分
MIRROR_TOLERANCE = 0.08       # 左右镜像误差（相对身高）

PRESET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets"
)

_PRESET_STATS = None
_NAME_SCORE_CACHE = {}

# 需要强制父子顺序的字段对（父 -> 子）。只有当两者都已分配时才校验。
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

FINGER_FIELDS = [f for f in FIELD_ORDER if re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_", f)]

# 各字段期望的高度区间（0=最低，1=最高），左右、手指数值字段共用
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

# 别名关键词（token 组），仅在预设库无法精确匹配时作为补充证据
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
    "left_chest_bone": [("breast",), ("chest",)],
    "right_chest_bone": [("breast",), ("chest",)],
    "control_center_bone": [("root",), ("control",), ("center",)],
    "all_parents_bone": [("root",), ("master",), ("parent",)],
    "center_bone": [("center",), ("ctrl",)],
    "groove_bone": [("groove",), ("waist",)],
    "breast_parent_bone": [("chest",), ("spine",)],
}

# 拓扑类别
def _category(field):
    if field == "all_parents_bone":
        return "root"
    if field in ("center_bone", "groove_bone", "control_center_bone", "breast_parent_bone"):
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
    if FINGER_FIELDS and field in FINGER_FIELDS:
        return "finger"
    for token in ("shoulder", "upper_arm", "lower_arm", "hand",
                  "thigh", "calf", "foot", "toe"):
        if token in field:
            return token if token not in ("thigh", "calf") else token
    return "other"


def _field_side(field):
    if field.startswith("left_"):
        return "L"
    if field.startswith("right_"):
        return "R"
    return None


def _normalize(name):
    """归一化骨骼名：去常见前缀、去分隔符、小写。"""
    n = name.lower()
    n = re.sub(r"^(mixamorig|bip0?0?1|bip001|vrm|armature)[:._ -]*", "", n)
    n = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", "", n)
    return n


def _tokens(name):
    """拆分为小写 token，例如 LeftHandIndex1 -> [left, hand, index, 1]。"""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"([_.:\- ])+", " ", s)
    return [t.lower() for t in s.split() if t]


def _load_preset_stats():
    """统计 presets 目录中每个字段出现过的骨骼名。"""
    global _PRESET_STATS
    if _PRESET_STATS is not None:
        return _PRESET_STATS
    stats = {f: {} for f in FIELD_ORDER}
    try:
        filenames = sorted(os.listdir(PRESET_DIR))
    except OSError:
        filenames = []
    for filename in filenames:
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(PRESET_DIR, filename), "r", encoding="utf-8") as fh:
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
    _PRESET_STATS = stats
    return stats


def _alias_score(field, tokens):
    token_set = set(tokens)
    groups = list(ALIAS_TOKENS.get(field, []))
    match = re.match(r"^(left|right)_(thumb|index|middle|ring|pinky)_(\d)$", field)
    if match:
        finger = match.group(2)
        groups.extend(FINGER_ALIASES.get(finger, []))
        digit = match.group(3)
    else:
        digit = None

    best = 0.0
    for group in groups:
        if not set(group).issubset(token_set):
            continue
        if digit is not None:
            # thumb 字段 0/1/2 对应模型里的 1/2/3；其余手指 1/2/3 直接对应
            if finger == "thumb":
                wanted = {"0": ("1",), "1": ("2",), "2": ("3",)}.get(digit, ())
            else:
                wanted = (digit,)
            if finger_has_digit(token_set, wanted):
                return 0.9
            continue
        best = max(best, 0.75)
    return best


def finger_has_digit(token_set, wanted):
    return any(w in token_set for w in wanted)


def _name_score(field, bone_name):
    key = (field, _normalize(bone_name))
    cached = _NAME_SCORE_CACHE.get(key)
    if cached is not None:
        return cached

    norm = key[1]
    stats = _load_preset_stats()[field]
    if not norm or not stats:
        _NAME_SCORE_CACHE[key] = 0.0
        return 0.0

    if norm in stats:
        _NAME_SCORE_CACHE[key] = 1.0
        return 1.0

    tokens = _tokens(bone_name)
    alias = _alias_score(field, tokens)

    best = 0.0
    for known in stats:
        if abs(len(known) - len(norm)) > 6:
            continue
        ratio = SequenceMatcher(None, norm, known).ratio()
        if ratio > best:
            best = ratio
            if best >= 0.98:
                break

    score = max(alias, best * 0.85 if best >= 0.80 else best * 0.4)
    _NAME_SCORE_CACHE[key] = score
    return score


class BoneFeature:
    """单根骨骼的几何/拓扑/权重特征。"""

    __slots__ = ("name", "head", "tail", "depth", "depth_pct", "children",
                 "child_count", "z_pct", "x", "length", "parent",
                 "weight_sum", "weight_centroid")

    def __init__(self, bone, depth, max_depth, z_min, span, up_axis):
        self.name = bone.name
        self.head = bone.head_local.copy()
        self.tail = bone.tail_local.copy()
        self.parent = bone.parent.name if bone.parent else None
        self.depth = depth
        self.depth_pct = depth / max_depth if max_depth else 0.0
        self.children = [c.name for c in bone.children]
        self.child_count = len(self.children)
        self.length = (self.tail - self.head).length
        up = self.head[up_axis]
        self.z_pct = (up - z_min) / span if span else 0.0
        self.x = self.head.x
        self.weight_sum = 0.0
        self.weight_centroid = None


def _bound_meshes(armature):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        bound = obj.parent == armature
        if not bound:
            bound = any(m.type == "ARMATURE" and m.object == armature
                        for m in obj.modifiers)
        if bound:
            meshes.append(obj)
    return meshes


def _collect_weight_stats(armature, features):
    """按顶点组权重统计每根骨骼的权重和与权重质心（骨架局部空间）。"""
    try:
        inv = armature.matrix_world.inverted()
    except (ValueError, RuntimeError):
        inv = None
    for mesh_obj in _bound_meshes(armature):
        group_to_bone = {}
        for idx, group in enumerate(mesh_obj.vertex_groups):
            if group.name in features:
                group_to_bone[idx] = group.name
        if not group_to_bone:
            continue
        try:
            matrix = (inv @ mesh_obj.matrix_world) if inv is not None else mesh_obj.matrix_world
        except (ValueError, RuntimeError):
            matrix = mesh_obj.matrix_world
        for vertex in mesh_obj.data.vertices:
            if not vertex.groups:
                continue
            co = matrix @ vertex.co
            for element in vertex.groups:
                bone_name = group_to_bone.get(element.group)
                if not bone_name or element.weight <= 1e-4:
                    continue
                feature = features[bone_name]
                feature.weight_sum += element.weight
                if feature.weight_centroid is None:
                    feature.weight_centroid = co.copy()
                else:
                    feature.weight_centroid += co


def _pick_up_axis(bones):
    """选择骨骼包围盒跨度最大的轴作为高度轴（兼容横躺模型）。"""
    coords = [b.head_local for b in bones]
    extents = [max(c[i] for c in coords) - min(c[i] for c in coords) for i in range(3)]
    return max(range(3), key=lambda i: extents[i])


def build_features(armature):
    bones = [b for b in armature.data.bones if b.name not in ("",)]
    # 过滤工具生成的辅助骨
    bones = [b for b in bones
             if not re.search(r"(_dummy_|_shadow_|\.L\.\d+$)", b.name)]
    if not bones:
        return {}, 0.0, 0.0

    max_depth = 0
    depth_map = {}
    for bone in bones:
        depth = 0
        current = bone.parent
        while current is not None:
            depth += 1
            current = current.parent
        depth_map[bone.name] = depth
        max_depth = max(max_depth, depth)

    up_axis = _pick_up_axis(bones)
    up_values = [b.head_local[up_axis] for b in bones]
    z_min, z_max = min(up_values), max(up_values)
    span = z_max - z_min

    features = {}
    for bone in bones:
        features[bone.name] = BoneFeature(
            bone, depth_map[bone.name], max_depth, z_min, span, up_axis)

    _collect_weight_stats(armature, features)
    for feature in features.values():
        if feature.weight_centroid is not None and feature.weight_sum > 0:
            feature.weight_centroid = feature.weight_centroid / feature.weight_sum

    diagonal = 0.0
    if features:
        pts = [f.head for f in features.values()]
        mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        diagonal = (maxs - mins).length
    return features, span, diagonal


def _geometry_score(field, feature, span):
    band = Z_BANDS.get(field)
    if not band:
        return 0.5
    low, high = band
    if low <= feature.z_pct <= high:
        score = 1.0
    else:
        distance = low - feature.z_pct if feature.z_pct < low else feature.z_pct - high
        score = math.exp(-((distance / 0.12) ** 2))
    # 末端骨（足尖/脚/手）不应过长
    if field.endswith(("_foot_bone", "_toe_bone")) and span > 0:
        if feature.length > span * 0.35:
            score *= 0.6
    return score


def _topology_score(field, feature):
    category = _category(field)
    if category == "root":
        return 1.0 if feature.depth == 0 else 0.2
    if category == "control":
        score = 1.0 if feature.depth <= 3 else 0.5
        # 控制骨通常不直接蒙皮；Hips 这类带权重的形变骨应让位给身体链字段
        if feature.weight_sum > 0:
            score *= 0.6
        return score
    if category == "hip":
        if feature.depth <= 3 and feature.child_count >= 2:
            return 1.0
        return 0.6
    if category == "torso":
        if field == "upper_body_bone":
            return 1.0 if feature.child_count >= 1 else 0.5
        return 1.0 if feature.child_count >= 1 else 0.6
    if category == "neck":
        return 1.0 if 1 <= feature.child_count <= 3 else 0.55
    if category == "head":
        return 1.0
    if category == "eye":
        return 1.0 if feature.child_count == 0 and feature.length > 0 else 0.6
    if category == "chest":
        return 1.0 if feature.weight_sum > 0 else 0.4
    if category == "finger":
        if field.endswith("_3"):
            return 1.0 if feature.child_count <= 1 else 0.7
        return 1.0 if feature.child_count == 1 else 0.65
    if category == "shoulder":
        return 1.0 if feature.child_count == 1 else 0.6
    if category in ("upper_arm", "lower_arm"):
        return 1.0 if feature.child_count == 1 else 0.55
    if category == "hand":
        return 1.0 if feature.child_count >= 1 else 0.65
    if category in ("thigh", "calf"):
        return 1.0 if feature.child_count >= 1 else 0.55
    if category == "foot":
        return 1.0 if feature.child_count >= 1 else 0.65
    if category == "toe":
        return 1.0 if feature.child_count <= 1 else 0.75
    return 0.5


def _weight_score(feature, diagonal):
    if feature.weight_sum <= 0 or feature.weight_centroid is None:
        return 0.0
    if diagonal <= 0:
        return 0.8
    dist = (feature.weight_centroid - feature.head).length
    proximity = math.exp(-((dist / (0.25 * diagonal)) ** 2))
    return 0.5 + 0.5 * proximity


def _side_ok(field, feature):
    side = _field_side(field)
    if side is None:
        return True
    # 插件约定：局部 +X 为左侧
    if side == "L":
        return feature.x > 0.0
    return feature.x < 0.0


def _score_candidate(field, feature, span, diagonal):
    if not _side_ok(field, feature):
        return None
    parts = {
        "name": _name_score(field, feature.name),
        "topology": _topology_score(field, feature),
        "geometry": _geometry_score(field, feature, span),
        "weight": _weight_score(feature, diagonal),
    }
    # 目/胸这类语义字段仅靠高度区间会命中头发等无关骨骼，必须有命名证据
    if parts["name"] <= 0.0 and _category(field) in ("eye", "chest"):
        return None
    total = sum(parts[key] * EVIDENCE_WEIGHTS[key] for key in EVIDENCE_WEIGHTS)
    return {
        "field": field,
        "bone": feature.name,
        "score": total,
        "parts": parts,
    }


def _is_ancestor(features, ancestor_name, descendant_name):
    if ancestor_name == descendant_name:
        return True
    current = features[descendant_name].parent
    while current:
        if current == ancestor_name:
            return True
        current = features[current].parent if current in features else None
    return False


def _chain_ok(field, bone, assignments, features):
    for parent_field, child_field in CHAIN_PAIRS:
        if field == child_field and parent_field in assignments:
            parent_bone = assignments[parent_field]["bone"]
            if not _is_ancestor(features, parent_bone, bone):
                return False
        if field == parent_field and child_field in assignments:
            child_bone = assignments[child_field]["bone"]
            if not _is_ancestor(features, bone, child_bone):
                return False
    return True


def _descendants(features, root_name):
    result = []
    stack = [c for c in features[root_name].children if c in features]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(c for c in features[current].children if c in features)
    return result


def solve_mapping(armature):
    """执行打分与约束求解，返回 (assignments, low_conf, stats)。"""
    features, span, diagonal = build_features(armature)
    if not features:
        return {}, [], {}

    candidates = []
    best_scores = {}
    for field in FIELD_ORDER:
        if field == "breast_parent_bone":
            continue
        field_candidates = []
        for feature in features.values():
            candidate = _score_candidate(field, feature, span, diagonal)
            if candidate and candidate["score"] >= MIN_CANDIDATE_SCORE:
                field_candidates.append(candidate)
        field_candidates.sort(key=lambda c: c["score"], reverse=True)
        if field_candidates:
            best_scores[field] = field_candidates[0]["score"]
        candidates.extend(field_candidates[:6])

    # 同分时优先具体骨骼字段（下半身优先于腰），避免 Hips 被腰抢占
    priority = {"lower_body_bone": 2, "hip_bone": 1}

    def sort_key(candidate):
        return (round(candidate["score"], 4), priority.get(candidate["field"], 0))

    candidates.sort(key=sort_key, reverse=True)
    assignments = {}
    used_bones = set()

    for candidate in candidates:
        field = candidate["field"]
        bone = candidate["bone"]
        if field in assignments or bone in used_bones:
            continue
        if not _chain_ok(field, bone, assignments, features):
            continue
        assignments[field] = candidate
        used_bones.add(bone)

    # 主链补全：父骨已确定、子字段为空时，只在后代中寻找
    for parent_field, child_field in CHAIN_PAIRS:
        if child_field in assignments or parent_field not in assignments:
            continue
        if child_field.startswith("upper_body"):
            continue  # 由上半身链单独处理
        parent_bone = assignments[parent_field]["bone"]
        best = None
        for bone_name in _descendants(features, parent_bone):
            if bone_name in used_bones:
                continue
            candidate = _score_candidate(child_field, features[bone_name], span, diagonal)
            if not candidate or candidate["score"] < CONFIDENCE_THRESHOLD:
                continue
            if not _chain_ok(child_field, bone_name, assignments, features):
                continue
            if best is None or candidate["score"] > best["score"]:
                best = candidate
        if best:
            assignments[child_field] = best
            used_bones.add(best["bone"])

    # 上半身 2~5：沿 首 -> 上半身 的父链推导
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
        for index, field in enumerate(
                ["upper_body2_bone", "upper_body3_bone",
                 "upper_body4_bone", "upper_body5_bone"]):
            if index >= len(chain):
                break
            if field in assignments or chain[index] in used_bones:
                continue
            assignments[field] = {
                "field": field,
                "bone": chain[index],
                "score": 0.9,
                "parts": {"name": 0.0, "topology": 1.0,
                          "geometry": 1.0, "weight": 0.0},
                "derived": "upper_body_chain",
            }
            used_bones.add(chain[index])

    # 左右镜像校验：成对字段要求局部 X 相反且镜像误差小
    low_conf = []
    for left_field in [f for f in FIELD_ORDER if f.startswith("left_")]:
        right_field = "right_" + left_field[len("left_"):]
        if left_field not in assignments or right_field not in assignments:
            continue
        left = assignments[left_field]
        right = assignments[right_field]
        left_head = features[left["bone"]].head
        right_head = features[right["bone"]].head
        mirrored = Vector((-right_head.x, right_head.y, right_head.z))
        error = (left_head - mirrored).length / span if span else 1.0
        if error > MIRROR_TOLERANCE:
            drop = left if left["score"] <= right["score"] else right
            assignments.pop(drop["field"], None)
            low_conf.append((drop["field"], drop["score"],
                             "左右镜像误差过大"))

    # 低置信度字段：只报告“存在候选但分数不足”的字段，完全没有候选的
    # 字段（模型缺该骨）不打扰用户
    reported = {item[0] for item in low_conf}
    for field in FIELD_ORDER:
        if field == "breast_parent_bone" or field in assignments:
            continue
        if field in reported:
            continue
        best = best_scores.get(field, 0.0)
        if best >= 0.45:
            # 最佳候选分够高却仍为空，通常是骨骼被更高优先字段占用或链约束冲突
            reason = ("候选骨骼已被其它字段占用或约束冲突"
                      if best >= CONFIDENCE_THRESHOLD else "置信度低于阈值")
            low_conf.append((field, best, reason))

    filled = {f: c for f, c in assignments.items()
              if c["score"] >= CONFIDENCE_THRESHOLD}
    for field in list(assignments.keys()):
        if field not in filled:
            if field not in reported:
                low_conf.append((field, assignments[field]["score"],
                                 "置信度低于阈值"))
            assignments.pop(field)

    stats = {
        "bone_count": len(features),
        "filled": len(filled),
        "low_conf": len(low_conf),
        "average": (sum(c["score"] for c in filled.values()) / len(filled)
                    if filled else 0.0),
    }
    return filled, low_conf, stats
