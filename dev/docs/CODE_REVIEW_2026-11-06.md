# Convert to MMD 代码审查报告

- 审查对象：`c:\Users\UITCIS\OneDrive\Code\addons\Convert-to-MMD`（Blender 插件，`bl_info` 版本 (2,6)，CHANGELOG 最新 1.1.0）
- 审查时间：2026-11-06
- 审查方式：通读全部 Python 模块（根目录 6 个 + `operators/` 13 个 + `tools/` 12 个），并结合 README/CHANGELOG 理解设计意图；`python -m compileall` 通过，**未在 Blender 内实际运行**，涉及运行期行为的结论已标注依据，无法静态确认的放入「不确定项」。
- 说明：本报告只做审查，不改代码。`.workbuddy/memory/2026-08-27_code_review.md` 中的旧问题（预设枚举定时器、备份清理、Blender 4.0 兼容、异常处理）已确认大部分已修复，本报告不重复。

---

## 一、先弄清转换流程（这决定了问题优先级）

插件本质上是「一个有顺序的向导」，数据流是 **Scene 上的字符串属性（骨骼名）→ 按 `mmd_bone_map` 批量改名 → 按 MMD 规范补建缺失骨骼 → 加 IK/骨骼集合 → mmd_tools 转模型 → 追加次标准骨骼与物理**。

主流程（对应 README）：

1. **A-Pose 转换**（`operators/pose_operator.py`）：在姿态模式旋转肩/腕，复制一份 Armature 修改器烘焙到网格，再 `pose.armature_apply()` 把 A-Pose 写入 rest。
2. **归正骨骼位置**（`operators/correct_bones_operator.py`）：备份骨架 → 把 3D 游标移到上半身正下方地面 → `origin_set` → `obj.location=0` → 清 pose 与动画。
3. **1. 重命名**（`operators/rename_bones_operator.py`）：备份 → [`check_and_scale_skeleton`](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/bone_utils.py#L108-L148) 检测高度/缩放 → 编辑模式批量改名 → 自动识别上半身链 → 按规则设 roll。
4. **2. 补全缺失骨骼**（`operators/complete_bones_operator.py`）：补 `全ての親/腰/上半身/首/頭/肩/腕/手指/足先EX/足首D` 等，设置父子与 roll。
5. **3. IK + 4. 骨骼集合**（`operators/ik_operator.py`、`operators/collection_operator.py`）：给膝/踝加 IK 与限制，按 [bone_map_and_group.py](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/bone_map_and_group.py) 建骨骼集合。
6. **5. mmd_tools 转换**（`operators/preset_operator.py#L508`）。
7. **次标准骨骼与物理**：合并骨骼、捩骨、足 D 骨、肩 P/C、胸部物理、简易身体刚体（`operators/*_operator.py`、`tools/*.py`）。

关键依赖：第 3 步之后的几乎所有代码都直接用日文骨名做 `edit_bones[...]` 索引；第 7 步大量依赖 mmd_tools 的 `FnModel/FnRigidBody`，并且都假设「网格是骨架对象的直接子级」。这些假设是下面问题的根源。

---

## 二、问题总览

| 编号 | 位置 | 问题 | 级别 | 成本 |
|---|---|---|---|---|
| A1 | `ui_panel.py:20-38` vs 全部算子 | 面板能显示网格的骨架，但算子只认 `context.active_object`，选中网格时整条流程按钮全部报错 | 必须修 | 1 小时 |
| A2 | `complete_bones_operator.py:152,171` | `edit_bones["左手首"] if ... else` 的兜底分支永远不会生效，缺手骨时直接 KeyError | 必须修 | 20 分钟 |
| A3 | `rename_bones_operator.py:93` | 改名后第二次 `auto_detect_upper_body_chain` 在编辑模式读 `data.bones`（旧快照），属性刷新实际失效 | 必须修 | 10 分钟 |
| A4 | `bone_utils.py:122-148` | `scaled` 永远是 `False`，缩放后不给任何提示 | 必须修 | 2 分钟 |
| A5 | `tools/body_rigid_builder.py:179-187` | 圆拟合最小二乘公式错误，`n>3` 时矩阵必奇异，永远退回质心，拟合功能实际失效 | 必须修 | 15 分钟 |
| A6 | `tools/chest_physics_builder.py:364-386` | 弹簧关节名用了刚体名（`sd["joint"]` 未使用），与刚体对象重名；重跑时判重条件写错，关节会重复堆积 | 必须修 | 20 分钟 |
| A7 | `preset_operator.py:42-73` vs `properties.py:11-22` | 胸部左右骨骼声明为「对称属性」，但左右映射表里没有胸，自动填对侧静默失效 | 必须修 | 5 分钟 |
| A8 | `tools/export_bones_info_operator.py:90-117` | `is_weight_bone` 在 Armature 对象上查顶点组，恒为 `False`，导出信息失真 | 必须修 | 30 分钟 |
| A9 | `pose_operator.py`、`rename/complete/ik/correct` | 破坏性算子未声明 `{'UNDO'}`；A-Pose 还会临时删/建形态键，失败时不可恢复 | 建议修 | 5 分钟 + 备份 1 小时 |
| B1 | `body_rigid_builder.py:46`、`chest_physics_builder.py`、`add_twist_bone_operator.py:246` | 只用 `obj.parent == armature` 找网格，漏掉「仅用修改器绑定」的常见情况，物理/权重静默跳过 | 建议修 | 30 分钟 |
| B2 | `add_leg_d_bones_operator.py:16-35,198-201` | 未校验 `右足/右ひざ/足先EX` 等就索引，缺骨直接 traceback；且总是把模式切回 OBJECT | 建议修 | 20 分钟 |
| B3 | `chest_physics_builder.py:134`、`body_rigid_builder.py:265` | 物理算子里静默调用「5. mmd_tools 转换」，重复点击可能重复转换/覆盖 | 建议修（不确定是否需要） | 30 分钟 |
| B4 | `correct_bones_operator.py:28-55,63-71` | 备份在参数校验前创建（失败留垃圾），3D 游标和原选择不恢复 | 建议修 | 10 分钟 |
| B5 | `preset_operator.py:75-106`、`properties.py:57-103` | 清空骨骼字段不会清空自动填充的第二/三节；非 ARMATURE 活动对象时自动填充也静默不生效 | 建议修 | 30 分钟 |
| B6 | `load_preset_operator.py`、`preset_operator.py` 导入/导出 | JSON 未校验结构，坏文件只打控制台；文件读写未显式 UTF-8 | 建议修 | 15 分钟 |
| B7 | `bone_utils.py:108-138` | 只在高度 >10 时缩放，且按 10 倍取整；正常高度但对象 scale≠1 时不会应用缩放 | 建议修（需实测） | 20 分钟 |
| B8 | `collection_operator.py:74-78` | 「创建骨骼集合」会先删除骨架上的**所有**已有集合；三个次标准骨骼算子还会隐式调用它 | 建议修 | 20 分钟 |
| C1 | `body_rigid_builder.py:52-74,285` | 对每根变形骨扫描所有网格的所有顶点/组：O(骨×顶点×组)，大模型明显卡顿 | 优化 | 1-2 小时 |
| C2 | `merge_bones_operator.py:51-55,79-84` | 每顶点单独 `vg.add`，且每根骨都重新遍历全场景对象/修改器 | 优化 | 30 分钟 |
| C3 | `physics_utils.py:90-135`、`body_rigid_builder.py:239` | 每根骨都做 `gc.collect()` + 系统内存检查；系统内存 >80% 直接中止，副作用过大 | 优化 | 15 分钟 |
| D1 | `bone_map_and_group.py` / `preset_operator.py` / `complete` / `ik` | 骨骼名与左右关系分散在多处硬编码，已经出现漏配（A7） | 可维护性 | 半天 |
| D2 | `add_twist` / `add_leg_d` / `add_shoulder_p` | 「dummy+shadow+COPY_TRANSFORMS + 骨骼集合」三套几乎相同代码 | 可维护性 | 2-3 小时 |
| D3 | 多处 | 死代码与调试打印：`_current_updating_prop`、`check_bone_position_direction`（且左右符号与另一函数相反）、`is_temp_mesh`、`DEBUG print` | 可维护性 | 30 分钟 |
| D4 | `__init__.py:4`、`README.md:133`、`CHANGELOG.md` | 版本号 2.6 / 1.1.0 不一致；README 写 Blender 3.0+，实际 `bl_info` 要求 4.0 | 可维护性 | 5 分钟 |

---

## 三、正确性与潜在 Bug（必须修）

### A1. 面板按网格找骨架，但所有算子只认活动对象：选中网格时整条流程不可用

**位置**：[ui_panel.py:20-44](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/ui_panel.py#L20-L44)；受影响算子包括 `rename_bones_operator.py:15`、`complete_bones_operator.py:46`、`ik_operator.py:73`、`correct_bones_operator.py:10`、`merge_bones_operator.py:92`、`add_leg_d_bones_operator.py:17`、`chest_physics_builder.py:129`、`body_rigid_builder.py:256`、`clear_unweighted_bones_operator.py`、`export_bones_info_operator.py` 等。

**问题**：面板在活动对象是网格时会沿 `ARMATURE` 修改器找到骨架，并把它赋给 **局部变量** `obj` 用于绘制，所以 UI 看起来一切正常、骨骼选择器也能列出骨骼。但点击任何按钮后，Blender 传给算子的 `context.active_object` 仍然是那个网格，算子第一行 `if obj.type != 'ARMATURE'` 直接 `CANCELLED`。结果是「UI 有反应、操作没反应」。仓库里只有 [`adjust_bone_rolls_operator.py`](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/adjust_bone_rolls_operator.py#L18-L48) 的 `_resolve_armature` 做了同样的事情，说明这是已知问题但没有统一。

**依据**：面板绘图是纯读取，不会改变 `context.active_object`；后面的 `bpy.ops` 调用都以活动对象为准。

**建议**：新增 `bone_utils.resolve_armature(context)`（活动对象是骨架直接返回；是网格则沿 `ARMATURE` 修改器找；找不到返回 `None`），把所有算子的入口改为调用它；面板继续复用同一函数。这样也顺带修复了 `prop_search` 设置字段后 update 回调不生效的问题（见 B5）。

**成本**：约 1 小时（约 15 个算子统一替换，逻辑很小）。

**必须修**：这是最常见的用户状态（骨架+网格同时存在，最后操作往往停在网格），会让人误以为插件坏了。

---

### A2. `complete_bones_operator` 的「可选手骨」兜底分支永远不会执行

**位置**：[complete_bones_operator.py:150-174](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/complete_bones_operator.py#L150-L174)

```python
"tail": edit_bones["左手首"].head if edit_bones["左手首"] else edit_bones["左ひじ"].tail,
```

**问题**：条件表达式先求值 `edit_bones["左手首"]`，缺骨时这一步就抛 `KeyError`，`else` 分支永远到不了。注释写的是「不存在就用肘尾」，实际行为是整条补全失败（异常被外层 `except` 捕获后只报一句「骨骼属性构建失败」）。右手同样。另外 `required_bones` 列表（L59-60）没有包含 `左足/左ひざ/右足/右ひざ`（`上半身` 在 L87-89 另有单独检查），但这些骨骼在 L177-198 被直接索引，缺骨时错误提示会指错方向。

**建议**：改为 `edit_bones.get("左手首")`，把条件写成 `hand.head if hand else edit_bones["左ひじ"].tail`；把后续会用到的骨骼补进 `required_bones`；整个构建放在 `try/finally` 里恢复进入时的模式（现在失败会停留在 EDIT）。

**成本**：20 分钟。

**必须修**：直接影响 Vroid/无手骨骨架的可转换性，且错误信息误导排查方向。

---

### A3. 重命名后「用 MMD 名称重新检测上半身链」实际不生效（编辑模式读到旧骨骼快照）

**位置**：[rename_bones_operator.py:74-93](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/rename_bones_operator.py#L74-L93)，配合 [preset_operator.py:467-505](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/preset_operator.py#L467-L505)

**问题**：第一次检测在改名之前、用原始名，能成功（`data.bones` 里的旧名字就是原名）。改名在 **编辑模式** 中对 `edit_bones` 完成；随后 L93 立刻再调一次 `auto_detect_upper_body_chain`。该函数内部读的是 `armature.data.bones`（L477），而 Blender 的 `Armature.bones` 在编辑模式下是「进入编辑模式时的快照」，新增/改名的骨骼不反映；此时查 `上半身`/`首` 查不到，函数在 L481 返回 `False`。于是 `upper_body2..5` 等属性仍保留**改名前的名字**，注释声称的「确保属性一致」没有发生。

**影响**：预设导出/导入会带上失效旧名；二次执行「重命名」会对这些骨骼报「未找到」。这不是外观问题，是场景数据被写错。

**依据**：Blender API 中 `Armature.bones` 仅在对象模式下保证最新；同文件其它地方都刻意在编辑模式用 `edit_bones`，只有这里用了 `data.bones`。

**建议**：把第二次检测移到 L100-102 恢复对象模式之后；或给 `auto_detect_upper_body_chain` 增加 `edit_bones` 分支（在编辑模式用 `edit_bones[neck].parent` 遍历）。推荐后者，顺手解决 `load_preset` 在编辑模式下自动检测失效的问题。

**成本**：10 分钟（移动调用）或 30 分钟（支持编辑模式）。

**必须修**：静默写错场景数据，排查成本高。

---

### A4. `check_and_scale_skeleton` 的 `scaled` 永远为 `False`

**位置**：[bone_utils.py:122-148](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/bone_utils.py#L122-L148)

**问题**：函数声明 `scaled = False`，在 `skeleton_height > 10` 分支里执行了 `obj.scale *= scale_factor` 和 `apply_armature_transforms`，但**全函数没有任何 `scaled = True`**（已全文件检索确认）。调用方 [`rename_bones_operator.py:66-67`](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/rename_bones_operator.py#L66-L67) 的提示分支因此永远不会执行，用户模型被缩小 10 倍或 100 倍却没有任何反馈，容易误判成「模型坏了」。

**建议**：缩放成功后 `scaled = True`；并把「检测到 X m，已缩放为 Y m」写进 `self.report`。

**成本**：2 分钟。

**必须修**：属于「已经做了操作却不告诉用户」的确定性缺陷，且修复极廉价。

---

### A5. 简易身体刚体的「圆拟合」最小二乘公式错误，`n > 3` 时必然退化为质心

**位置**：[body_rigid_builder.py:166-187](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L166-L187)

```python
x = A_mat.transposed() @ ((A_mat @ A_mat.transposed()).inverted() @ b_vec)
```

**问题**：`A` 是 `n×3`（n = 权重顶点数）。`A @ A.T` 是 `n×n`，秩最多 3；实际顶点数远大于 3，矩阵必然奇异，`.inverted()` 抛异常 → 被 `except Exception` 吞掉 → `C_fit = centroid`。也就是说注释里的「圆拟合（最小二乘法）」在生产数据上**从来没有执行过**，半径用的是「到质心的最大距离」，位置偏差全部由质心决定，且异常被静默吞掉，未来真正的错误也看不到。

**建议**：在投影平面（u/v）内解正规方程 `x = (AᵀA)⁻¹ Aᵀ b`（3×3，可逆性远好），或改用更稳的 Kasa 拟合；`except` 里至少 `print`/记录回退原因。

**成本**：15 分钟。

**必须修**：功能名不副实，且症状（刚体位置偏）难以归因。

---

### A6. 胸部物理：弹簧关节用刚体名命名、判重条件写错，重跑会重复创建关节

**位置**：[chest_physics_builder.py:356-386](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/chest_physics_builder.py#L356-L386)；关节定义见同文件 L389-404

**问题 A（命名/重名）**：`_get_spring_definitions()` 为每个弹簧生成了 `"joint": f"J.{prefix}胸上"`，但 `_create_spring_joints` 从未读取 `sd["joint"]`，而是 `setup_joint_object(name=rb2.name, ...)`。`rb2` 是刚体对象（`左胸上/右胸上`），该名字已被刚体占用，Blender 会把关节自动改成 `左胸上.001`，MMD 侧看到的也不是约定的 `J.xxx`。

**问题 B（判重失效）**：L370 的 `if rb2.name in bpy.data.objects and bpy.data.objects[rb2.name].mmd_type == "JOINT": continue` 检查的是**刚体对象本身**，其 `mmd_type` 为 `RIGID_BODY`，条件永远为假；再点一次「自动构建胸部物理」就会再建一组关节（名字继续 `.001/.002`）。

**影响**：导出的 PMX 关节名不合规范、重跑后物理部分重复，肉眼在 Blender 里不容易发现。

**建议**：`name=sd["joint"]`、`name_e=sd["joint"]`；判重改为按 `sd["joint"]` 在关节组内查找并更新参数（或先删除同名旧关节再建）。同时 `_build_breast_bone_chain` 只捕获了 `MemoryError`，`raise ValueError(f"骨骼 '{user_bone}' 不存在")`（L198）会以 traceback 形式抛出并把模式留在 EDIT，建议改成 `self.report + return {'CANCELLED'}`（或 `try/finally` 恢复模式）。

**成本**：20-30 分钟。

**必须修**：产出物（PMX）与重复执行后的场景状态都是错的。

---

### A7. 胸部左右骨骼声明为对称属性，但左右映射表缺项，自动填对侧静默失效

**位置**：[properties.py:11-22](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/properties.py#L11-L22) 的 `_symmetric_bone_props` 含 `left_chest_bone/right_chest_bone`；[preset_operator.py:42-73](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/preset_operator.py#L42-L73) 的 `_left_right_mapping` 没有这两个键。

**问题**：`properties.register_properties` 给胸骨属性挂了「自动填对侧」的 update 回调（L81-103），但 `try_fill_symmetric_bones` 第一步 `_left_right_mapping.get(first_prop)` 返回 `None` 就直接 `return False`。所以面板上选了 `左胸上 2` 不会自动填右胸，与手指/腿的体验不一致，且没有任何提示。

**建议**：补上 `'left_chest_bone': 'right_chest_bone'` 与反向两项（并核对 `_symmetric_bone_rules` 对「左胸上 2 / 右胸上 2」的字符串替换能否命中）。

**成本**：5 分钟。

**必须修**：小改动、确定性失效。

---

### A8. 导出骨骼信息时 `is_weight_bone` 恒为 `False`

**位置**：[export_bones_info_operator.py:90-117](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/export_bones_info_operator.py#L90-L117)

**问题**：`obj` 是骨架对象。Armature 对象虽然有 `vertex_groups` 属性，但基本为空；`obj.data` 是 `Armature`，没有 `vertices`，所以 L107 的 `hasattr(obj.data,'vertices')` 为假。三条判定全部走空 → 每个骨骼都导出 `is_weight_bone: false`。这个字段用于调试/生成预设，失真会误导后续判断。

**建议**：改成遍历「绑定了该骨架的网格」（`ARMATURE` 修改器或父级为骨架），先一次性建立 `weighted_bone_names = {vg.name ...}`，再判断；不要在每个骨骼里做「骨骼×顶点×组」的三重循环（见 C1 同类问题）。

**成本**：30 分钟。

**必须修**（工具输出确定性错误；若这个字段没人用，也可以直接删掉，避免误导）。

---

## 四、健壮性（建议修）

### B1. 「网格必须是骨架的直接子级」假设过强，物理/权重会静默不生效

**位置**：[body_rigid_builder.py:46](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L46)、[add_twist_bone_operator.py:246](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_twist_bone_operator.py#L246)、`chest_physics_builder.py` 的 `calculate_breast_sphere_fit`、`add_leg_d` 的顶点组改名。

**问题**：都用 `obj.parent == armature` 判断网格归属。从网站下载的 Blender 模型、部分 FBX 导入结果经常是「网格在集合里，用 Armature 修改器绑定但父级不是骨架」。这些网格会被排除：胸部拟合报「无法计算」（勉强有提示），捩骨权重、足 D 顶点组改名则是**静默跳过**，用户只会觉得「物理没效果」。

**建议**：抽一个 `iter_skinned_meshes(armature)`：父级是骨架 **或** 任意 `ARMATURE` 修改器指向该骨架；所有涉及网格的模块统一调用。

**成本**：30 分钟。

---

### B2. 足 D 骨算子缺少前置校验，且不恢复原模式

**位置**：[add_leg_d_bones_operator.py:16-35](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_leg_d_bones_operator.py#L16-L35)、L198-201、L308

**问题**：直接 `edit_bones["右足"]`、`edit_bones["右ひざ"]`、`edit_bones["右足先EX"]` 索引；用户漏做「2.补全缺失骨骼」或改过名时抛 `KeyError` traceback（Blender 只显示「Python 脚本错误」），并且模式停在 EDIT。`existing_d_bones` 分支无条件 `mode_set(OBJECT)`，把用户从编辑模式踢出。

**建议**：入口统一校验所需骨骼，缺失时 `self.report({'ERROR'}, "缺少 ...，请先执行第 2 步")`；记录 `original_mode` 并在 `try/finally` 中恢复。`add_shoulder_p_bones_operator` 已经用了 `context_mode_to_mode_set`，可以复制该模式。

**成本**：20 分钟。

---

### B3. 物理算子内部静默重跑「mmd_tools 转换」

**位置**：[chest_physics_builder.py:134](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/chest_physics_builder.py#L134)、[body_rigid_builder.py:265](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L265)

**问题**：两个物理算子开头直接 `bpy.ops.object.use_mmd_tools_convert()`，随后再 `FnModel.find_root_object`。如果模型已经转换过，这个调用是否会重复创建 MMD 根/重复转换取决于 mmd_tools 的版本与选择集，属于「点击物理按钮却触发了整个模型转换」的隐式副作用；并且该调用复用 `preset_operator.OBJECT_OT_use_mmd_tools_convert`，只捕获 `TypeError/AttributeError`，mmd_tools 抛 `RuntimeError` 时会直接中断。

**建议**：先 `FnModel.find_root_object(armature)`；找到就跳过转换，找不到就明确报错「请先执行第 5 步」而不是替用户隐式转换。若确实需要隐式转换，至少选择集/模式前后保存恢复，并把 `RuntimeError` 转成 `self.report`。

**顺带**：`use_mmd_tools_convert`（`preset_operator.py:514-542`）只选中骨架对象就调用 `mmd_tools.convert_to_mmd_model`，而 mmd_tools 通常按「选中对象」转换。若用户只选中骨架、未选中网格，可能只转换骨架或得到不完整模型；且函数注释写「恢复原始选择状态」，实际只把骨架设回活动，没有恢复原选择集。

**成本**：30 分钟。

**不确定**：不同 mmd_tools 版本对重复转换的容忍度未知，建议实测「已转换模型再点一次」的行为。

---

### B4. 归正骨骼：备份早于校验、3D 游标与选择不恢复

**位置**：[correct_bones_operator.py:28-55](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/correct_bones_operator.py#L28-L55)、L63-71

**问题**：
1. 备份对象在 L28 创建，而 L41 才校验 `上半身` 是否存在；校验失败 `CANCELLED` 后，场景里留下一个隐藏的 `xxx_backup` 对象。
2. `original_cursor_location` 保存后从未使用，3D 游标被永久移动到「上半身正下方地面」。这会影响用户后续所有依赖游标的操作（新建物体、吸附、旋转中心）。
3. `select_all(DESELECT)` 后只选中骨架，用户原有的多选状态丢失。

**建议**：先校验再备份；操作结束（含失败）在 `finally` 中恢复游标和选择状态。

**成本**：10-15 分钟。

---

### B5. 自动填充的边界行为：清空不清链、活动对象不是骨架时不触发

**位置**：[properties.py:57-103](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/properties.py#L57-L103)、[preset_operator.py:75-106](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/preset_operator.py#L75-L106)

**问题**：
1. 用户把「手指第一节」字段清空时，update 回调走 `auto_fill_finger_bones`，第一根骨名为空直接 `return False`，但之前自动填进去的第二/三节仍保留。后续重命名会用这些残留名字改骨，属于脏数据。
2. update 回调要求 `context.active_object.type == 'ARMATURE'`。结合 A1，用户从面板下拉框（网格为活动对象）选择骨骼时，自动填充完全不发生，与 README 描述的体验不符。
3. `auto_fill_finger_bones` 只在 `EDIT_ARMATURE/POSE` 下工作，对象模式下静默返回。

**建议**：清空第一根时同步清空第二/三；把「解析骨架」和「是否可读层级」统一到 `resolve_armature`；在无法自动填充时用 `self.report`/UI 提示而不是静默。

**成本**：30 分钟。

---

### B6. 预设 I/O 未校验，坏文件只打控制台；文件编码未显式声明

**位置**：[load_preset_operator.py](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/load_preset_operator.py)、[preset_operator.py:248-300](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/preset_operator.py#L248-L300)（导出/导入预设）

**问题**：`load_preset` 只捕获文件不存在；JSON 解析失败、顶层不是 `dict`、值不是字符串都会以 traceback 结束，且面板上的枚举是异步定时器触发，用户点完后只看到枚举变了、骨骼没变。`import_preset` 同样未校验结构。文件读写没有 `encoding='utf-8'`，Windows 默认编码下第三方预设可能出现编解码错误（导出端 `ensure_ascii` 默认 True，暂时掩盖了问题）。

**建议**：统一 `try/except json.JSONDecodeError + isinstance(dict)`，失败时用 `self.report({'ERROR'}, ...)` 并把枚举恢复；读写显式 `encoding='utf-8'`。

**成本**：15-20 分钟。

---

### B7. 高度缩放策略粗糙，且只在一个分支处理对象级缩放

**位置**：[bone_utils.py:108-148](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/bone_utils.py#L108-L148)

**问题**：
1. L113 只 `transform_apply(rotation=True, scale=False)`。若高度 ≤10，对象本身残留的 scale（例如用户手动缩放到 0.1、或导入设置异常）不会被应用，后续骨骼长度/物理尺寸按局部坐标计算，可能整体偏小/偏大。典型 cm 模型（对象 scale=0.01、局部骨长 170）会被 L126 分支救回来，但「局部坐标已是米、对象 scale≠1」的组合会漏掉。
2. 缩放因子按 10 的幂取整：12m 的模型会直接变 1.2m，而不是 ~1.7m。对非标准比例模型偏激进。
3. L136 直接把 `obj.scale` 重置为 (1,1,1)，丢弃了用户原有的对象级缩放（虽然此分支假设需要归一化，但建议先记录并在报告里说明）。

**建议**：始终 `transform_apply(rotation=True, scale=True)` 把对象变换烘进骨架/网格；缩放因子改为「目标高度 1.7m」的比例（或至少 `10/height` 向上取到 10 的幂），并在 UI 里告诉用户缩放前后高度。

**成本**：20-30 分钟。

**不确定**：是否有意保持 MMD 的「1 单位 = 1 米」并只接受 10 倍整数缩放，需要作者确认。

---

### B8. 「创建骨骼集合」会清空用户已有集合，且在次标准骨骼算子里被隐式调用

**位置**：[collection_operator.py:67-93](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/collection_operator.py#L67-L93)；调用点：[add_twist_bone_operator.py:64](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_twist_bone_operator.py#L64)、[add_leg_d_bones_operator.py:311](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_leg_d_bones_operator.py#L311)、[add_shoulder_p_bones_operator.py:209](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_shoulder_p_bones_operator.py#L209)。

**问题**：L75-78 无条件遍历并 `collections.remove(coll)`，删除骨架上所有骨骼集合（包括用户自建集合、自定义可见性/颜色、骨骼分配）。用户只点「追加捩骨/足 D/肩 P」时，这些集合也会被一起清空并重建，属于未提示的数据丢失；若用户已有自定义集合命名与预设同名，还会被覆盖。

**建议**：改为「增量更新」：预设集合不存在则创建、存在则复用；只清理本插件命名空间内的集合（或提供 `rebuild` 参数，默认 `False`）；在删除前用 `self.report`/确认对话框提示。次标准骨骼算子不要无条件调用「重建集合」。

**成本**：20-30 分钟。

---

## 五、性能

### C1. 简易身体刚体是 O(骨骼数 × 顶点数 × 顶点组数)，大模型会明显卡顿

**位置**：[body_rigid_builder.py:52-74](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L52-L74)（每个骨遍历所有网格的所有顶点），L285 对所有 `use_deform` 骨执行。

**问题**：100 根变形骨 × 10 万顶点，内层再遍历 `vertex.groups`，就是千万级 Python 循环，且每根骨都重建 `v_world`。此外它会给**每根变形骨**（含手指、脚趾、捩骨）建刚体，刚体数量与权重阈值 0.4 都由硬编码决定。

**建议**：一次遍历所有顶点，按 `group.group` 建立「顶点组 index → (顶点, 权重)」倒排表；每根骨只查自己的桶。顺手把「哪些骨需要刚体」做成白名单/黑名单（排除手指、捩骨、`use_deform=False`）。

**成本**：1-2 小时（重构后可直接复用给 `export_bones_info` 与胸部拟合）。

**收益**：大模型从分钟级降到秒级；也避免无意中生成几百个刚体。

---

### C2. 合并骨骼时逐顶点写权重、逐骨扫描全场景

**位置**：[merge_bones_operator.py:51-55](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/merge_bones_operator.py#L51-L55)、L79-84

**问题**：`target_vg.add([vertex.index], weight, 'ADD')` 对每个顶点单独调用一次（Blender 的 Python API 每次调用都有跨语言开销）；外层每合并一根骨，都对 `bpy.context.scene.objects` 全量遍历并检查每个网格的全部修改器。

**建议**：先在算子入口收集一次「绑定到该骨架的网格」（与 B1 的 helper 复用），并在权重合并时按权重值分组批量 `add(indices, weight, 'REPLACE')`，或者直接用 `bmesh`/`vertex.group` 批量操作。

**成本**：30 分钟。

---

### C3. 内存检查过于频繁且判定过于激进

**位置**：[physics_utils.py:90-135](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/physics_utils.py#L90-L135)、[body_rigid_builder.py:239](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L239)、L345-350

**问题**：
1. `calculate_simple_body_rigid_params` 每根骨都 `_check_memory_and_gc()`，且末尾 `_check_memory_and_gc(force=True)`，即每根骨一次完整 `gc.collect()`。100 根骨就是 100 次全量 GC，纯属额外开销。
2. 判定用的是**系统整体内存占用率**：只要系统里别的程序把内存用到 80%，Blender 就会被判「内存不足」并中止（哪怕 Blender 自身只用了 100MB）。笔记本/多开环境下很容易误伤。
3. `_get_memory_info` 里 `bpy.app.debug_memory_usage()` / `bpy.app.debug_memory_peak()` 疑似不存在于 Blender Python API（被裸 `except` 吞掉），导致 `used_gb/peak_gb` 永远拿不到，但 `_check_memory_and_gc` 又依赖 `memory_percent`（Windows 分支可用），逻辑割裂。

**建议**：只在「每 N 个刚体」或「显式 force」时 GC；判定改为「Blender 自身 RSS 超过阈值」或「系统可用内存低于 X GB」；不存在的内存 API 直接删除，别用裸 `except` 掩护。

**成本**：15-20 分钟。

**不确定**：`bpy.app.debug_memory_usage` 是否在某些 Blender 版本/构建中存在，需实测确认；但即便存在，当前调用点也没有意义。

---

## 六、可维护性与结构

### D1. 骨骼名/左右关系没有单一数据源，已经导致 A7 这类漏配

**位置**：[bone_map_and_group.py](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/bone_map_and_group.py)（`mmd_bone_map`、`mmd_bone_group`）、[preset_operator.py:42-73](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/preset_operator.py#L42-L73)（左右映射/替换规则）、[properties.py:11-22](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/properties.py#L11-L22)（对称属性列表）、[complete_bones_operator.py:52-67](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/complete_bones_operator.py#L52-L67)（必需骨列表）以及 `ik_operator` 里的日文骨名。

**问题**：同一个「某骨是左/右/对称/必需/属于哪个集合」的信息分散在 5 处，新增/修改骨骼时必然漏配（胸部漏配已经在 A7 实际发生）。此外 `check_single_bone_position`（左侧应在 +X）与未被调用的 `check_bone_position_direction`（要求左侧世界 X < 中心）符号相反，后续维护者很难判断哪个是对的。

**建议**：建一张 `BONE_SPEC` 表（属性名、MMD 名、左右侧、是否对称、是否必需、所属集合、父级规则、roll 规则），由它派生 `mmd_bone_map`、属性注册、对称映射和校验；`check_bone_position_direction` 要么删除，要么改符号并接回调用点。

**成本**：半天（一次性整理，后续每加一根骨都省事）。

---

### D2. 三套「dummy + shadow + COPY_TRANSFORMS + 建骨骼集合」代码几乎重复

**位置**：[add_twist_bone_operator.py:170-238](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_twist_bone_operator.py)、[add_leg_d_bones_operator.py:240-300](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_leg_d_bones_operator.py)、[add_shoulder_p_bones_operator.py:150-210](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_shoulder_p_bones_operator.py)

**问题**：`_dummy_*` 的创建、`_shadow_*` 的创建、`COPY_TRANSFORMS`（`owner_space/target_space='POSE'`、`influence=1`、约束名 `mmd_tools_at_dummy`）在三个文件里复制粘贴；参数（Z 偏移 0.08/0.1、`to_max_rot = -180` 的 MMD 反向约定）各自硬编码。任何一处修 bug（例如 B1 的网格收集、模式恢复）都要改三遍。

**建议**：抽 `mmd_bone_utils.create_dummy_shadow_pair(...)` 与 `create_copy_transform(...)`，三个算子只保留各自的几何参数；集合创建也走同一个 helper（见 B8 的集合重建问题）。

**成本**：2-3 小时。

---

### D3. 死代码、调试打印与误导性注释

**位置/清单**：
- `properties.py:4,66-67,90-91`：`_current_updating_prop` 只写不读，可删。
- `properties.py:126`：`get_registered_props()` 无人调用。
- `preset_operator.py:366-445`：`check_bone_position_direction` 无人调用，且与 `check_single_bone_position` 的左右符号相反。
- `preset_operator.py:300-363`：`check_single_bone_position` 与 `fill_from_selection_specific` 里有大量 `print` 调试输出（每次点按钮刷十几行），且 `hasattr(bone,'head')` 的两个分支完全相同。
- `pose_operator.py:208-209`：`is_temp_mesh` 清理逻辑没有任何代码会把该标记置 True，是死分支。
- `tools/arm_forearm_tool.py:34-36`：保存了 `old_mode/old_quat` 却没有使用。
- `merge_bones_operator.py:76`：`if child != start_bone` 在 DFS 结果里不可能出现该情况，属于无效防御。
- `add_twist_bone_operator.py:277` 的 docstring 说「主捩 20-40%」，代码 L327-331 实际是「主捩 80-100%」（代码看起来才符合 MMD 惯例，应改注释）。

**建议**：删除死代码/死分支，调试输出改成 `self.report` 或 `logging`（保留错误路径），注释与实现对齐。

**成本**：30-40 分钟。

---

### D4. 版本与文档不一致

**位置**：[`__init__.py:4`](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/__init__.py#L4) `"version": (2, 6)`；[README.md:133](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/README.md) 写「Blender 3.0.0 或更高版本」；CHANGELOG 最新为 `1.1.0`；`bl_info["blender"] = (4,0,0)`。

**问题**：用户安装页显示的版本与 CHANGELOG 对不上；按 README 在 Blender 3.x 安装会被 `bl_info` 拒绝。`collection_operator.py` 里还留着 Blender 3.x 的 `pose.group_add` 回退分支，说明兼容目标本身也不清晰。

**建议**：确定唯一版本号（建议与 CHANGELOG 对齐），README 改成「Blender 4.0+」，并注明 3.x 回退分支是否还有意义（无意义则删）。

**成本**：5 分钟。

---

## 七、不确定项（需在 Blender 内实测后再决定是否改）

| 编号 | 位置 | 疑问 | 为什么不确定 |
|---|---|---|---|
| U1 | [arm_forearm_tool.py:60-80](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/arm_forearm_tool.py#L60-L80) | 世界空间旋转校正只做了 `parent_rot⁻¹ * world_corr`，没有用静止姿态矩阵 `R` 做共轭（正确形式应为 `R⁻¹ P⁻¹ C P R`），对非零 rest 方向的手臂可能方向错误 | 作者的实测结果未知；不同骨架 rest 朝向会让误差不同 |
| U2 | [add_twist_bone_operator.py:302-348](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/add_twist_bone_operator.py#L302-L348) | 权重总和被乘 `0.65` 后写入并 `REPLACE` 原组，若 Blender 不自动归一化，顶点会少 35% 的变形量 | 取决于 Blender 版本对 armature 权重的归一化行为与作者意图；建议用一个简单平面网格实测 |
| U3 | [body_rigid_builder.py:318-325](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/body_rigid_builder.py#L318-L325) | 所有身体刚体设为 `type="0"`（跟随骨骼/静态），且 `collision_group_mask[1]=True`（与自身组碰撞） | MMD 刚体分组约定与「简易身体」的设计目标未在文档说明，可能是有意的静态碰撞体 |
| U4 | [pose_operator.py:60-90](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/operators/pose_operator.py#L60-L90) | A-Pose 旋转固定绕 **全局 Y**、且按「左/右」取符号，隐含模型面朝 -Y | 面朝 +Y 的模型可能把手往上抬；仓库没有测试模型说明朝向约定 |
| U5 | [physics_utils.py:50-51](file:///c:/Users/UITCIS/OneDrive/Code/addons/Convert-to-MMD/tools/physics_utils.py#L50-L51) | `bpy.app.debug_memory_usage()` / `debug_memory_peak()` 可能不存在 | 被裸 `except` 吞掉，无法从日志看出；不同 Blender 构建可能不同 |

---

## 八、结论：最值得先做的 5 项

按「用户可见影响 × 修复成本」排序：

1. **A1（活动对象解析）** — 选中网格时整条向导不可用，是最高频的「插件没反应」来源。抽一个 `resolve_armature`，1 小时内解决，且为 B5 铺路。
2. **A3（重命名后的链检测失效）** — 静默把上半身链属性写成过期名字，影响预设与后续重跑。移动调用位置或改成支持 `edit_bones`，10-30 分钟。
3. **A6（胸部弹簧关节命名/重复创建）** — 直接污染最终 PMX 的物理部分，且重跑叠加。用 `sd["joint"]`、修正判重，20-30 分钟。
4. **A5（刚体圆拟合公式）** — 核心算法在生产数据上从未生效，修 3×3 正规方程即可，15 分钟；顺便去掉吞异常的 `except`。
5. **A4 + A7 + A2 + B4（四个单点快速修复）** — `scaled=True`、补齐胸部左右映射、`edit_bones.get` 兜底、恢复 3D 游标/选择；合计不到 40 分钟，立刻消除「操作了但没反馈 / 静默失效 / 残留垃圾对象」。

紧随其后的第二梯队：**A8（导出字段失真）、B1（网格归属 helper，同时为 C1/C2 铺路）、C1（刚体权重预计算）**。这三项建议合并成一次小重构：先写 `iter_skinned_meshes()` 与「顶点组倒排表」，再改三个调用点，收益/风险比最高。

**不必现在做**：D1 的骨骼规格表重构工作量较大，建议等下一次「新增骨骼类型」需求时再做；D2 的公共 helper 可以在修 B1/B2 时顺手抽取，避免为重构而重构。

---

## 九、验证建议（修复后）

1. **静态**：`python -m compileall`（当前已通过）。
2. **手工流程矩阵**（Blender 4.0/4.2/4.3）：
   - 选择「骨架」 vs 选择「网格」各跑一遍完整 7 步，确认按钮行为一致（验证 A1）。
   - 无手骨/无足骨模型跑「补全骨骼」，确认报错可读且模式恢复（验证 A2）。
   - 重命名后检查 `upper_body2_bone` 等 Scene 属性是否已是日文名；导出预设查看（验证 A3）。
   - 缩放过的 cm 模型（对象 scale=0.01）检查最终高度与提示（验证 A4/B7）。
   - 胸部物理：连续点击两次，确认关节对象名 `J.*` 且数量不增加（验证 A6）。
   - 只用 Armature 修改器、父级不是骨架的网格：确认刚体/捩骨仍生效（验证 B1）。
3. **性能基线**：10 万顶点、100 变形骨，记录「简易身体刚体」耗时（验证 C1）。
