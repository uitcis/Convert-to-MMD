"""自动骨骼映射操作符：把求解结果写回现有预设字段。"""

import datetime
import os
import tempfile

import bpy

from .. import bone_utils
from ..tools.auto_bone_mapping import (
    FIELD_ORDER, field_label, invalidate_preset_cache, solve_mapping,
)


def _report_path():
    """依据报告固定的临时文件路径（每次运行覆盖）。"""
    return os.path.join(tempfile.gettempdir(), "convert_to_mmd_mapping_report.txt")


def _build_report(filled, low_conf, stats, armature_name):
    """生成可读的映射依据文本报告。"""
    lines = [
        "Convert to MMD - 自动骨骼映射依据",
        f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"骨架对象：{armature_name}",
        f"骨骼数量：{stats.get('bone_count', 0)} 根",
        f"填写结果：{stats.get('filled', 0)}/{len(FIELD_ORDER)} 字段，"
        f"平均置信度 {stats.get('average', 0.0):.2f}",
        f"搜索节点：{stats.get('search_nodes', 0)}",
        "",
        "=" * 64,
        "已填写字段（按置信度降序）",
        "=" * 64,
    ]
    for field, candidate in sorted(filled.items(),
                                   key=lambda kv: kv[1]["score"], reverse=True):
        parts = candidate.get("parts", {})
        geometry = sum(parts.get(key, 0.0)
                       for key in ("side", "height", "direction"))
        derived = "（拓扑推导）" if candidate.get("derived") else ""
        guess = "（置信度不足，建议核对）" if candidate.get("low_confidence") else ""
        lines.append(
            f"{field_label(field)}  {candidate['bone']}  "
            f"{candidate['score']:.2f}{derived}{guess}"
        )
        lines.append(
            f"    名称 {parts.get('name', 0.0):.2f}  "
            f"拓扑 {parts.get('topology', 0.0):.2f}  "
            f"几何 {geometry:.2f}  "
            f"权重 {parts.get('weight', 0.0):.2f}"
        )
        if candidate.get("reason"):
            lines.append(f"    依据：{candidate['reason']}")

    lines += [
        "",
        "=" * 64,
        f"需人工核对（{len(low_conf)} 项）",
        "=" * 64,
    ]
    if low_conf:
        for field, score, reason in low_conf:
            lines.append(f"{field_label(field)}  置信度 {score:.2f}（{reason}）")
    else:
        lines.append("无")

    lines += [
        "",
        "说明：名称为原始贡献分（合计 1.20），置信度为归一到 0~1 后的值。",
        "      低于 0.55 的字段仍会填入，但在面板标红提示，需人工核对。",
    ]
    return "\n".join(lines)


class OBJECT_OT_auto_detect_bone_mapping(bpy.types.Operator):
    """自动识别骨骼映射"""
    bl_idname = "object.auto_detect_bone_mapping"
    bl_label = "自动识别骨骼映射"
    bl_description = (
        "根据名称、拓扑、几何、权重四类证据打分并做全局约束求解，"
        "把结果写入下方预设字段；置信度不足的字段照常填入但在面板高亮警告"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armature = bone_utils.resolve_armature(context)
        if not armature:
            self.report({'ERROR'}, "未选择骨架对象")
            return {'CANCELLED'}

        scene = context.scene

        # 先清空所有字段，避免上一次的旧结果混入
        for field in FIELD_ORDER:
            if hasattr(scene, field):
                setattr(scene, field, "")

        # 预设可能在上次运行后被导入/修改，名称库必须重建
        invalidate_preset_cache()

        try:
            filled, low_conf, stats = solve_mapping(armature)
        except Exception as exc:  # 数据异常时给出可见反馈，而不是静默失败
            print(f"[Convert-to-MMD] 自动骨骼映射失败: {exc}")
            self.report({'ERROR'}, f"自动骨骼映射失败: {exc}")
            return {'CANCELLED'}

        if not stats:
            self.report({'ERROR'}, "骨架中没有可用于识别的骨骼")
            return {'CANCELLED'}

        for field, candidate in filled.items():
            setattr(scene, field, candidate["bone"])

        summary = (
            f"已填写 {stats['filled']}/{len(FIELD_ORDER)} 字段，"
            f"平均置信度 {stats['average']:.2f}，可识别骨骼 {stats['bone_count']} 根"
        )
        if stats["low_conf"]:
            summary += f"，{stats['low_conf']} 个字段置信度不足（已标红）"

        # 控制台只留一行摘要：逐字段的分数、依据、拓扑推导说明都在
        # 「查看依据」报告里，点按钮才看，避免每次刷屏六十几行。
        print(f"[Convert-to-MMD] 自动骨骼映射：{summary}。"
              f"逐字段依据点「查看依据」")

        low_conf_lines = [f"{field_label(field)} {score:.2f}（{reason}）"
                          for field, score, reason in low_conf]
        scene.auto_map_summary = summary
        scene.auto_map_low_confidence = "\n".join(low_conf_lines)
        scene.auto_map_low_conf_fields = ",".join(
            field for field, _score, _reason in low_conf)

        # 写临时报告，路径保存到场景属性
        path = _report_path()
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(_build_report(filled, low_conf, stats, armature.name))
            scene.auto_map_report_path = path
        except OSError as exc:
            print(f"[Convert-to-MMD] 写入映射依据报告失败: {exc}")

        self.report({'INFO'}, summary)
        return {'FINISHED'}


class OBJECT_OT_view_auto_mapping_report(bpy.types.Operator):
    """打开自动骨骼映射依据报告"""
    bl_idname = "object.view_auto_mapping_report"
    bl_label = "查看映射依据"
    bl_description = "用系统默认文本编辑器打开最近一次的映射依据报告"
    bl_options = {'REGISTER'}

    def execute(self, context):
        path = getattr(context.scene, "auto_map_report_path", "")
        if not path or not os.path.isfile(path):
            self.report({'WARNING'}, "尚无映射依据，请先点击「自动识别骨骼映射」")
            return {'CANCELLED'}
        try:
            os.startfile(path)  # Windows 系统默认程序
        except AttributeError:  # 非 Windows 平台
            import subprocess
            try:
                subprocess.Popen(["xdg-open", path])
            except OSError as exc:
                self.report({'ERROR'}, f"无法打开报告: {exc}")
                return {'CANCELLED'}
        except OSError as exc:
            self.report({'ERROR'}, f"无法打开报告: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}
