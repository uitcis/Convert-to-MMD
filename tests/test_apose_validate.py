"""A-Pose 输入校验与提示文案的单测（不依赖 Blender）。

运行：python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# 直接按文件名导入：tools/__init__.py 会连带导入依赖 bpy 的模块，
# 纯 Python 环境（无 bpy）下不能走 `from tools import ...`。
import apose_validate as av  # noqa: E402


EXISTING = {"UB", "Neck", "LU", "LL", "RU", "RL"}


def settings(**kwargs):
    """按字段名出配置；未给出的字段为空。"""
    base = {field: "" for field, *_ in av.APOSE_FIELDS}
    base.update(kwargs)
    return base


def collect(conf, existing=EXISTING):
    return av.collect_issues(conf.get, existing)


class CollectIssuesTests(unittest.TestCase):

    def test_all_empty_reports_six_items(self):
        issues = collect(settings())
        self.assertEqual(len(issues), 6)
        self.assertTrue(all(i["kind"] == av.KIND_EMPTY for i in issues))

    def test_complete_config_has_no_issue(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone="RL"))
        self.assertEqual(issues, [])

    def test_only_one_side_reports_the_other_side(self):
        """左臂完整、右臂全空：只应报右侧两项，不能连左侧一起报。"""
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="", right_lower_arm_bone=""))
        fields = {i["field"] for i in issues}
        self.assertEqual(fields, {"right_upper_arm_bone",
                                  "right_lower_arm_bone"})

    def test_upper_arms_only_reports_both_lower_arms(self):
        """左右上臂都有、小臂全空：必须点出两个小臂，而不是笼统说「骨骼缺失」。"""
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", right_upper_arm_bone="RU"))
        fields = {i["field"] for i in issues}
        self.assertEqual(fields, {"left_lower_arm_bone",
                                  "right_lower_arm_bone"})
        self.assertTrue(all(i["kind"] == av.KIND_EMPTY for i in issues))

    def test_nonexistent_bone_keeps_name_and_kind(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="NoSuchBone", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone="RL"))
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["field"], "left_upper_arm_bone")
        self.assertEqual(issue["kind"], av.KIND_MISSING)
        self.assertEqual(issue["value"], "NoSuchBone")

    def test_duplicate_bones_flagged(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="LU", right_lower_arm_bone="RL"))
        kinds = [i["kind"] for i in issues]
        self.assertIn(av.KIND_DUPLICATE, kinds)

    def test_blank_and_whitespace_treated_as_empty(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="   ",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone="RL"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["field"], "neck_bone")
        self.assertEqual(issues[0]["kind"], av.KIND_EMPTY)


class MessageTests(unittest.TestCase):

    def test_message_names_side_part_and_state(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", right_upper_arm_bone="RU"))
        message = av.build_message(issues)
        self.assertIn("左侧小臂", message)
        self.assertIn("右侧小臂", message)
        self.assertIn("左ひじ", message)
        self.assertIn("右ひじ", message)
        self.assertIn("未设置", message)

    def test_message_includes_requirement(self):
        message = av.build_message(collect(settings()))
        self.assertIn(av.REQUIREMENT_TEXT, message)
        for word in ("上半身", "首", "左腕", "右腕", "左ひじ", "右ひじ"):
            self.assertIn(word, message)

    def test_message_does_not_leak_internal_field_names(self):
        """提示里不能出现 left_lower_arm 这类内部字段名。"""
        issues = collect(settings())
        message = av.build_message(issues)
        for field, *_ in av.APOSE_FIELDS:
            self.assertNotIn(field, message,
                             f"提示泄漏了内部字段名 {field}")

    def test_missing_bone_message_shows_actual_name(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="NoSuchBone", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone="RL"))
        message = av.build_message(issues)
        self.assertIn("NoSuchBone", message)
        self.assertIn("左腕", message)
        self.assertIn("不存在", message)

    def test_single_issue_message_reads_naturally(self):
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="Neck",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone=""))
        message = av.build_message(issues)
        self.assertTrue(message.startswith("无法执行 A-Pose："))
        self.assertNotIn("1 项", message)

    def test_detail_lines_list_each_issue_with_role(self):
        issues = collect(settings())
        lines = av.build_detail_lines(issues)
        self.assertTrue(lines[0].startswith("[A-Pose]"))
        self.assertEqual(len(lines), 1 + len(issues) + 1)
        self.assertIn("确定身体左右轴", "\n".join(lines))

    def test_center_fields_do_not_repeat_side_and_part(self):
        """躯干类字段的侧别与部位同名，提示里不能出现「躯干躯干」。"""
        issues = collect(settings(
            upper_body_bone="UB", neck_bone="",
            left_upper_arm_bone="LU", left_lower_arm_bone="LL",
            right_upper_arm_bone="RU", right_lower_arm_bone="RL"))
        message = av.build_message(issues)
        self.assertNotIn("躯干躯干", message)
        self.assertIn("首（躯干，未设置）", message)

    def test_no_issues_gives_empty_message(self):
        self.assertEqual(av.build_message([]), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
