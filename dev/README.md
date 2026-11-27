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
├── check_baseline.py          三模型基线：filled/solid/low/链断裂 + 关键字段
├── check_core.py              核心骨取值核对
├── check_chain.py             14 类错配探针（父子关系反了应被否决）
├── verify_mapping.py          映射结果人工可读导出
├── generality_probe.py        泛化探针：4 套未参与调参的命名体系
├── apose_operator_smoke.py    A-Pose 最小场景跨版本兼容（4.0/4.2 无工程文件）
├── apose_operator_verify.py   A-Pose 真实工程端到端
├── apose_render/              A-Pose 渲染对照脚本与截图（脚本用 __file__ 同目录出图）
├── docs/                      审查报告与算法笔记
└── reference/                 本地参考资料（.gitignore 忽略，不进仓库）
```

## 常用命令

以下命令都在**仓库根目录**执行。

```bash
# 单测（93 + 15 项，纯 Python，无需 Blender）
python -m unittest discover -s dev -p "test_*.py"

# 泛化探针（四套命名体系，核心骨应 15/15）
python dev/generality_probe.py

# 三模型基线 / 核心骨 / 错配探针（需要 Blender）
BLENDER="/e/Programs/blender-5.1.0-windows-x64/blender.exe"
"$BLENDER" --background --factory-startup --python dev/check_baseline.py -- model.blend
"$BLENDER" --background --factory-startup --python dev/check_core.py     -- model.blend
"$BLENDER" --background --factory-startup --python dev/check_chain.py    -- model.blend
```

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

## 当前基线（确定性，可复现）

| 模型 | 填充 | 稳妥 | 链断裂 | 核心骨 |
|---|---|---|---|---|
| test.blend | 53/64 | 52 | 0 | 全对 |
| Gley | 58/64 | 55 | 0 | 全对 |
| DNF | 58/64 | 46 | 0 | 全对 |

Blender 内嵌 Python 无视 `PYTHONHASHSEED`，任何影响排序的 set 遍历必须 `sorted()`。
改动后须同模型连跑 ≥3 次比对 STAT 完全一致。
