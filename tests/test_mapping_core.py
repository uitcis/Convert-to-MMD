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
        self.assertEqual(core.name_contribution("head_bone", "Bip Head Top", stats)[0], 0.25)
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
