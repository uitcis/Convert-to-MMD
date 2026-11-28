"""自动骨骼映射的 Blender 侧特征提取。

打分与约束求解已抽到 mapping_core.py（不依赖 bpy，可独立测试）。
本模块只负责从骨架/网格提取特征，并把求解结果交回调用方。
"""

import re

import bpy

from . import mapping_core as core

FIELD_ORDER = core.FIELD_ORDER
field_label = core.field_label
CONFIDENCE_THRESHOLD = core.CONFIDENCE_THRESHOLD
MIN_CANDIDATE_SCORE = core.MIN_CANDIDATE_SCORE
MIRROR_TOLERANCE = core.MIRROR_TOLERANCE

# 供外部核对当前口径：原始贡献分 / 合计 1.20
EVIDENCE_WEIGHTS = {
    "name": core.NAME_EXACT / core.RAW_TOTAL,
    "topology": core.TOPO_MAX / core.RAW_TOTAL,
    "geometry_side": core.SIDE_MAX / core.RAW_TOTAL,
    "geometry_height": core.HEIGHT_MAX / core.RAW_TOTAL,
    "geometry_direction": core.DIRECTION_MAX / core.RAW_TOTAL,
    "weight_max": core.WEIGHT_MAX / core.RAW_TOTAL,
}


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


class _HeadOnly:
    """给左右配对判定用的轻量代理：只需要 head 坐标。"""

    __slots__ = ("head",)

    def __init__(self, head):
        self.head = head


class _GeoNode:
    """给几何身体划分用的轻量代理：head/tail/父子/深度/骨长。"""

    __slots__ = ("name", "head", "tail", "parent", "children", "depth",
                 "length")


def _geo_up_axis(bones):
    """用几何身体划分定高度轴，返回 (axis, up_vector) 或 None。

    腿是人形自带的铅垂线：找两条互相平行、垂得最远的分支，其平均方向
    取反就是「上」。这比 `_pick_up_axis` 的「配对中点分布最广」多一层
    解剖证据——后者依赖「肩肘髋踝沿身高排开」，站架/坐姿下会被前后跨度
    干扰（DNF 全骨点云 PCA 的 up 偏 18°）。

    只在解析成功且高置信时采信，并且要求「上」足够贴近某条坐标轴
    （|分量| ≥ 0.9），否则返回 None 让调用方回退原判据——45° 旋转的
    骨架用轴索引表达不了，硬取会退化成掷硬币。
    """
    if len(bones) < 8:
        return None
    nodes = {}
    for bone in bones:
        node = _GeoNode()
        node.name = bone.name
        node.head = tuple(bone.head_local)
        node.tail = tuple(bone.tail_local)
        node.parent = bone.parent.name if bone.parent else None
        node.children = []
        node.depth = 0
        node.length = (bone.tail_local - bone.head_local).length
        nodes[bone.name] = node
    for node in nodes.values():
        if node.parent in nodes:
            nodes[node.parent].children.append(node.name)
    for node in nodes.values():
        depth, current = 0, node.parent
        while current in nodes:
            depth += 1
            current = nodes[current].parent
        node.depth = depth
    try:
        plan = core.parse_body_plan(nodes)
    except Exception:                                   # noqa: BLE001
        return None
    if not plan or not plan["confident"]:
        return None
    up = plan["up"]
    axis = max(range(3), key=lambda i: abs(up[i]))
    if abs(up[axis]) < 0.9:
        return None
    return axis, up


def _pick_up_axis(bones, from_pairs_only=False):
    """选择骨骼的高度轴（兼容横躺/侧躺模型）。

    旧判据是「根骨沿唯一子骨链的跨度最大」，但骨架在根骨处就分叉时
    （hip 直接分出脊柱与两条腿），唯一子骨链长度只有 1、跨度全为 0，
    于是回退到包围盒——而张开的双臂会把 X 撑成最大跨度。实测服装子
    骨架 XF-dForce / Cute Casual Top 因此把 up 判成 X，高度带全部失效。

    新判据只用**左右配对骨**这一组证据，同时定出两个轴：
      side 轴 = 左右骨坐标差最大的轴（左右一定是这条轴分开的）；
      up   轴 = 每对中点分布最广的轴（肩/肘/髋/踝沿身高排开），排除 side。
    两者互斥且来自同一组证据，不会出现 up == side（leviathan 实测
    up=X、side=X，全盘错位）。配对不足时才回退到主链跨度 / 包围盒。

    from_pairs_only=True 时，配对证据不足直接返回 None，把后面两条弱判据
    （主链跨度 / 包围盒）留给调用方决定要不要用——build_features 在这种情况下
    会先试几何身体划分（腿的方向），比「包围盒最大的轴」可靠得多。
    """
    heads = {bone.name: _HeadOnly(bone.head_local) for bone in bones}
    side_axis = core.detect_side_axis(heads) if heads else None
    if heads and side_axis is not None:
        depths = {}
        for bone in bones:
            depth = 0
            current = bone.parent
            while current is not None:
                depth += 1
                current = current.parent
            depths[bone.name] = depth
        pairs = []
        for left_name, right_name in core._named_side_pairs(
                heads, include_middle=True):
            if left_name not in heads or right_name not in heads:
                continue
            depth = (depths.get(left_name, 0) + depths.get(right_name, 0)) * 0.5
            pairs.append((depth, heads[left_name].head, heads[right_name].head))
        if len(pairs) >= 3:
            # 只用**浅层配对**：肩/肘/髋/膝/踝沿身高排开，能代表身体主轴；
            # 手指是最深的一批，A-pose 下五指向前张开，中点沿前后轴散得
            # 比肩到踝还宽——不过滤会把 DNF 的高度轴判成 Y（实测 center
            # 骨全体填进马尾，链断 0→2）。取深度不深于中位数的那一半。
            pairs.sort(key=lambda item: item[0])
            keep = pairs[:max(3, len(pairs) // 2)]
            midpoints = [((l[0] + r[0]) * 0.5, (l[1] + r[1]) * 0.5,
                          (l[2] + r[2]) * 0.5) for _d, l, r in keep]
            others = [axis for axis in range(3) if axis != side_axis]
            spreads = {axis: max(p[axis] for p in midpoints)
                       - min(p[axis] for p in midpoints) for axis in others}
            best = max(others, key=lambda axis: spreads[axis])
            if spreads[best] > 0:
                return best

    if from_pairs_only:
        return None

    children = {}
    for bone in bones:
        children.setdefault(bone.parent.name if bone.parent else "", [])
        if bone.parent is not None:
            children[bone.parent.name].append(bone.name)

    def chain_length(start):
        """从 start 出发，沿唯一子骨走到底，统计经过的骨数。"""
        count = 0
        current = start
        seen = set()
        while current and current not in seen:
            seen.add(current)
            count += 1
            kids = children.get(current, [])
            if len(kids) != 1:
                break
            current = kids[0]
        return count

    roots = [b.name for b in bones if b.parent is None]
    lengths = [0, 0, 0]
    for axis in range(3):
        # 每个轴上各条主链的长度取最大
        best = 0
        for root in roots:
            best = max(best, chain_length(root))
        lengths[axis] = best
    # 三轴的主链长度相同（链与轴无关），所以改用「主链在该轴上的
    # 坐标跨度」：身高方向上脊柱首尾落差最大。
    spans = []
    for axis in range(3):
        widest = 0.0
        for root in roots:
            coords = []
            current = root
            seen = set()
            while current and current not in seen:
                seen.add(current)
                node = next((b for b in bones if b.name == current), None)
                if node is None:
                    break
                coords.append(node.head_local[axis])
                kids = children.get(current, [])
                if len(kids) != 1:
                    break
                current = kids[0]
            if len(coords) >= 2:
                widest = max(widest, max(coords) - min(coords))
        spans.append(widest)
    best = max(range(3), key=lambda i: spans[i])
    if spans[best] > 0:
        return best
    coords = [b.head_local for b in bones]
    extents = [max(c[i] for c in coords) - min(c[i] for c in coords)
               for i in range(3)]
    return max(range(3), key=lambda i: extents[i])


detect_side_axis = core.detect_side_axis


def build_features(armature):
    """返回 (features, span, diagonal, z_min, up_axis)。"""
    bones = [b for b in armature.data.bones if b.name]
    # 过滤工具生成的辅助骨
    bones = [b for b in bones
             if not re.search(r"(_dummy_|_shadow_|\.L\.\d+$)", b.name)]
    if not bones:
        return {}, 0.0, 0.0, 0.0, 2

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

    up_axis = _pick_up_axis(bones, from_pairs_only=True)
    if up_axis is None:
        # 配对证据不足（命名自由 / 服装子骨架 / 只有半身）：先试几何身体
        # 划分——腿的平均方向就是「上」，比「主链跨度最大」和「包围盒最大」
        # 这两条弱判据可靠。解析不出人形再退回原判据，保持原有行为。
        geo = _geo_up_axis(bones)
        up_axis = geo[0] if geo is not None else _pick_up_axis(bones)
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
        mins = tuple(min(p[i] for p in pts) for i in range(3))
        maxs = tuple(max(p[i] for p in pts) for i in range(3))
        diagonal = sum((maxs[i] - mins[i]) ** 2 for i in range(3)) ** 0.5
    return features, span, diagonal, z_min, up_axis


def solve_mapping(armature):
    """执行特征提取与方案 C 求解，返回 (assignments, low_conf, stats)。"""
    features, span, diagonal, z_min, up_axis = build_features(armature)
    if not features:
        return {}, [], {}
    side_axis = detect_side_axis(features, up_axis)
    return core.solve(FIELD_ORDER, features, span, diagonal, z_min,
                      up_axis, side_axis)


def invalidate_preset_cache():
    """预设导入后由操作符调用。"""
    core.invalidate_preset_cache()
