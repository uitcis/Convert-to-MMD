# 更新日志 (CHANGELOG)

本文件由 Gitee Release 流水线 `.workflow/发行.yml` 读取，作为每次 Tag 发版的发布说明。
发版约定：每次发版只保留当前版本的内容，不保留历史版本条目。

## [1.6] - 2026-11-27

### A-Pose 转换改为烘顶点方案

- 移除「复制 Armature 修改器 → modifier_apply → 删除重建全部形态键」流程，改为读取 depsgraph 的 evaluated mesh 顶点直接写回 Basis / mesh.vertices；修改器栈与形态键全程保留
- 烘顶点前形态键 value 临时归零（Basis 除外）、非 Armature 修改器临时关闭并重新获取 depsgraph，避免表情与细分/镜像效果混入基础网格；写回后自动恢复
- `armature_apply()` 将摆好的 A-Pose 固化为新的静置姿态，网格与骨骼姿态一致，视觉零跳变（实测最大差 0.000000）
- 形态键 delta 无需跟随骨骼旋转：它是相对 Basis 的独立层，Blender 先算形态键再做蒙皮

### 跨版本兼容性修复

- 修复 Blender 4.5 下 A-Pose 报错：`PoseBone.select` 仅 5.x 存在（4.5 为 `Bone.select`），清除手臂姿态改为直接重置 `matrix_basis`
- 修复 `bone_utils._restore_shape_keys()` 重建 Basis 后未恢复 `value`，导致 4.5 下 Basis value 从 1 变 0；此修复对所有调用 `apply_armature_transforms` 的操作生效

### 验证

- 新增 `tools/apose_operator_verify.py`（真实工程端到端）与 `tools/apose_operator_smoke.py`（最小场景跨版本）
- 最小场景 Blender 4.0 / 4.2 / 4.5 / 5.0 / 5.2 全部 6/6 通过
- 真实工程 TESTMIKU1（日文骨架）4.5 / 5.0 / 5.2 与 TESTMIKU（英文骨架）5.2 全部 7/7 通过

<!-- V1.6 release trigger -->
