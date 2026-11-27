"""自动骨骼映射操作符：把求解结果写回现有预设字段。"""

import bpy

from .. import bone_utils
from ..tools.auto_bone_mapping import FIELD_ORDER, solve_mapping


class OBJECT_OT_auto_detect_bone_mapping(bpy.types.Operator):
    """自动识别骨骼映射"""
    bl_idname = "object.auto_detect_bone_mapping"
    bl_label = "自动识别骨骼映射"
    bl_description = (
        "根据名称、拓扑、几何、权重四类证据打分并做全局约束求解，"
        "把结果写入下方预设字段；置信度不足的字段保持为空并在面板高亮"
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

        # 逐项置信度输出到控制台，便于核对算法效果
        print("[Convert-to-MMD] 自动骨骼映射结果：")
        for field in FIELD_ORDER:
            if field in filled:
                print(f"  {field}: {filled[field]['bone']} "
                      f"({filled[field]['score']:.2f})")
        if low_conf:
            print("  以下字段置信度不足，已留空：")
            for field, score, reason in low_conf:
                print(f"  {field}: 最佳候选 {score:.2f}（{reason}）")

        summary = (
            f"已填写 {stats['filled']}/{len(FIELD_ORDER)} 字段，"
            f"平均置信度 {stats['average']:.2f}，可识别骨骼 {stats['bone_count']} 根"
        )
        if stats["low_conf"]:
            summary += f"，{stats['low_conf']} 个字段留空"

        low_conf_lines = [f"{field} {score:.2f}（{reason}）"
                          for field, score, reason in low_conf]
        scene.auto_map_summary = summary
        scene.auto_map_low_confidence = "\n".join(low_conf_lines)
        scene.auto_map_low_conf_fields = ",".join(
            field for field, _score, _reason in low_conf)

        self.report({'INFO'}, summary)
        return {'FINISHED'}
