# dev —— 非插件内容

**这个目录不属于 Blender 插件本体，不会被打进发行包。**

发行流水线（`.workflow/发行.yml`）按白名单复制 `__init__.py properties.py ui_panel.py
bone_map_and_group.py bone_utils.py encoding_patch.py operators presets tools
README.md LICENSE CHANGELOG.md`，`dev/` 不在其中，所以这里放什么都不影响安装包体积。

判断一个文件该放哪：**插件运行时会不会 import / 读取它**。
会 → 放 `tools/` 或仓库根；不会（验证脚本、测试、截图、笔记、审查报告）→ 放 `dev/`。

## 目录结构

```
dev/
├── test_mapping_core.py       骨骼映射算法单测（不需要 Blender）
├── test_apose_validate.py     A-Pose 输入校验提示文案单测（不需要 Blender）
├── check_baseline.py          基线检查：filled/solid/low/链断裂 + 关键字段（支持 --armature）
├── check_core.py              核心骨取值核对
├── check_chain.py             14 类错配探针（父子关系反了应被否决）
├── verify_mapping.py          映射结果人工可读导出
├── generality_probe.py        泛化探针：4 套未参与调参的命名体系
├── probe_structure.py         骨架结构探针：多骨架文件的骨数/根骨/命名样本
├── explain_field.py           字段候选解释：为什么选中这根、正确骨为何被否决
├── debug_chain.py             单根骨的链关系判定明细（父子语义/辅助骨/域）
├── scan_all_models.py         批量扫描：目录里每个 .blend 的每套骨架能否识别
├── scan_snapshot.txt          上面脚本在 136 个模型的目录上跑出的快照（对比用）
├── scan_new.txt               候选生成优化后的同一份扫描（对比对象为上一行）
├── scan_axis.txt              侧轴/上轴判据修正后的扫描快照
├── scan_fix.txt               姿态判定与侧别修复前的扫描快照
├── scan_geo.txt               几何身体划分接入后的扫描快照（当前基线）
├── posture_scan.txt           193 套骨架的站姿判定结果
├── geo_scan.txt               9 套骨架的几何划分与骨名对账
├── compare_scan.py            对比两份扫描快照，列出变好/变差的骨架
├── probe_search_cost.py       每套骨架的回溯节点数与耗时（SEARCH_CAP / NO_EDIT 可覆盖）
├── probe_profile.py           cProfile 剖析 solve 各阶段耗时
├── probe_geo_limbs.py         几何身体划分探针：不看骨名的臂/腿/躯干划分，与骨名对账
├── probe_posture.py           站姿判定探针（站立 A/T-pose / 非站立 / 判不了）
├── probe_classify.py          人形 / 部分人形 / 非人形分类结果
├── probe_axes.py              各骨架的侧轴与上轴候选及其分布
├── probe_axis_rot.py          骨架绕高度轴的旋转量（检验轴对齐假设）
├── probe_symmetry.py          镜像对称面拟合（旋转不变量）
├── probe_side.py              侧别符号与左右配对统计
├── probe_orientation.py       骨架朝向（上/前/侧）判定
├── probe_restpose.py          rest 姿态下的骨骼旋转是否为单位（判断模型自带非站姿）
├── probe_pose_source.py       骨骼坐标取自 rest 还是 pose/动画
├── probe_noname.py            抹掉骨名后仅靠几何能否定位各部位
├── render_model.py            正交三视图 + 透视 X-Ray 渲染，人工核对骨架（输出到 renders/）
├── apose_operator_smoke.py    A-Pose 最小场景跨版本兼容（4.0/4.2 无工程文件）
├── apose_operator_verify.py   A-Pose 真实工程端到端
├── apose_render/              A-Pose 渲染对照脚本与截图（脚本用 __file__ 同目录出图）
├── docs/                      审查报告与算法笔记
└── reference/                 本地参考资料（.gitignore 忽略，不进仓库）
```

## 常用命令

以下命令都在**仓库根目录**执行。

```bash
# 单测（141 项，纯 Python，无需 Blender）
python -m unittest discover -s dev -p "test_*.py"

# 泛化探针（四套命名体系，核心骨应 15/15）
python dev/generality_probe.py

# 基线 / 核心骨 / 错配探针（需要 Blender）
BLENDER="/e/Programs/blender-5.1.0-windows-x64/blender.exe"
"$BLENDER" --background --factory-startup --python dev/check_baseline.py -- model.blend
"$BLENDER" --background --factory-startup --python dev/check_core.py     -- model.blend
"$BLENDER" --background --factory-startup --python dev/check_chain.py    -- model.blend

# 一个 .blend 里有多套骨架时（角色 FP/TP/头发、DAZ 的服装+rig），
# 默认取第一套，可能不是主骨架，必须指定：
"$BLENDER" --background --factory-startup --python dev/check_baseline.py -- \
    model.blend --armature "PC_TP_Female_Red02.ao"
"$BLENDER" --background --factory-startup --python dev/probe_structure.py -- \
    model.blend --all          # 先看有哪些骨架、骨名怎么写

# 某字段选错了，查它为什么选这根骨：
"$BLENDER" --background --factory-startup --python dev/explain_field.py -- \
    model.blend --armature 2 left_upper_arm_bone
"$BLENDER" --background --factory-startup --python dev/debug_chain.py    -- \
    model.blend --armature 2 left_upper_arm_bone Bip001-L-UpperArm001

# 整个目录扫一遍（每套骨架一行，TAB 分隔，便于 awk/python 汇总）
"$BLENDER" --background --python dev/scan_all_models.py -- a.blend b.blend ...

# 性能：每套骨架的回溯节点数与耗时（判断有没有撞搜索上限）
"$BLENDER" --background --factory-startup --python dev/probe_search_cost.py -- a.blend
#   环境变量：SEARCH_CAP=20000000 放宽节点上限看精确解；NO_EDIT=1 关闭编辑距离档

# 性能：把 solve 各阶段耗时拆开（cProfile，开销约 2~3 倍）
"$BLENDER" --background --factory-startup --python dev/probe_profile.py -- a.blend

# 对比两次全量扫描，列出所有变好/变差的骨架
python dev/compare_scan.py dev/scan_snapshot.txt dev/scan_new.txt
```

## 当前基线（确定性，可复现）

三套长期回归基线（改动后必须复测，数字不得回退）：

| 模型 | 骨架 | 填充 | 稳妥 | 链断裂 |
|---|---|---|---|---|
| Vipe - test（TP） | PC_TP_Female_Red02.ao | 58/64 | 46 | 0 |
| Gley | TFD_Gley | 58/64 | 53 | 0 |
| DNF | gai.blend | 59/64 | 50 | 0 |

新增模型实测（2026-11-28）：

| 模型 | 骨架 | 填充 | 稳妥 | 链断裂 | 说明 |
|---|---|---|---|---|---|
| Vipe - test（FP） | PC_FP_Female_Red02.ao | 50/64 | 38 | 0 | 修前 46/28，左右反、中心骨全空 |
| 蒂法 | Tifa_Default_Armature | 58/64 | 52 | 0 | 无独立上臂 DEF 骨，上臂留空 |
| 蒂法 | Tifa_metarig | 61/64 | 56 | 0 | |
| 镜 | SK_0102503000029.ao | 52/64 | 51 | 0 | 前两套是面部 / 头发物理骨架 |
| knight | root | 57/64 | 52 | 0 | |
| tsukushi | Tsukushi_rig | 54/64 | 35 | 0 | 24 套骨架；rig 含大量控制骨 |
| tsukushi | Armature | 50/64 | 52 | 0 | 上臂骨名为 arm left shoulder，无 upperarm |
| HIT2 Orb2 | Armature | 45/64 | 42 | 0 | 修前 39/37，法球骨抢占脊柱链 |

OG_14 没有骨架（未绑定），无法测试。

### 目录批量扫描（136 个 .blend，2026-11-28）

`E:\3D Objects\downloaded_models` 全量扫描（`scan_snapshot.txt`）：

| 项 | 结果 |
|---|---|
| .blend 文件 | 136 个 |
| 无骨架（静态场景 / 未绑定模型） | 46 个文件 |
| 骨架总数 | 147 套 |
| 其中骨数 ≥30（角色 / 半身） | 116 套，平均填充 46.6/64 |
| 其中骨数 <30（道具 / 单件服装子骨架） | 31 套，不参与评价 |
| 核心骨 17/17 全对 | 66 套（57%），修前 30 套 |
| 有链断裂 | 32 套 |
| 左右侧别判反 | 5 套 |

候选生成优化后（2026-11-28 第二轮，`scan_new.txt`）：

| 指标 | 优化前 | 优化后 |
|---|---|---|
| 合计填充 | 5792 | 5794 |
| 合计稳妥 | 4346 | 4350 |
| 链断裂合计 | 196 | 184 |
| 核心骨非空骨架 | 146 | 146 |

198 条骨架里 185 条填充数完全不变、188 条稳妥数完全不变。4 条填入数少 1
而**链断裂同时减少**（沙袋 12→10、Rebirth 头发 10→6）——搜索真正跑到
目标函数最优后，选了「少填一根但总分更高」的解。目标是
`score + FILL_BONUS`，与 filled 指标本来就不是一回事。

## 候选生成的性能（2026-11-28）

`solve()` 的耗时分布（Tifa_rig，1792 骨，改前总计 40.5s 含 profile 开销）：

| 阶段 | 改前 | 说明 |
|---|---|---|
| `score_candidate` | 95.5% | 64 字段 × 骨数，逐个打分 |
| 其中 `difflib.ratio` | 43% | 编辑距离档，49 万次调用 |
| 其中 `_tokens` / `re.sub` | 20% | 87 万次，**原先无缓存** |
| `chain_relation_violated` | 23% | 内部别名判定同样无缓存 |
| DFS 回溯 | <2% | 200k 节点上限**不是**瓶颈 |

三处改动，全部是「等价加速」，不改判定逻辑：

1. **纯函数缓存**：`_normalize` / `_tokens` / `_is_support_bone_name` /
   `_bone_matches_category` / `difflib.ratio`。输入空间只有骨名那么多，
   同一根骨名会被 64 个字段各问一遍。
   `_tokens` 返回 **tuple**（可缓存），调用方只读不改性。
2. **硬否决前置**：`score_candidate` 里把脊柱链 / 中轴 / 手指域 / 手臂域
   这些「集合成员测试」提到 `name_contribution` 之前。否决之间是 AND，
   先后不影响结果，但能把注定被否决的骨挡在编辑距离之外——大骨架
   70% 以上的骨是被域过滤掉的，`name_contribution` 调用从 11.3 万降到 5.3 万。
3. **DFS 上界修正**：`remaining` 原来对**没有候选**的字段也累加
   `FILL_BONUS + field_bonus`（每个空字段白送 0.27），上界虚高导致剪枝
   永不触发——仅 10 根骨的服装骨架也会跑满 20 万节点。修正两处：
   空字段不计入上界并从搜索顺序里剔除；上界按「骨骼容量」取前
   `min(字段数, 候选骨并集大小)` 大的 gain 之和，而不是逐字段求和
   （15 个字段抢 4 根骨时原上界高估 4 倍）。

实测（单文件冷启动，`probe_search_cost.py`）：

| 骨架 | 骨数 | 改前 | 改后 |
|---|---|---|---|
| Tifa_Default_Armature | 354 | 5834 ms | 1024 ms |
| Tifa_metarig | 733 | 10996 ms | 1936 ms |
| Tifa_rig | 1792 | 16909 ms | 9110 ms |

**搜索上限不是瓶颈**，不要为它换求解器：把 `SEARCH_CAP` 放到 3000 万
（150 倍）跑沙袋骨架，filled/solid 与 200k 截断**完全一致**。
真正的耗时在候选生成。

`SearchBoundValidityTests` 用暴力枚举钉住上界：把它故意低估 1，
测试立刻报「2.71 不 ≥ 最优 4.03」。

编辑距离档**不能删**：`NO_EDIT=1` 实测 `Tifa_Default_Armature` 稳妥从
52 掉到 24，多个模型填充 -1~-2。

Blender 内嵌 Python 无视 `PYTHONHASHSEED`，任何影响排序的 set 遍历必须 `sorted()`。
改动后须同模型连跑 ≥3 次比对 STAT 完全一致。

## 脚本的路径约定

`dev/` 根下的脚本用

```python
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

上溯两级得到**仓库根**，再据此定位 `__init__.py`、`tools/`。因此：

- 放在 `dev/` 根 → `ROOT` 正确；
- 放进更深一层子目录（如 `dev/probes/`）→ `ROOT` 会算成 `dev/`，路径全断。

只有**完全不依赖 ROOT** 的脚本（仅用 `__file__` 同目录出图，如 `apose_render/` 里的渲染脚本）
才能放子目录。新增验证脚本默认放 `dev/` 根。
