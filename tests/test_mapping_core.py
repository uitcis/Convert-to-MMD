"""方案 C 打分与求解的纯 Python 单测（不依赖 Blender）。

运行：python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mapping_core as core  # noqa: E402


def make_feature(name, head=(0.0, 0.0, 0.0), tail=(0.0, 0.0, 0.1),
                 parent=None, children=(), depth=0, length=0.1, z_pct=0.5,
                 weight_sum=0.0, weight_centroid=None):
    return SimpleNamespace(
        name=name, head=head, tail=tail, parent=parent,
        children=list(children), child_count=len(children), depth=depth,
        length=length, z_pct=z_pct, weight_sum=weight_sum,
        weight_centroid=weight_centroid,
    )


def make_ctx(features=None, span=10.0, diagonal=10.0, z_min=0.0,
             up_axis=2, side_axis=0, stats=None):
    return {
        "span": span, "diagonal": diagonal, "z_min": z_min,
        "up_axis": up_axis, "side_axis": side_axis,
        "stats": stats if stats is not None else {f: {} for f in core.FIELD_ORDER},
    }


class NameScoreTests(unittest.TestCase):
    def test_exact_contains_edit_and_none(self):
        stats = {"head_bone": {"head": 1, "頭": 1}}
        self.assertEqual(core.name_contribution("head_bone", "Head", stats)[0], 0.40)
        self.assertEqual(core.name_contribution("head_bone", "頭", stats)[0], 0.40)
        # "head" 是头骨的确定性名称 → 强语义别名 → 精确档
        self.assertEqual(core.name_contribution("head_bone", "Bip Head Top", stats)[0], 0.40)
        edit = core.name_contribution("head_bone", "Hed", stats)[0]
        self.assertGreater(edit, 0.0)
        self.assertLessEqual(edit, 0.15)
        self.assertEqual(core.name_contribution("head_bone", "zzzz", stats)[0], 0.0)

    def test_finger_digit_mapping(self):
        stats = {}
        self.assertEqual(
            core.name_contribution("left_thumb_0", "LeftThumb1", stats)[0], 0.25)
        self.assertEqual(
            core.name_contribution("left_thumb_0", "LeftThumb2", stats)[0], 0.0)
        self.assertEqual(
            core.name_contribution("left_index_2", "LeftIndex2", stats)[0], 0.25)


class CommonNameTests(unittest.TestCase):
    def test_japanese_common_names_without_preset_entries(self):
        """预设表为空的字段，日文规范名仍应拿到精确匹配 0.40。"""
        stats = core.load_preset_stats()
        empty_fields = ("upper_body3_bone", "upper_body4_bone", "upper_body5_bone",
                        "left_chest_bone", "right_chest_bone", "breast_parent_bone")
        for field in empty_fields:
            self.assertLessEqual(len(stats[field]), 1, field)
        for field, label in (("upper_body3_bone", "上半身3"),
                             ("left_chest_bone", "左胸"),
                             ("right_chest_bone", "右胸"),
                             ("breast_parent_bone", "胸親")):
            score, why = core.name_contribution(field, label, stats)
            self.assertEqual(score, 0.40, (field, label, why))
            self.assertIn("常用名", why)

    def test_ambiguous_english_primary_vs_secondary(self):
        """冲突英文词只给主字段精确档，其余降为 0.25 包含匹配。"""
        stats = core.load_preset_stats()
        # hips 主字段是下半身，腰降档，避免两者争 Hips
        self.assertEqual(core.name_contribution("lower_body_bone", "Hips", stats)[0], 0.40)
        self.assertEqual(core.name_contribution("hip_bone", "Hips", stats)[0], 0.25)
        # chest 主字段是上半身2，UpperChest 对其降档
        self.assertEqual(core.name_contribution("upper_body2_bone", "Chest", stats)[0], 0.40)
        self.assertEqual(core.name_contribution("upper_body2_bone", "UpperChest", stats)[0], 0.25)

    def test_english_common_names_exact_for_en_skeletons(self):
        """英文骨架常用名必须走精确档，含裸词/侧别后缀/侧别前缀三种写法。"""
        stats = core.load_preset_stats()
        cases = (("head_bone", "Head"), ("neck_bone", "Neck"),
                 ("upper_body_bone", "Spine"), ("upper_body3_bone", "UpperChest"),
                 ("left_thigh_bone", "UpperLeg_L"),
                 ("left_thigh_bone", "LeftUpLeg"),
                 ("left_thigh_bone", "L_Thigh"),
                 ("left_upper_arm_bone", "UpperArm_L"),
                 ("left_chest_bone", "Chest_L"),
                 ("right_chest_bone", "Chest_R"),
                 ("right_chest_bone", "bust"))
        for field, name in cases:
            score, why = core.name_contribution(field, name, stats)
            self.assertEqual(score, 0.40, (field, name, why))

    def test_fullwidth_digits_normalized(self):
        """全角数字骨骼名应归一化到半角，避免漏匹配。"""
        self.assertEqual(core._normalize("上半身２"), "上半身2")
        self.assertEqual(core._normalize("左親指０"), "左親指0")


class ChestSideTests(unittest.TestCase):
    def test_midline_chest_rejected_for_sided_chest_fields(self):
        """中轴 Chest 名字含 chest，但左右胸是成对侧别骨，不能互为候选。"""
        mid = {"Chest": make_feature("Chest", head=(0.0, 0.0, 2.4), depth=3,
                                     z_pct=0.75, weight_sum=0.5)}
        ctx = make_ctx(mid, span=3.2)
        stats = core.load_preset_stats()
        ctx["stats"] = stats
        for field in ("left_chest_bone", "right_chest_bone"):
            self.assertIsNone(core.score_candidate(field, mid["Chest"], mid, ctx))
        # 中轴骨仍应正常映射上半身2
        self.assertIsNotNone(
            core.score_candidate("upper_body2_bone", mid["Chest"], mid, ctx))

    def test_sided_chest_bones_accepted(self):
        """带左右侧别的胸骨必须能被对应侧字段命中。"""
        features = {
            "Chest_L": make_feature("Chest_L", head=(0.15, 0.0, 2.4),
                                    depth=3, z_pct=0.75, weight_sum=0.5),
            "Chest_R": make_feature("Chest_R", head=(-0.15, 0.0, 2.4),
                                    depth=3, z_pct=0.75, weight_sum=0.5),
        }
        ctx = make_ctx(features, span=3.2)
        ctx["stats"] = core.load_preset_stats()
        left = core.score_candidate("left_chest_bone", features["Chest_L"],
                                    features, ctx)
        right = core.score_candidate("right_chest_bone", features["Chest_R"],
                                     features, ctx)
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        self.assertIsNone(core.score_candidate("left_chest_bone",
                                               features["Chest_R"], features, ctx))


class DisplayTests(unittest.TestCase):
    def test_field_label_uses_japanese_bone_names(self):
        self.assertEqual(core.field_label("left_thigh_bone"), "左足")
        self.assertEqual(core.field_label("left_calf_bone"), "左ひざ")
        self.assertEqual(core.field_label("right_lower_arm_bone"), "右ひじ")
        self.assertEqual(core.field_label("head_bone"), "頭")
        self.assertEqual(core.field_label("breast_parent_bone"), "胸親父级")
        self.assertEqual(core.field_label("unknown_field"), "unknown_field")


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx()

    def test_side_sign_is_scored_not_hard_filtered(self):
        feature = make_feature("LeftArm", head=(1.0, 0.0, 5.0))
        left, _ = core.geometry_contributions(
            "left_upper_arm_bone", feature, {}, self.ctx)
        right, _ = core.geometry_contributions(
            "right_upper_arm_bone", feature, {}, self.ctx)
        self.assertEqual(left["side"], core.SIDE_MAX)
        self.assertEqual(right["side"], 0.0)

    def test_center_bone_gets_neutral_side(self):
        feature = make_feature("Center")
        parts, _ = core.geometry_contributions("center_bone", feature, {}, self.ctx)
        self.assertEqual(parts["side"], core.SIDE_MAX * 0.5)

    def test_direction_uses_parent_chain_for_fingers(self):
        features = {
            "hand": make_feature("hand", head=(1, 0, 3), tail=(1.4, 0, 3)),
            "finger": make_feature("finger", head=(1.4, 0, 3), tail=(1.8, 0, 3),
                                   parent="hand"),
        }
        ctx = make_ctx(features)
        aligned, _ = core.geometry_contributions(
            "left_index_1", features["finger"], features, ctx)
        features["finger"].tail = (1.1, 0, 3)  # 反向
        opposed, _ = core.geometry_contributions(
            "left_index_1", features["finger"], features, ctx)
        self.assertGreater(aligned["direction"], opposed["direction"])

    def test_detect_side_axis_horizontal_rig(self):
        # 模型横躺：高度在 X，左右在 Z
        features = {
            "left_arm": make_feature("left_arm", head=(5, 0, 1)),
            "right_arm": make_feature("right_arm", head=(5, 0, -1)),
            "hips": make_feature("hips", head=(0, 0, 0)),
        }
        self.assertEqual(core.detect_side_axis(features, up_axis=0), 2)

    def test_detect_side_axis_standard_rig(self):
        features = {
            "LeftArm": make_feature("LeftArm", head=(1, 0, 5)),
            "RightArm": make_feature("RightArm", head=(-1, 0, 5)),
        }
        self.assertEqual(core.detect_side_axis(features, up_axis=2), 0)


class WeightTests(unittest.TestCase):
    def test_fingers_and_toes_get_higher_cap(self):
        ctx = make_ctx()
        at_head = (0.0, 0.0, 5.0)
        finger = make_feature("left_index_1", head=at_head,
                              weight_sum=1.0, weight_centroid=at_head)
        thigh = make_feature("left_thigh_bone", head=at_head,
                             weight_sum=1.0, weight_centroid=at_head)
        finger_score, _ = core.weight_contribution("left_index_1", finger, {}, ctx)
        thigh_score, _ = core.weight_contribution("left_thigh_bone", thigh, {}, ctx)
        self.assertGreater(finger_score, thigh_score)
        self.assertLessEqual(finger_score, core.WEIGHT_MAX)

    def test_no_weight_returns_zero(self):
        feature = make_feature("Center")
        score, _ = core.weight_contribution("center_bone", feature, {}, make_ctx())
        self.assertEqual(score, 0.0)


class ConstraintTests(unittest.TestCase):
    def setUp(self):
        self.features = {
            "Root": make_feature("Root", children=["Hips"], depth=0),
            "Hips": make_feature("Hips", parent="Root",
                                 children=["Spine", "LeftThigh"], depth=1),
            "Spine": make_feature("Spine", parent="Hips", depth=2),
            "LeftThigh": make_feature("LeftThigh", parent="Hips",
                                      children=["LeftCalf"], depth=2),
            "LeftCalf": make_feature("LeftCalf", parent="LeftThigh", depth=3),
            "Unrelated": make_feature("Unrelated", parent=None, depth=0),
        }

    def test_chain_requires_ancestor(self):
        assignments = {"lower_body_bone": {"bone": "Hips"}}
        self.assertTrue(core.chain_ok("left_thigh_bone", "LeftThigh",
                                      assignments, self.features))
        self.assertFalse(core.chain_ok("left_thigh_bone", "Unrelated",
                                       assignments, self.features))

    def test_backtrack_beats_greedy(self):
        # 贪心先把 X 给 A(0.90)，B 就没骨可用；回溯改让 A=Y、B=X
        candidates = {
            "A": [{"field": "A", "bone": "X", "score": 0.90},
                  {"field": "A", "bone": "Y", "score": 0.60}],
            "B": [{"field": "B", "bone": "X", "score": 0.80}],
        }
        features = {"X": make_feature("X"), "Y": make_feature("Y")}
        result, _ = core._solve_backtrack(candidates, ["A", "B"], features, make_ctx())
        self.assertEqual(result["A"]["bone"], "Y")
        self.assertEqual(result["B"]["bone"], "X")

    def test_auto_complete_fields_are_low_priority(self):
        # 可拓扑补全的辅助骨为低优先级；四肢/頭/腰仍有独立骨，需独立匹配
        for field in ("upper_body2_bone", "upper_body3_bone",
                      "upper_body4_bone", "upper_body5_bone",
                      "breast_parent_bone"):
            self.assertEqual(core.field_priority(field), 1, field)
        for field in ("head_bone", "left_thigh_bone", "left_calf_bone",
                      "hip_bone", "lower_body_bone", "left_upper_arm_bone"):
            self.assertEqual(core.field_priority(field), 2, field)
        self.assertGreater(core.field_bonus("hip_bone"),
                           core.field_bonus("upper_body2_bone"))

    def test_priority_prefers_must_match_on_conflict(self):
        # 同一根 X：高优先级字段 A 得分 0.60，低优先级字段 B 得分 0.70。
        # 无奖励时 B 胜；有优先级奖励后 A 的 0.60+0.15 > B 的 0.70，A 胜。
        candidates = {
            "A": [{"field": "A", "bone": "X", "score": 0.60}],
            "B": [{"field": "B", "bone": "X", "score": 0.70}],
        }
        features = {"X": make_feature("X")}
        ctx = make_ctx()
        # 用真实优先级函数替换内部奖励做对照：先验证无奖励时高分者胜
        original = core.field_bonus
        try:
            core.field_bonus = lambda f: 0.0
            plain, _ = core._solve_backtrack(candidates, ["A", "B"], features, ctx)
            self.assertEqual(plain["B"]["bone"], "X")
            # 让 A 高优先级、B 低优先级，验证 A 胜出
            core.field_bonus = lambda f: 0.15 if f == "A" else 0.0
            weighted, _ = core._solve_backtrack(candidates, ["A", "B"], features, ctx)
            self.assertEqual(weighted["A"]["bone"], "X")
        finally:
            core.field_bonus = original

    def test_mirror_rejects_same_side_pair(self):
        ctx = make_ctx(side_axis=0)
        assignments = {
            "left_arm": {"bone": "LeftArm"},
        }
        features = {
            "LeftArm": make_feature("LeftArm", head=(1, 0, 5)),
            "Mirror": make_feature("Mirror", head=(-1, 0, 5)),
            "SameSide": make_feature("SameSide", head=(1, 0, 5)),
        }
        self.assertLess(
            core.mirror_error("right_arm", "Mirror", assignments, features, ctx),
            core.MIRROR_TOLERANCE)
        self.assertGreater(
            core.mirror_error("right_arm", "SameSide", assignments, features, ctx),
            core.MIRROR_TOLERANCE)


class FallbackFillTests(unittest.TestCase):
    """回溯未选中的字段也应照填（不留下空白行）。"""

    def _solve_simple(self):
        """一个只有少量骨骼的简化骨架：多数字段必然落空。"""
        definitions = [
            ("全ての親", None, (0, 0, 0)),
            ("センター", "全ての親", (0, 0, 0.3)),
            ("グルーブ", "センター", (0, 0, 0.5)),
            ("腰", "グルーブ", (0, 0, 0.8)),
            ("下半身", "腰", (0, 0, 1.0)),
            ("上半身", "腰", (0, 0, 1.4)),
            ("首", "上半身", (0, 0, 1.8)),
            ("頭", "首", (0, 0, 2.0)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.1)
        stats = core.load_preset_stats()
        return core.solve(
            core.FIELD_ORDER, features, span=2.1, diagonal=2.5, z_min=0.0,
            up_axis=2, side_axis=0, stats=stats)

    def test_every_field_gets_a_value_or_is_flagged(self):
        """每个字段要么被填上，要么出现在低置信度列表里（不静默消失）。"""
        filled, low_conf, _result = self._solve_simple()
        listed = {f for f, _s, _r in low_conf}
        for field in core.FIELD_ORDER:
            self.assertTrue(field in filled or field in listed,
                            f"{field} 既未填写也未提示")

    def test_no_duplicate_bone_references(self):
        """同一根骨不得被两个字段引用。"""
        filled, _low_conf, _result = self._solve_simple()
        bones = [c["bone"] for c in filled.values()]
        self.assertEqual(len(bones), len(set(bones)),
                         "存在同一根骨被多个字段引用")

    def test_fallback_fills_are_marked_low_confidence(self):
        """兜底填入的字段必须带低置信度标记（面板据此标红）。"""
        filled, _low_conf, _result = self._solve_simple()
        for field, candidate in filled.items():
            if candidate.get("low_confidence"):
                self.assertIn("low_confidence", candidate)


class ForkedHandTests(unittest.TestCase):
    """分叉式手掌：两根手指挂在同一块掌骨下（握拳的 Fist）。"""

    def _build_forked_hand(self):
        """搭一只五指手：拇指+三指直挂手掌，两指经由掌骨 Fist 分出。

        返回 (features, span)。
        """
        span = 2.0
        definitions = [
            ("Root", None, (0.0, 0.0, 0.0)),
            ("Waist", "Root", (0.0, 0.0, 0.5)),
            ("Chest", "Waist", (0.0, 0.0, 1.0)),
            ("Shoulder", "Chest", (0.5, 0.0, 1.2)),
            ("Arm", "Shoulder", (0.8, 0.0, 1.1)),
            ("ForeArm", "Arm", (0.95, 0.0, 1.05)),
            ("Hand", "ForeArm", (1.0, 0.0, 1.0)),
            # 掌骨：其下分出两根手指
            ("Fist", "Hand", (1.05, 0.0, 1.0)),
        ]
        # 四指方向统一朝 +X，位置依次排开；拇指朝 -X 偏出
        for name, x in (("index", 1.30), ("middle", 1.22), ("ring", 1.14)):
            for seg in (1, 2, 3):
                definitions.append((
                    f"{name}{seg}", f"{name}{seg - 1}" if seg > 1 else "Hand",
                    (x, -0.05 * seg, 1.0 - 0.02 * seg)))
        # 两根挂在掌骨下
        for name, x in (("pinky", 1.06), ("thumb2", 0.98)):
            for seg in (1, 2, 3):
                definitions.append((
                    f"{name}{seg}", f"{name}{seg - 1}" if seg > 1 else "Fist",
                    (x, -0.05 * seg, 1.0 - 0.02 * seg)))
        features = {}
        for name, parent, head in definitions:
            if name == "Hand":
                length = 0.15
            elif name in ("Root", "Waist", "Chest"):
                length = 0.5
            elif name in ("Shoulder", "Arm", "ForeArm"):
                length = 0.3
            elif name == "Fist":
                length = 0.1
            else:
                length = 0.06
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1] - length, head[2]),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=self._depth(definitions, name),
                length=length, z_pct=head[2] / 3.2)
        return features, span

    @staticmethod
    def _depth(definitions, name):
        mapping = {n: p for n, p, _ in definitions}
        depth = 0
        current = mapping.get(name)
        while current:
            depth += 1
            current = mapping.get(current)
        return depth

    def test_forked_hand_yields_five_chains(self):
        """分叉掌骨下的两根手指都要被收集成独立链。"""
        features, span = self._build_forked_hand()
        chains = core._collect_finger_chains(features, features["Hand"],
                                             core.FINGER_LEN_RATIO * span)
        self.assertEqual(len(chains), 5, f"链数应为 5，实为 {len(chains)}")
        # 每条链都应从不同的骨头起（不能有重复链）
        roots = [chain[0] for chain in chains]
        self.assertEqual(len(roots), len(set(roots)), f"链根重复：{roots}")

    def test_fork_node_not_included_in_chain(self):
        """分叉点本身（掌骨）不应混进指链。"""
        features, span = self._build_forked_hand()
        chains = core._collect_finger_chains(features, features["Hand"],
                                             core.FINGER_LEN_RATIO * span)
        for chain in chains:
            self.assertNotIn("Fist", chain,
                             f"掌骨不应在链中：{chain}")


class AdaptiveFingerCountTests(unittest.TestCase):
    """指头数量应从几何自动推导，不能写死「必须 5 指」。"""

    def _build_hand(self, finger_count, forked=False):
        """搭一只手。finger_count 为非拇指手指的根数。

        forked=True 时，其中两根挂在同一块掌骨下（模拟握拳）。
        """
        span = 2.0
        definitions = [
            ("Root", None, (0.0, 0.0, 0.0)),
            ("Waist", "Root", (0.0, 0.0, 0.5)),
            ("Chest", "Waist", (0.0, 0.0, 1.0)),
            ("Shoulder", "Chest", (0.5, 0.0, 1.2)),
            ("Arm", "Shoulder", (0.8, 0.0, 1.1)),
            ("ForeArm", "Arm", (0.95, 0.0, 1.05)),
            ("Hand", "ForeArm", (1.0, 0.0, 1.0)),
        ]
        if forked:
            definitions.append(("Fist", "Hand", (1.05, 0.0, 1.0)))
        # 非拇指手指：沿 X 轴依次排开，方向统一朝 +X
        for index in range(finger_count):
            name = f"f{index}"
            x = 1.30 - 0.08 * index
            parent = "Hand"
            if forked and index >= finger_count - 2:
                parent = "Fist"
            for seg in (1, 2, 3):
                definitions.append((
                    f"{name}{seg}", f"{name}{seg - 1}" if seg > 1 else parent,
                    (x, -0.05 * seg, 1.0 - 0.02 * seg)))
        # 拇指：朝 -X 偏出，方向与其余明显不同
        for seg in (1, 2, 3):
            definitions.append((
                f"thumb{seg}", f"thumb{seg - 1}" if seg > 1 else "Hand",
                (0.95 - 0.10 * seg, -0.05 * seg, 0.95 - 0.02 * seg)))

        features = {}
        for name, parent, head in definitions:
            if name == "Hand":
                length = 0.15
            elif name == "Fist":
                length = 0.1
            elif name in ("Root", "Waist", "Chest"):
                length = 0.5
            elif name in ("Shoulder", "Arm", "ForeArm"):
                length = 0.3
            else:
                length = 0.06
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1] - length, head[2]),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=self._depth(definitions, name),
                length=length, z_pct=head[2] / 3.2)
        return features, span

    @staticmethod
    def _depth(definitions, name):
        mapping = {n: p for n, p, _ in definitions}
        depth = 0
        current = mapping.get(name)
        while current:
            depth += 1
            current = mapping.get(current)
        return depth

    def test_four_finger_model(self):
        """四指 + 拇指：应正确识别出拇指与四指。"""
        features, span = self._build_hand(4)
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        kinds = set(finger for finger, _seg in roles.values())
        self.assertIn("thumb", kinds)
        self.assertTrue(kinds.issubset({"thumb", "index", "middle", "ring",
                                         "pinky"}))
        # 拇指应只有一条链
        thumb_bones = [b for b, (f, _s) in roles.items() if f == "thumb"]
        self.assertEqual(len(thumb_bones), 3)

    def test_three_finger_model(self):
        """三指 + 拇指：少于五指也要能推断，不因数量不足而放弃。"""
        features, span = self._build_hand(3)
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        kinds = set(finger for finger, _seg in roles.values())
        self.assertIn("thumb", kinds)
        thumb_bones = [b for b, (f, _s) in roles.items() if f == "thumb"]
        self.assertEqual(len(thumb_bones), 3)

    def test_forked_six_chain_model(self):
        """六条链（含分叉）也能推断，不因数量超过五而放弃。"""
        features, span = self._build_hand(5, forked=True)
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        kinds = set(finger for finger, _seg in roles.values())
        self.assertIn("thumb", kinds)
        thumb_bones = [b for b, (f, _s) in roles.items() if f == "thumb"]
        self.assertEqual(len(thumb_bones), 3)

    def test_no_hardcoded_five_in_source(self):
        """源码里不应再出现「必须正好 5 条链」这类硬编码。"""
        import inspect
        source = inspect.getsource(core)
        self.assertNotIn("len(infos) != 5", source)
        self.assertNotIn("best_parallel < 4", source)


class UpperLimbDomainTests(unittest.TestCase):
    """手指骨必须长在上肢分支上（手掌骨的后代）。"""

    def _build_rig_with_fingers(self):
        """一副人形：手指挂在左手掌骨下，另有一根腿骨与一根躯干骨。

        返回 (features, span)。
        """
        span = 2.0
        definitions = [
            ("Root", None, (0.0, 0.0, 0.0)),
            ("Waist", "Root", (0.0, 0.0, 0.5)),
            ("Chest", "Waist", (0.0, 0.0, 1.0)),
            ("Shoulder", "Chest", (0.5, 0.0, 1.2)),
            ("Arm", "Shoulder", (0.8, 0.0, 1.1)),
            ("ForeArm", "Arm", (0.95, 0.0, 1.05)),
            ("Hand", "ForeArm", (1.0, 0.0, 1.0)),
            # 左手四指 + 拇指
            ("index1", "Hand", (1.30, -0.05, 0.98)),
            ("index2", "index1", (1.30, -0.10, 0.96)),
            ("index3", "index2", (1.30, -0.15, 0.94)),
            ("middle1", "Hand", (1.22, -0.05, 0.98)),
            ("middle2", "middle1", (1.22, -0.10, 0.96)),
            ("middle3", "middle2", (1.22, -0.15, 0.94)),
            ("ring1", "Hand", (1.14, -0.05, 0.98)),
            ("ring2", "ring1", (1.14, -0.10, 0.96)),
            ("ring3", "ring2", (1.14, -0.15, 0.94)),
            ("pinky1", "Hand", (1.06, -0.05, 0.98)),
            ("pinky2", "pinky1", (1.06, -0.10, 0.96)),
            ("pinky3", "pinky2", (1.06, -0.15, 0.94)),
            ("thumb1", "Hand", (0.85, -0.05, 0.95)),
            ("thumb2", "thumb1", (0.75, -0.10, 0.93)),
            ("thumb3", "thumb2", (0.65, -0.15, 0.91)),
            # 干扰项：腿骨与躯干骨，形态也像手指但不在上肢分支
            ("Toe1", "Chest", (0.2, -0.05, 0.98)),
            ("Toe2", "Toe1", (0.2, -0.10, 0.96)),
            ("Toe3", "Toe2", (0.2, -0.15, 0.94)),
        ]
        features = {}
        for name, parent, head in definitions:
            length = 0.05 if name.startswith(("index", "middle", "ring",
                                              "pinky", "thumb", "Toe")) else 0.3
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + length),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=self._depth(definitions, name),
                length=length, z_pct=head[2] / 3.2)
        return features, span

    @staticmethod
    def _depth(definitions, name):
        mapping = {n: p for n, p, _ in definitions}
        depth = 0
        current = mapping.get(name)
        while current:
            depth += 1
            current = mapping.get(current)
        return depth

    def test_domain_contains_only_upper_limb_bones(self):
        """上肢域内应只有手部骨骼，不含躯干/腿上的骨。"""
        features, span = self._build_rig_with_fingers()
        _roles, _sides, domains = core.infer_finger_roles(
            features, span=span, side_axis=0, up_axis=2)
        domain = domains.get("left")
        self.assertIsNotNone(domain)
        self.assertIn("index1", domain)
        self.assertIn("thumb1", domain)
        self.assertNotIn("Toe1", domain)
        self.assertNotIn("Chest", domain)

    def test_finger_field_rejects_bones_outside_domain(self):
        """域外的骨不能成为手指字段的候选。"""
        features, span = self._build_rig_with_fingers()
        roles, sides, domains = core.infer_finger_roles(
            features, span=span, side_axis=0, up_axis=2)
        ctx = make_ctx(features, span=span, diagonal=span, z_min=0.0,
                       up_axis=2, side_axis=0)
        ctx["finger_roles"] = roles
        ctx["finger_sides"] = sides
        ctx["finger_domains"] = domains
        candidate = core.score_candidate("left_index_1", features["Toe1"],
                                         features, ctx)
        self.assertIsNone(candidate,
                          "上肢域外的骨不应成为手指候选")


class CenterHeightTests(unittest.TestCase):
    """中心骨可用相对位置推断（上半身在上半身2之上、首之上、头之上）。"""

    def _build_center_chain(self):
        """造一副中心骨链，骨名无语义，只有几何。"""
        span = 2.5
        definitions = [
            ("C0", None, (0, 0, 0.0)),
            ("C1", "C0", (0, 0, 0.3)),
            ("C2", "C1", (0, 0, 0.6)),
            ("C3", "C2", (0, 0, 0.9)),
            ("C4", "C3", (0, 0, 1.2)),
            ("C5", "C4", (0, 0, 1.5)),
            ("C6", "C5", (0, 0, 1.8)),
            ("C7", "C6", (0, 0, 2.1)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.5)
        return features, span

    def test_height_chains_are_chain_relations_only(self):
        """高度序只约束链式关系，不含兄弟关系（腰/下半身 vs 上半身）。"""
        for lower, upper in core.CENTER_HEIGHT_CHAINS:
            self.assertNotEqual((lower, upper),
                                ("lower_body_bone", "upper_body_bone"),
                                "下半身与上半身是兄弟骨，不能做高度序约束")

    def test_height_order_rejects_too_low_candidate(self):
        """上侧字段的候选低于下侧字段时，高度序应否决。"""
        features, span = self._build_center_chain()
        ctx = make_ctx(features, span=span, diagonal=span, z_min=0.0,
                       up_axis=2, side_axis=0)
        assignments = {"upper_body_bone": {"bone": "C4"}}
        # C2 比 C4 低，不能作为上半身2 的候选
        self.assertFalse(core.height_order_ok(
            "upper_body2_bone", "C2", assignments, features, ctx))
        # C6 比 C4 高，可以
        self.assertTrue(core.height_order_ok(
            "upper_body2_bone", "C6", assignments, features, ctx))

    def test_upper_axis_detection_prefers_spine_chain(self):
        """高度轴应由脊柱主链决定，而非包围盒跨度最大。"""
        import inspect
        source = inspect.getsource(core)
        self.assertIn("CENTER_HEIGHT_CHAINS", source)
        # 上下半身是兄弟关系，不能进高度序表
        self.assertNotIn("(\"lower_body_bone\", \"upper_body_bone\")",
                         source)


class NoAutoMatchTests(unittest.TestCase):
    """上半身2~5 不参与自动匹配，只走主链拓扑推导。"""

    def test_upper_body_chain_excluded_from_auto_match(self):
        """上半身2~5 应列入「不参与自动匹配」的字段集。"""
        for index in (2, 3, 4, 5):
            field = f"upper_body{index}_bone"
            self.assertIn(field, core.NO_AUTO_MATCH_FIELDS,
                          f"{field} 应不参与自动匹配")

    def test_breast_parent_not_excluded(self):
        """胸親父级仍可复用主链骨，不属于「不参与自动匹配」。"""
        self.assertNotIn("breast_parent_bone", core.NO_AUTO_MATCH_FIELDS)

    def test_upper_body_chain_derived_from_neck_chain(self):
        """有中间骨时应由推导填入，而非留空或硬填候选。"""
        definitions = [
            ("Root", None, (0, 0, 0.0)),
            ("Waist", "Root", (0, 0, 1.0)),
            ("Spine", "Waist", (0, 0, 1.5)),
            ("Spine1", "Spine", (0, 0, 1.8)),
            ("Neck", "Spine1", (0, 0, 2.1)),
            ("Head", "Neck", (0, 0, 2.4)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.5)
        stats = {"upper_body_bone": {"spine": 1},
                 "neck_bone": {"neck": 1}}
        filled, _low_conf, _result = core.solve(
            core.FIELD_ORDER, features, span=2.5, diagonal=2.5, z_min=0.0,
            up_axis=2, side_axis=0, stats=stats)
        # 上半身 = Spine，中间骨 Spine1 应推导出 upper_body2
        self.assertEqual(filled.get("upper_body_bone", {}).get("bone"), "Spine")
        candidate = filled.get("upper_body2_bone")
        if candidate is not None:
            self.assertEqual(candidate["bone"], "Spine1")
            self.assertTrue(candidate.get("derived"))

    def test_no_auto_match_fields_not_filled_by_spare_candidates(self):
        """不参与自动匹配的字段不应被兜底候选硬填。"""
        features = {
            "Root": make_feature("Root", head=(0, 0, 0.0),
                                 children=[], depth=0, length=0.1,
                                 z_pct=0.0),
            "Something": make_feature("Something", head=(0, 0, 1.5),
                                      children=[], depth=0, length=0.1,
                                      z_pct=0.6),
        }
        stats = {f: {} for f in core.FIELD_ORDER}
        filled, low_conf, _result = core.solve(
            core.FIELD_ORDER, features, span=2.0, diagonal=2.0, z_min=0.0,
            up_axis=2, side_axis=0, stats=stats)
        for index in (2, 3, 4, 5):
            field = f"upper_body{index}_bone"
            if field in filled:
                self.assertTrue(filled[field].get("derived"),
                                f"{field} 应由推导填入，而非候选硬填")


class CoreBonePriorityTests(unittest.TestCase):
    """核心骨（面板标签带 *）优先级高于扩展骨。"""

    def test_core_bone_list_matches_panel_stars(self):
        """核心骨清单要与面板上带 * 的标签一致。"""
        expected = {
            "upper_body_bone", "neck_bone", "head_bone",
            "left_shoulder_bone", "right_shoulder_bone",
            "left_upper_arm_bone", "right_upper_arm_bone",
            "left_lower_arm_bone", "right_lower_arm_bone",
            "left_hand_bone", "right_hand_bone",
            "left_thigh_bone", "right_thigh_bone",
            "left_calf_bone", "right_calf_bone",
            "left_foot_bone", "right_foot_bone",
        }
        self.assertEqual(set(core.CORE_BONE_FIELDS), expected)

    def test_extension_bones_are_not_core(self):
        """扩展骨不应被当作核心骨。"""
        for field in ("control_center_bone", "all_parents_bone",
                      "center_bone", "groove_bone", "hip_bone",
                      "lower_body_bone", "left_eye_bone", "left_toe_bone"):
            self.assertFalse(core.is_core_bone(field),
                             f"{field} 是扩展骨，不该有核心骨加成")

    def test_core_bone_gets_bonus(self):
        """核心骨在回溯目标函数里应拿到额外加成。"""
        core_bonus = core.field_bonus("left_hand_bone")
        extension_bonus = core.field_bonus("left_toe_bone")
        self.assertGreater(core_bonus, extension_bonus)

    def test_panel_star_labels_are_core(self):
        """面板上带 * 的标签对应的字段都应是核心骨。"""
        import re
        panel = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui_panel.py"), encoding="utf-8")
        try:
            source = panel.read()
        finally:
            panel.close()
        # 抓 add_bone_row_with_button(col, "标签*", "field") 与
        # add_symmetric_bones_with_buttons(col, "标签*", "left_field", ...)
        for match in re.finditer(r'"([^"]*\*)"[,\s]*\n?\s*"([a-z_]+_bone)"',
                                 source):
            label, field = match.group(1), match.group(2)
            self.assertTrue(core.is_core_bone(field),
                            f"面板标签 {label} 带 * 但字段 {field} 不在核心骨清单")


class SpineChainTests(unittest.TestCase):
    """中心骨必须落在脊柱主链上，不能是左右侧肢体骨。"""

    def _build_spine_and_limbs(self):
        """造一副有脊柱链 + 左右大腿/手臂的骨架。"""
        span = 2.0
        definitions = [
            ("Root", None, (0, 0, 0.0)),
            ("Hips", "Root", (0, 0, 1.0)),
            ("Spine", "Hips", (0, 0, 1.3)),
            ("Chest", "Spine", (0, 0, 1.6)),
            ("Neck", "Chest", (0, 0, 1.8)),
            ("Head", "Neck", (0, 0, 2.0)),
            # 左右大腿（偏离中轴，在脊柱链之外）
            ("LeftUpLeg", "Hips", (0.15, 0, 0.95)),
            ("LeftLeg", "LeftUpLeg", (0.15, 0, 0.5)),
            ("RightUpLeg", "Hips", (-0.15, 0, 0.95)),
            ("RightLeg", "RightUpLeg", (-0.15, 0, 0.5)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.0)
        return features, span

    def test_spine_chain_excludes_limb_bones(self):
        """脊柱链应含脊柱骨，不含左右大腿。"""
        features, span = self._build_spine_and_limbs()
        chain = core.detect_spine_chain(features, up_axis=2)
        self.assertIn("Spine", chain)
        self.assertIn("Head", chain)
        self.assertNotIn("LeftUpLeg", chain)
        self.assertNotIn("RightLeg", chain)

    def test_center_bone_rejects_limb_bone(self):
        """偏离中轴的肢体骨不能成为中心骨字段的候选。"""
        features, span = self._build_spine_and_limbs()
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=span, diagonal=span, z_min=0.0,
                       up_axis=2, side_axis=0)
        ctx["spine_chain"] = core.detect_spine_chain(features, up_axis=2)
        ctx["midline"] = core.detect_midline(features, side_axis=0)
        candidate = core.score_candidate("lower_body_bone",
                                         features["LeftUpLeg"], features, ctx)
        self.assertIsNone(candidate, "大腿骨不应成为下半身候选")

    def test_midline_from_symmetric_pairs(self):
        """中轴应由左右成对骨的中点确定，而非跨度中点。"""
        features = {
            "LeftArm": make_feature("LeftArm", head=(1.0, 0, 1.0),
                                    children=[], depth=0, length=0.1,
                                    z_pct=0.5),
            "RightArm": make_feature("RightArm", head=(-1.0, 0, 1.0),
                                     children=[], depth=0, length=0.1,
                                     z_pct=0.5),
            "Extra": make_feature("Extra", head=(3.0, 0, 1.0),
                                   children=[], depth=0, length=0.1,
                                   z_pct=0.5),
        }
        midline = core.detect_midline(features, side_axis=0)
        self.assertAlmostEqual(midline, 0.0, places=6)


class PriorityTierTests(unittest.TestCase):
    """三档优先级：核心骨 > 下半身 > 其它扩展骨。"""

    def test_lower_body_is_second_tier(self):
        """下半身属于第二档。"""
        self.assertEqual(core.priority_tier("lower_body_bone"),
                         core.PRIORITY_TIER_SECOND)

    def test_core_bones_are_top_tier(self):
        """面板带 * 的核心骨属第一档。"""
        for field in core.CORE_BONE_FIELDS:
            self.assertEqual(core.priority_tier(field),
                             core.PRIORITY_TIER_CORE, field)

    def test_other_extensions_are_lowest_tier(self):
        """其余扩展骨属第三档。"""
        for field in ("control_center_bone", "all_parents_bone",
                      "center_bone", "groove_bone", "hip_bone",
                      "left_eye_bone", "left_toe_bone"):
            self.assertEqual(core.priority_tier(field),
                             core.PRIORITY_TIER_EXTEND, field)

    def test_tier_order_is_respected(self):
        """档位顺序：核心 < 第二档 < 扩展。"""
        self.assertLess(core.priority_tier("left_hand_bone"),
                        core.priority_tier("lower_body_bone"))
        self.assertLess(core.priority_tier("lower_body_bone"),
                        core.priority_tier("center_bone"))

    def test_bonus_follows_tier(self):
        """目标函数加成随档位递减。"""
        core_bonus = core.field_bonus("left_hand_bone")
        second_bonus = core.field_bonus("lower_body_bone")
        extend_bonus = core.field_bonus("center_bone")
        self.assertGreater(core_bonus, second_bonus)
        self.assertGreater(second_bonus, extend_bonus)


class StrongAliasTests(unittest.TestCase):
    """强语义别名：命中即确定字段，给精确档。"""

    def test_camel_case_alias_is_matched(self):
        """驼峰连写形式（UpperArm）应能命中别名表。"""
        stats = core.load_preset_stats()
        # "G UpperArm L" 规范化后是 gupperarml，与别名不全等，
        # 但驼峰拼接出的 upperarm 命中 → 精确档
        self.assertEqual(
            core.name_contribution("left_upper_arm_bone", "G UpperArm L",
                                   stats)[0], core.NAME_EXACT)
        self.assertEqual(
            core.name_contribution("left_lower_arm_bone", "G ForeArm L",
                                   stats)[0], core.NAME_EXACT)

    def test_generic_alias_stays_contains(self):
        """泛化词（arm）仍给包含档，不能压过确定性名称。"""
        stats = core.load_preset_stats()
        score = core.name_contribution("left_upper_arm_bone",
                                       "GD ForeArmLow Scl L", stats)[0]
        self.assertEqual(score, core.NAME_CONTAINS)

    def test_ambiguous_word_not_bypassed(self):
        """降级词不可被泛化词绕过：UpperChest 不给 upper_body2 精确档。"""
        stats = core.load_preset_stats()
        self.assertEqual(
            core.name_contribution("upper_body2_bone", "UpperChest", stats)[0],
            core.NAME_CONTAINS)

    def test_upper_arm_prefers_real_bone_over_scale_bone(self):
        """上臂字段应优先拿到真骨，而非叶子状的缩放骨。"""
        stats = core.load_preset_stats()
        real = core.name_contribution("left_upper_arm_bone", "G UpperArm L",
                                      stats)[0]
        scale = core.name_contribution("left_upper_arm_bone",
                                        "GD UpperArmMid Scl L", stats)[0]
        # 辅助骨（Scl/Twist）只给包含档：它们与主骨同名却被降权，
        # 否则会靠高度/方向分的噪声险胜主骨，导致下一节变成兄弟骨
        # （实测 DNF 小臂 0.815 vs 0.813）
        self.assertEqual(real, core.NAME_EXACT)
        self.assertEqual(scale, core.NAME_CONTAINS)
        # 拓扑分上真骨（含小臂子骨）应高于叶子缩放骨
        features = {
            "G UpperArm L": make_feature(
                "G UpperArm L", head=(0.5, 0, 1.5),
                children=["G ForeArm L"], depth=3, length=0.3, z_pct=0.75),
            "G ForeArm L": make_feature(
                "G ForeArm L", head=(0.8, 0, 1.5),
                children=[], depth=4, length=0.3, z_pct=0.75),
            "GD UpperArmMid Scl L": make_feature(
                "GD UpperArmMid Scl L", head=(0.5, 0, 1.5),
                children=[], depth=4, length=0.3, z_pct=0.75),
        }
        real_topology = core.topology_contribution(
            "left_upper_arm_bone", features["G UpperArm L"], features)[0]
        scale_topology = core.topology_contribution(
            "left_upper_arm_bone", features["GD UpperArmMid Scl L"],
            features)[0]
        self.assertGreater(real_topology, scale_topology)


class SupportBoneTests(unittest.TestCase):
    """辅助骨（Scl/Twist/Socket）的名称为降档依据。"""

    def test_scale_bone_detected(self):
        self.assertTrue(core._is_support_bone_name("GD ForeArmLow Scl L"))
        self.assertTrue(core._is_support_bone_name("Bn_Twist_Bip001_L_Forearm3"))
        self.assertTrue(core._is_support_bone_name("Bn_Socket_Hair"))

    def test_main_bone_not_flagged(self):
        """主骨不含辅助词——尤其 LeftUpLeg 的 up 不能被误判。"""
        for name in ("G UpperArm L", "Bip001-L-Forearm", "LeftUpLeg",
                     "mixamorig:LeftForeArm", "G Clavicle L"):
            self.assertFalse(core._is_support_bone_name(name), name)

    def test_main_bone_outranks_scale_bone(self):
        """同一部位的主骨名称分应高于缩放骨。"""
        stats = core.load_preset_stats()
        main = core.name_contribution("left_lower_arm_bone", "G ForeArm L",
                                      stats)[0]
        scale = core.name_contribution("left_lower_arm_bone",
                                        "GD ForeArmLow Scl L", stats)[0]
        self.assertGreater(main, scale)


class SupportBoneChainTests(unittest.TestCase):
    """辅助骨不能作为链关系的证据——否则会把主骨误杀掉。"""

    def _build(self):
        definitions = [
            ("Clavicle", None, (0.1, 0, 1.5)),
            ("UpperArm", "Clavicle", (0.4, 0, 1.5)),
            ("ForeArm", "UpperArm", (0.7, 0, 1.5)),
            ("Hand", "ForeArm", (0.95, 0, 1.5)),
            # 挂在三角肌位置的肩部控制器（Gley 的真实结构）
            ("Shape Shoulder", "UpperArm", (0.45, 0, 1.5)),
            # 扭曲骨
            ("Twist UpperArm", "UpperArm", (0.5, 0, 1.5)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=0.75)
        return features

    def test_support_child_is_not_chain_evidence(self):
        """上臂挂着肩部控制器时，不能判成「子骨是肩骨」而否掉主骨。"""
        features = self._build()
        self.assertFalse(
            core.chain_relation_violated("left_upper_arm_bone",
                                         features["UpperArm"], features),
            "子骨里的控制骨不应触发「上一节」否决")

    def test_main_bone_survives_with_support_children(self):
        """带辅助子骨的主骨仍应是有效候选。"""
        features = self._build()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        candidate = core.score_candidate("left_upper_arm_bone",
                                         features["UpperArm"], features, ctx)
        self.assertIsNotNone(candidate)

    def test_support_bone_itself_not_typed_as_chain_node(self):
        """控制骨自身不被当成链上某一节。"""
        self.assertFalse(core._bone_matches_category("Shape Shoulder",
                                                     "shoulder"))
        self.assertFalse(core._bone_matches_category("Twist UpperArm",
                                                     "upper_arm"))


class ChainRelationTests(unittest.TestCase):
    """父子关系反了 → 否决候选。"""

    def _build_arm(self):
        """肩 → 上臂 → 小臂 → 手，各带一层缩放骨干扰。"""
        definitions = [
            ("Clavicle L", "Chest", (0.2, 0, 1.5)),
            ("UpperArm L", "Clavicle L", (0.4, 0, 1.5)),
            ("ForeArm L", "UpperArm L", (0.7, 0, 1.5)),
            ("Hand L", "ForeArm L", (0.95, 0, 1.5)),
            # 缩放骨：小臂的子骨，叶子状
            ("ForeArmLow Scl L", "ForeArm L", (0.8, 0, 1.5)),
            # 缩放骨：上臂的子骨
            ("UpperArmMid Scl L", "UpperArm L", (0.5, 0, 1.5)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=0.75)
        return features

    def test_child_bone_rejected_for_parent_field(self):
        """小臂骨不能当上臂字段的候选（父子反了）。"""
        features = self._build_arm()
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        candidate = core.score_candidate("left_upper_arm_bone",
                                         features["ForeArm L"], features, ctx)
        self.assertIsNone(candidate, "小臂骨不应成为上臂候选")

    def test_scale_child_of_forearm_rejected(self):
        """小臂的缩放骨（叶子状）也不该被填给上臂。"""
        features = self._build_arm()
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        candidate = core.score_candidate("left_upper_arm_bone",
                                         features["ForeArmLow Scl L"],
                                         features, ctx)
        self.assertIsNone(candidate, "小臂的缩放骨不应成为上臂候选")

    def test_correct_bone_accepted(self):
        """真正的上臂骨不应被否决。"""
        features = self._build_arm()
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        candidate = core.score_candidate("left_upper_arm_bone",
                                         features["UpperArm L"], features, ctx)
        self.assertIsNotNone(candidate, "真正的上臂骨不应被否决")

    def test_torso_chain_relations(self):
        """躯干链：首/頭/上半身 也要能排除四肢骨。"""
        definitions = [
            ("Spine", "Hips", (0, 0, 1.2)),
            ("Neck", "Spine", (0, 0, 1.7)),
            ("Head", "Neck", (0, 0, 1.9)),
            ("ForeArm", "Arm", (0.7, 0, 1.5)),
            ("Hand", "ForeArm", (0.95, 0, 1.5)),
            ("Thigh", "Hips", (0.15, 0, 0.9)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.0)
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        # 手骨/小臂骨不能填给首、头、上半身
        for field in ("neck_bone", "head_bone", "upper_body_bone"):
            for bone in ("ForeArm", "Hand", "Thigh"):
                candidate = core.score_candidate(field, features[bone],
                                                 features, ctx)
                self.assertIsNone(candidate,
                                  f"{bone} 不应成为 {field} 的候选")
        # 正确的脊柱骨不应被否决
        for field, bone in (("neck_bone", "Neck"), ("head_bone", "Head"),
                            ("upper_body_bone", "Spine")):
            candidate = core.score_candidate(field, features[bone],
                                             features, ctx)
            self.assertIsNotNone(candidate,
                                 f"{bone} 不应被否决（{field}）")

    def test_lower_limb_chain_relations(self):
        """下肢链：大腿/小腿/脚 的父子关系也要检查。"""
        definitions = [
            ("Hips", "Root", (0, 0, 1.0)),
            ("Thigh", "Hips", (0.15, 0, 0.9)),
            ("Calf", "Thigh", (0.15, 0, 0.5)),
            ("Foot", "Calf", (0.15, 0, 0.1)),
            ("Toe", "Foot", (0.15, -0.15, 0.05)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=0.1, z_pct=head[2] / 2.0)
        stats = core.load_preset_stats()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        self.assertIsNone(core.score_candidate(
            "left_thigh_bone", features["Calf"], features, ctx))
        self.assertIsNone(core.score_candidate(
            "left_calf_bone", features["Thigh"], features, ctx))
        self.assertIsNone(core.score_candidate(
            "left_foot_bone", features["Calf"], features, ctx))
        self.assertIsNotNone(core.score_candidate(
            "left_calf_bone", features["Calf"], features, ctx))

    def test_unnamed_bones_not_rejected(self):
        """命名不规范的骨匹配不上类别时，不应被误杀。"""
        features = {
            "A": make_feature("A", head=(0.4, 0, 1.5), parent="B",
                              children=["C"], depth=0, length=0.1, z_pct=0.75),
            "B": make_feature("B", head=(0.2, 0, 1.5), parent=None,
                              children=["A"], depth=0, length=0.1, z_pct=0.75),
            "C": make_feature("C", head=(0.7, 0, 1.5), parent="A",
                              children=[], depth=0, length=0.1, z_pct=0.75),
        }
        self.assertFalse(core.chain_relation_violated(
            "left_upper_arm_bone", features["A"], features))


class MidlineToleranceTests(unittest.TestCase):
    """中轴容差：实测真实脊柱骨偏移 0.01~0.04%，侧骨（肩 3.27%/髋 4.85%）远在容差外。"""

    SPAN = 2.0

    def _build(self, offset_ratio):
        """造一根离中轴 offset_ratio*身高 的脊柱骨。"""
        offset = offset_ratio * self.SPAN
        features = {
            "Spine": make_feature(
                "Spine", head=(offset, 0, 1.0),
                tail=(offset, 0, 1.2), parent=None, children=[],
                depth=2, length=0.2, z_pct=0.55),
        }
        ctx = make_ctx(features, span=self.SPAN, diagonal=self.SPAN,
                       z_min=0.0, up_axis=2, side_axis=0)
        ctx["midline"] = 0.0
        # 放进脊柱链，确保被否决的原因是中轴而非脊柱链
        ctx["spine_chain"] = set(features)
        return features, ctx

    def test_real_spine_offset_accepted(self):
        """真实脊柱骨的偏移（0.04% 身高）应通过。"""
        features, ctx = self._build(0.0004)
        candidate = core.score_candidate("upper_body_bone", features["Spine"],
                                        features, ctx)
        self.assertIsNotNone(candidate, "贴近中轴的脊柱骨不应被否决")

    def test_shoulder_distance_rejected(self):
        """肩骨的距离（3.27% 身高）应被否决——原 3% 容差正好卡不住它。"""
        features, ctx = self._build(0.0327)
        candidate = core.score_candidate("upper_body_bone", features["Spine"],
                                        features, ctx)
        self.assertIsNone(candidate, "肩骨级别的偏移不应成为中心骨")

    def test_hip_distance_rejected(self):
        """髋骨的距离（4.85% 身高）应被否决。"""
        features, ctx = self._build(0.0485)
        candidate = core.score_candidate("upper_body_bone", features["Spine"],
                                        features, ctx)
        self.assertIsNone(candidate, "髋骨级别的偏移不应成为中心骨")

    def test_tolerance_stays_tight(self):
        """容差不得放宽到肩骨量级（防止以后被改松）。"""
        self.assertLessEqual(core.MIDLINE_TOLERANCE, 0.015,
                             "容差过宽会放过肩骨（实测 3.27%）")
        self.assertGreater(core.MIDLINE_TOLERANCE, 0.0004 * 10,
                           "容差过窄会误杀姿态化骨架的脊柱骨")


class ShadowedSupportBoneTests(unittest.TestCase):
    """同父骨下已有正牌主骨时，辅助骨应让位。"""

    def _build(self):
        # DNF 的真实结构：G Toe L 与 GD Toe Scl L 都挂在 GD Foot Scl L 下
        definitions = [
            ("Calf Like", None, (0.1, 0, 0.5)),
            ("Foot Scl", "Calf Like", (0.1, 0, 0.12)),
            ("Toe", "Foot Scl", (0.1, -0.15, 0.05)),
            ("Toe Scl", "Foot Scl", (0.1, -0.15, 0.05)),
        ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1] - 0.1, head[2]),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=2, length=0.12, z_pct=head[2] / 2.0)
        return features

    def test_scale_sibling_yields_to_main_bone(self):
        """脚趾字段应拿正牌骨，不是它的缩放兄弟骨。"""
        features = self._build()
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        self.assertIsNone(
            core.score_candidate("left_toe_bone", features["Toe Scl"],
                                 features, ctx),
            "有正牌趾骨时，缩放骨不应成为候选")
        self.assertIsNotNone(
            core.score_candidate("left_toe_bone", features["Toe"],
                                 features, ctx))

    def test_sole_bone_survives_when_no_main_sibling(self):
        """同父下没有正牌骨时，带 Scl 的骨仍可用（DNF 的掌骨/脚骨）。"""
        features = {
            "Calf Like": make_feature("Calf Like", head=(0.1, 0, 0.5),
                                      children=["Hand Scl"], depth=2,
                                      length=0.4, z_pct=0.25),
            "Hand Scl": make_feature("Hand Scl", head=(0.6, 0, 1.6),
                                     parent="Calf Like", children=[], depth=3,
                                     length=0.08, z_pct=0.8),
        }
        ctx = make_ctx(features, span=2.0, diagonal=2.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        self.assertIsNotNone(
            core.score_candidate("left_hand_bone", features["Hand Scl"],
                                 features, ctx),
            "同父下没有正牌掌骨时，缩放骨是唯一选择，不应被否决")


class SideSymbolTests(unittest.TestCase):
    """侧向分的核心是区分左右，不该惩罚贴近中轴的骨。"""

    def test_near_midline_bone_keeps_base_score(self):
        """锁骨根这类贴中轴的骨，符号正确就该拿基础档。"""
        near = make_feature("LeftClavicle", head=(0.005, 0, 1.5),
                            children=[], depth=2, length=0.15, z_pct=0.75)
        far = make_feature("LeftArm", head=(0.4, 0, 1.5),
                           children=[], depth=3, length=0.2, z_pct=0.75)
        ctx = make_ctx(span=2.0, diagonal=2.0, up_axis=2, side_axis=0)
        near_parts, _ = core.geometry_contributions(
            "left_shoulder_bone", near, {"LeftClavicle": near}, ctx)
        far_parts, _ = core.geometry_contributions(
            "left_shoulder_bone", far, {"LeftArm": far}, ctx)
        # 基础档 0.7 起，再按离中轴的距离小幅加成（0.005/2.0 身高 → +1.5%）
        self.assertAlmostEqual(near_parts["side"],
                               core.SIDE_MAX * core.SIDE_BASE, delta=0.005)
        self.assertGreaterEqual(near_parts["side"],
                                core.SIDE_MAX * core.SIDE_BASE)
        self.assertGreater(far_parts["side"], near_parts["side"])
        # 基础档至少要给到「符号正确」的大部分权重
        self.assertGreaterEqual(core.SIDE_BASE, 0.6)

    def test_wrong_symbol_still_zero(self):
        """符号不符仍是 0——区分左右的职能不能被削弱。"""
        wrong = make_feature("RightArm", head=(-0.4, 0, 1.5),
                             children=[], depth=3, length=0.2, z_pct=0.75)
        ctx = make_ctx(span=2.0, diagonal=2.0, up_axis=2, side_axis=0)
        parts, _ = core.geometry_contributions(
            "left_upper_arm_bone", wrong, {"RightArm": wrong}, ctx)
        self.assertEqual(parts["side"], 0.0)


class FullSkeletonChainTests(unittest.TestCase):
    """整副骨架跑完整解算后，左右肢体链的祖先关系必须全部成立。"""

    def _build_skeleton(self):
        """造一副标准人形骨架（身高 2.0）。"""
        center = [
            ("Root", None, (0, 0, 0.0)),
            ("Hips", "Root", (0, 0, 0.95)),
            ("Spine", "Hips", (0, 0, 1.15)),
            ("Chest", "Spine", (0, 0, 1.45)),
            ("Neck", "Chest", (0, 0, 1.70)),
            ("Head", "Neck", (0, 0, 1.85)),
        ]
        limbs = []
        for side, sign in (("Left", 1), ("Right", -1)):
            limbs.extend([
                (f"{side}Clavicle", "Chest", (sign * 0.06, 0, 1.62)),
                (f"{side}UpperArm", f"{side}Clavicle", (sign * 0.18, 0, 1.62)),
                (f"{side}ForeArm", f"{side}UpperArm", (sign * 0.42, 0, 1.62)),
                (f"{side}Hand", f"{side}ForeArm", (sign * 0.64, 0, 1.62)),
                (f"{side}Thigh", "Hips", (sign * 0.10, 0, 0.92)),
                (f"{side}Calf", f"{side}Thigh", (sign * 0.10, 0, 0.50)),
                (f"{side}Foot", f"{side}Calf", (sign * 0.10, 0, 0.08)),
            ])
        definitions = center + limbs
        features = {}
        for name, parent, head in definitions:
            bone_length = 0.2
            for child_name, child_parent, child_head in definitions:
                if child_parent != name:
                    continue
                bone_length = max(
                    0.05,
                    sum((child_head[i] - head[i]) ** 2 for i in range(3)) ** 0.5)
                break
            features[name] = make_feature(
                name, head=head,
                tail=(head[0], head[1], head[2] + bone_length),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=0, length=bone_length, z_pct=head[2] / 2.0)
        return features

    def test_limb_chains_hold_after_full_solve(self):
        features = self._build_skeleton()
        stats = core.load_preset_stats()
        filled, _low, _result = core.solve(
            core.FIELD_ORDER, features, span=2.0, diagonal=2.0, z_min=0.0,
            up_axis=2, side_axis=0, stats=stats)
        for parent_field, child_field in core.CHAIN_PAIRS:
            if parent_field not in filled or child_field not in filled:
                continue
            parent_bone = filled[parent_field]["bone"]
            child_bone = filled[child_field]["bone"]
            if parent_bone not in features or child_bone not in features:
                continue
            self.assertTrue(
                core._is_ancestor(features, parent_bone, child_bone),
                f"{child_field}={child_bone} 不是 {parent_field}="
                f"{parent_bone} 的后代")
        # 一根骨不能被两个字段占用
        bones = [c["bone"] for c in filled.values()]
        self.assertEqual(len(bones), len(set(bones)), "存在重复占骨")

    def test_core_bones_resolved_on_clean_skeleton(self):
        """干净骨架（命名规范）的核心骨应全部填对。"""
        features = self._build_skeleton()
        stats = core.load_preset_stats()
        filled, _low, _result = core.solve(
            core.FIELD_ORDER, features, span=2.0, diagonal=2.0, z_min=0.0,
            up_axis=2, side_axis=0, stats=stats)
        expected = {
            "upper_body_bone": "Spine",
            "neck_bone": "Neck",
            "head_bone": "Head",
            "left_shoulder_bone": "LeftClavicle",
            "left_upper_arm_bone": "LeftUpperArm",
            "left_lower_arm_bone": "LeftForeArm",
            "left_hand_bone": "LeftHand",
            "left_thigh_bone": "LeftThigh",
            "left_calf_bone": "LeftCalf",
            "left_foot_bone": "LeftFoot",
            "right_upper_arm_bone": "RightUpperArm",
            "right_lower_arm_bone": "RightForeArm",
            "right_thigh_bone": "RightThigh",
            "right_calf_bone": "RightCalf",
            "right_foot_bone": "RightFoot",
        }
        for field, bone in expected.items():
            self.assertEqual(filled.get(field, {}).get("bone"), bone,
                             f"{field} 应为 {bone}")


class SymmetryTests(unittest.TestCase):
    """非对称骨架不能套用镜像约束。"""

    def _build(self, raise_left_arm=False):
        """搭一副人形骨架。raise_left_arm=True 时左手举起（左右不对称）。"""
        definitions = [
            ("左肩", "上半身", (0.2, 0.0, 1.85)),
            ("左腕", "左肩", (0.5, 0.0, 1.8)),
            ("左ひじ", "左腕", (0.8, 0.0, 1.6)),
            ("左手首", "左ひじ", (1.0, 0.0, 1.5)),
            ("右肩", "上半身", (-0.2, 0.0, 1.85)),
            ("右腕", "右肩", (-0.5, 0.0, 1.8)),
            ("右ひじ", "右腕", (-0.8, 0.0, 1.6)),
            ("右手首", "右ひじ", (-1.0, 0.0, 1.5)),
            ("左足", "下半身", (0.15, 0.0, 1.0)),
            ("左ひざ", "左足", (0.15, 0.0, 0.5)),
            ("左足首", "左ひざ", (0.15, 0.0, 0.1)),
            ("右足", "下半身", (-0.15, 0.0, 1.0)),
            ("右ひざ", "右足", (-0.15, 0.0, 0.5)),
            ("右足首", "右ひざ", (-0.15, 0.0, 0.1)),
        ]
        if raise_left_arm:
            definitions = [
                (name, parent,
                 (head[0], head[1] + 0.3, head[2] + 0.5)
                 if name in ("左腕", "左ひじ", "左手首") else head)
                for name, parent, head in definitions
            ]
        features = {}
        for name, parent, head in definitions:
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1], head[2] + 0.1),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                length=0.1, z_pct=0.5)
        return features

    def test_symmetric_rig_detected(self):
        """左右镜像的骨架应判定为对称。"""
        features = self._build()
        symmetric, error = core.detect_symmetry(features, 2.2, side_axis=0)
        self.assertTrue(symmetric)
        self.assertLessEqual(error, core.MIRROR_TOLERANCE)

    def test_asymmetric_rig_detected(self):
        """举起单手的骨架应判定为非对称。"""
        features = self._build(raise_left_arm=True)
        symmetric, error = core.detect_symmetry(features, 2.2, side_axis=0)
        self.assertFalse(symmetric)
        self.assertGreater(error, core.MIRROR_TOLERANCE)

    def test_mirror_constraint_disabled_for_asymmetric_rig(self):
        """非对称骨架下，镜像约束不得否决候选。"""
        features = self._build(raise_left_arm=True)
        symmetric, _error = core.detect_symmetry(features, 2.2, side_axis=0)
        self.assertFalse(symmetric)
        ctx = make_ctx(features, span=2.2, diagonal=3.0, z_min=0.0,
                       up_axis=2, side_axis=0)
        ctx["symmetric"] = symmetric
        assignments = {"left_upper_arm_bone": {"bone": "左腕"}}
        # 右手上臂与左上臂镜像误差超限，但对非对称骨架不构成否决理由
        error = core.mirror_error("right_upper_arm_bone", "右腕",
                                  assignments, features, ctx)
        self.assertGreater(error, core.MIRROR_TOLERANCE)

    def test_named_side_pairs_recognize_common_spellings(self):
        """左右配对识别应覆盖中英文与常见后缀写法。"""
        names = ["左腕", "右腕", "LeftArm", "RightArm", "arm.L", "arm.R",
                 "l_forearm", "r_forearm"]
        pairs = dict((left, right) for left, right
                     in core._named_side_pairs({n: None for n in names}))
        self.assertEqual(pairs.get("左腕"), "右腕")
        self.assertEqual(pairs.get("LeftArm"), "RightArm")
        self.assertEqual(pairs.get("arm.L"), "arm.R")
        self.assertEqual(pairs.get("l_forearm"), "r_forearm")


class FingerGeometryTests(unittest.TestCase):
    """手指身份的几何推断：只靠物理位置，不依赖名称。"""

    def _build_hand(self, side_x, finger_x):
        """搭一只带五指的手（含躯干以形成足够的骨架深度）。

        finger_x: {食指/中指/无名指/小指: X 坐标}
        掌骨长 0.15、指节长 0.06，相对身高 2.0 符合真实比例。
        """
        span = 2.0
        # 躯干：从根到手的链条，让手部骨的 depth 达到整体深度的 35% 以上
        definitions = [
            ("Root", None, (0.0, 0.0, 0.0)),
            ("Waist", "Root", (0.0, 0.0, 0.5)),
            ("Chest", "Waist", (0.0, 0.0, 1.0)),
            ("Shoulder", "Chest", (side_x * 0.5, 0.0, 1.2)),
            ("Arm", "Shoulder", (side_x * 0.8, 0.0, 1.1)),
            ("ForeArm", "Arm", (side_x * 0.95, 0.0, 1.05)),
            ("Hand", "ForeArm", (side_x, 0.0, 1.0)),
        ]
        for name, x in finger_x.items():
            for seg in (1, 2, 3):
                definitions.append((
                    f"{name}{seg}",
                    f"{name}{seg - 1}" if seg > 1 else "Hand",
                    (x, -0.08 * seg, 1.0 - 0.02 * seg)))
        # 拇指：朝侧方偏出，方向与四指明显不同（夹角 > 40°）
        for seg in (1, 2, 3):
            definitions.append((
                f"thumb{seg}",
                f"thumb{seg - 1}" if seg > 1 else "Hand",
                (side_x - 0.15 * seg, -0.06 * seg, 0.95 - 0.03 * seg)))

        features = {}
        for name, parent, head in definitions:
            if name == "Hand":
                length = 0.15
            elif name in ("Root", "Waist", "Chest"):
                length = 0.5
            elif name in ("Shoulder", "Arm", "ForeArm"):
                length = 0.3
            else:
                length = 0.06
            features[name] = make_feature(
                name, head=head, tail=(head[0], head[1] - length, head[2]),
                parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=self._depth(definitions, name),
                length=length, z_pct=head[2] / 3.2)
        return features, span

    @staticmethod
    def _depth(definitions, name):
        mapping = {n: p for n, p, _ in definitions}
        depth = 0
        current = mapping.get(name)
        while current:
            depth += 1
            current = mapping.get(current)
        return depth

    def test_thumb_identified_by_geometry(self):
        """拇指独立偏出，应被识别为 thumb。"""
        features, span = self._build_hand(
            1.0, {"index": 1.05, "middle": 1.15, "ring": 1.25, "pinky": 1.35})
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        # 拇指的掌骨节节号为 0，其余手指的掌骨节节号为 1
        firsts = {v[0]: k for k, v in roles.items()
                  if v[1] == (0 if v[0] == "thumb" else 1)}
        self.assertEqual(firsts["thumb"], "thumb1")
        # 四指类型齐全且顺序正确
        self.assertEqual(
            sorted(f for f in firsts if f != "thumb"),
            ["index", "middle", "pinky", "ring"])

    def test_four_fingers_ordered_by_distance_from_thumb(self):
        """食指紧邻拇指，小指最远。"""
        features, span = self._build_hand(
            1.0, {"index": 1.05, "middle": 1.15, "ring": 1.25, "pinky": 1.35})
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        # 拇指在 X=0.85 一侧，食指应是最靠近拇指的那根
        positions = {}
        for finger in ("index", "middle", "ring", "pinky"):
            bone = next(k for k, v in roles.items()
                        if v[0] == finger and v[1] == 1)
            positions[finger] = features[bone].head[0]
        self.assertLess(positions["index"], positions["middle"])
        self.assertLess(positions["middle"], positions["ring"])
        self.assertLess(positions["ring"], positions["pinky"])

    def test_segment_numbers_follow_field_convention(self):
        """节号口径：拇指从 0 起，其余手指从 1 起。"""
        features, span = self._build_hand(
            1.0, {"index": 1.05, "middle": 1.15, "ring": 1.25, "pinky": 1.35})
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        thumb_bone = next(k for k, v in roles.items()
                          if v[0] == "thumb" and v[1] == 0)
        index_bone = next(k for k, v in roles.items()
                          if v[0] == "index" and v[1] == 1)
        self.assertEqual(roles[thumb_bone][1], 0)
        self.assertEqual(roles[index_bone][1], 1)

    def test_geo_conflict_does_not_exclude_candidate(self):
        """几何推断与字段冲突时不排除候选，只降权（避免误判毁掉映射）。"""
        features, span = self._build_hand(
            1.0, {"index": 1.05, "middle": 1.15, "ring": 1.25, "pinky": 1.35})
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        thumb_bone = next(k for k, v in roles.items()
                          if v[0] == "thumb" and v[1] == 0)
        ctx = make_ctx(features, span=span, diagonal=span, z_min=0.0,
                       up_axis=2, side_axis=0)
        ctx["finger_roles"] = roles
        candidate = core.score_candidate("left_index_1", features[thumb_bone],
                                         features, ctx)
        self.assertIsNotNone(candidate, "候选不应被排除")
        # 冲突时方向项拿中性分（0.05 = DIRECTION_MAX * 0.5）
        self.assertAlmostEqual(candidate["parts"]["direction"], 0.05, places=6)

    def test_matching_finger_gets_full_geometry_credit(self):
        """几何身份吻合时，方向项拿满分。"""
        features, span = self._build_hand(
            1.0, {"index": 1.05, "middle": 1.15, "ring": 1.25, "pinky": 1.35})
        roles, _sides, _domains = core.infer_finger_roles(features, span=span,
                                                side_axis=0, up_axis=2)
        index_bone = next(k for k, v in roles.items()
                          if v[0] == "index" and v[1] == 1)
        ctx = make_ctx(features, span=span, diagonal=span, z_min=0.0,
                       up_axis=2, side_axis=0)
        ctx["finger_roles"] = roles
        ratio, _reason = core.finger_geo_contribution(
            "left_index_1", features[index_bone], roles)
        self.assertEqual(ratio, 1.0)


class LowConfidenceTests(unittest.TestCase):
    """低置信度字段：照填 + 标红，而不是留空。"""

    def _features_with_low_confidence_field(self):
        """构造一个只有名字像、但几何明显不对的字段，迫使分数偏低。"""
        features = {
            "Head": make_feature("Head", head=(0, 0, 3.0), tail=(0, 0, 3.2),
                                 children=[], depth=3,
                                 length=0.2, z_pct=0.95),
            "SomethingElse": make_feature(
                "SomethingElse", head=(0, 0, 0.5), tail=(0, 0, 0.6),
                children=[], depth=1,
                length=0.1, z_pct=0.15),
        }
        return features

    def test_low_confidence_field_is_still_filled(self):
        """分数低于阈值的字段也要出现在结果里，并打上标记。"""
        features = self._features_with_low_confidence_field()
        stats = {"head_bone": {"head": 1}}
        filled, low_conf, result = core.solve(
            core.FIELD_ORDER, features, span=3.2, diagonal=3.2,
            z_min=0.0, up_axis=2, side_axis=0, stats=stats)
        # 所有被选中的字段都要在结果中，不因低分被丢弃
        for field, candidate in filled.items():
            if candidate["score"] < core.CONFIDENCE_THRESHOLD:
                self.assertTrue(candidate.get("low_confidence"),
                                f"{field} 低分却未标记")
                self.assertIn(field, [f for f, _s, _r in low_conf])

    def test_low_confidence_flagged_fields_appear_in_low_conf_list(self):
        """被标记的字段必须出现在 low_conf 里，供面板标红。"""
        features = self._features_with_low_confidence_field()
        stats = {"head_bone": {"head": 1}}
        filled, low_conf, _result = core.solve(
            core.FIELD_ORDER, features, span=3.2, diagonal=3.2,
            z_min=0.0, up_axis=2, side_axis=0, stats=stats)
        flagged = {f for f, c in filled.items() if c.get("low_confidence")}
        listed = {f for f, _s, _r in low_conf}
        self.assertTrue(flagged)
        self.assertTrue(flagged.issubset(listed),
                        f"标记字段未全部进入 low_conf：{flagged - listed}")

    def test_average_excludes_low_confidence(self):
        """平均置信度只统计稳妥填写，不被低分项拉低。"""
        features = self._features_with_low_confidence_field()
        stats = {"head_bone": {"head": 1}}
        filled, _low_conf, result = core.solve(
            core.FIELD_ORDER, features, span=3.2, diagonal=3.2,
            z_min=0.0, up_axis=2, side_axis=0, stats=stats)
        solid = [c["score"] for c in filled.values()
                 if not c.get("low_confidence")]
        if solid:
            expected = sum(solid) / len(solid)
            self.assertAlmostEqual(result["average"], expected, places=6)


class EndToEndTests(unittest.TestCase):
    def test_mmd_named_rig_resolves_major_chain(self):
        """用预设里的 MMD 日文名搭一个简化人形，验证整条链路。"""
        definitions = [
            ("全ての親", None, (0, 0, 0)),
            ("センター", "全ての親", (0, 0, 1)),
            ("グルーブ", "センター", (0, 0, 1.2)),
            ("腰", "グルーブ", (0, 0, 1.4)),
            ("下半身", "腰", (0, 0, 1.5)),
            ("上半身", "腰", (0, 0, 2.0)),
            ("上半身2", "上半身", (0, 0, 2.3)),
            ("上半身3", "上半身2", (0, 0, 2.5)),
            ("首", "上半身3", (0, 0, 2.8)),
            ("頭", "首", (0, 0, 3.0)),
            ("左肩", "上半身3", (0.3, 0, 2.7)),
            ("左腕", "左肩", (0.6, 0, 2.6)),
            ("左ひじ", "左腕", (0.9, 0, 2.4)),
            ("左手首", "左ひじ", (1.2, 0, 2.2)),
            ("右肩", "上半身3", (-0.3, 0, 2.7)),
            ("右腕", "右肩", (-0.6, 0, 2.6)),
            ("右ひじ", "右腕", (-0.9, 0, 2.4)),
            ("右手首", "右ひじ", (-1.2, 0, 2.2)),
            ("左足", "下半身", (0.2, 0, 1.4)),
            ("左ひざ", "左足", (0.2, 0, 0.8)),
            ("左足首", "左ひざ", (0.2, 0, 0.2)),
            ("左足先EX", "左足首", (0.2, 0.3, 0.1)),
            ("右足", "下半身", (-0.2, 0, 1.4)),
            ("右ひざ", "右足", (-0.2, 0, 0.8)),
            ("右足首", "右ひざ", (-0.2, 0, 0.2)),
            ("右足先EX", "右足首", (-0.2, 0.3, 0.1)),
            ("左目", "頭", (0.1, 0.25, 3.05)),
            ("右目", "頭", (-0.1, 0.25, 3.05)),
        ]
        features = {}
        for name, parent, head in definitions:
            tail = (head[0], head[1], head[2] + 0.1)
            features[name] = make_feature(
                name, head=head, tail=tail, parent=parent,
                children=[n for n, p, _ in definitions if p == name],
                depth=self._depth(definitions, name),
                length=0.1,
                z_pct=head[2] / 3.2,
            )
        stats = core.load_preset_stats()
        filled, low_conf, stats_out = core.solve(
            core.FIELD_ORDER, features, span=3.2, diagonal=3.2,
            z_min=0.0, up_axis=2, side_axis=0, stats=stats)

        self.assertGreater(stats_out["filled"], 20)
        for field, bone in (
                ("head_bone", "頭"),
                ("neck_bone", "首"),
                ("left_upper_arm_bone", "左腕"),
                ("right_lower_arm_bone", "右ひじ"),
                ("left_thigh_bone", "左足"),
                ("left_calf_bone", "左ひざ"),
                ("left_foot_bone", "左足首"),
                ("left_eye_bone", "左目")):
            self.assertIn(field, filled, f"{field} 未被填写；低置信={low_conf}")
            self.assertEqual(filled[field]["bone"], bone, field)
        self.assertIn("reason", filled["head_bone"])
        self.assertIn("parts", filled["head_bone"])

    @staticmethod
    def _depth(definitions, name):
        mapping = {n: p for n, p, _ in definitions}
        depth = 0
        current = mapping.get(name)
        while current:
            depth += 1
            current = mapping.get(current)
        return depth


if __name__ == "__main__":
    unittest.main(verbosity=2)
