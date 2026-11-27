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


def _pick_up_axis(bones):
    """选择骨骼包围盒跨度最大的轴作为高度轴（兼容横躺模型）。"""
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
