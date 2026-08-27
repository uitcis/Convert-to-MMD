# Convert-to-MMD 插件代码审查标准与流程

## 一、项目背景

**项目名称**：Convert-to-MMD（Blender插件）  
**技术栈**：Python 3.13+, Blender 4.0-4.3+ API, mathutils  
**代码规模**：约5940行Python代码，66个文件  
**核心功能**：将Blender骨架转换为MMD（MikuMikuDance）标准格式，包含骨骼重命名、IK约束生成、骨骼roll计算、刚体碰撞等

**审查目标**：
- 保证Blender API调用的正确性与版本兼容性
- 防止模式切换错误（EDIT_ARMATURE → EDIT）
- 确保几何计算的准确性（坐标系转换、roll值）
- 提升代码可维护性与团队协作效率
- 减少运行时崩溃与数据损坏风险

---

## 二、审查流程

### 2.1 提交前检查（开发者自查）

**必须完成以下步骤**：

1. **语法校验**
   ```bash
   python -m py_compile <修改的文件.py>
   ```

2. **Blender版本兼容性检查**
   - 新增API需在Blender 4.0-4.3+中测试
   - 禁用实验性API（标记为`@experimental`的）

3. **本地功能测试**
   - 在标准MMD骨架上测试修改的功能
   - 覆盖正常路径与边缘情况（空骨骼、已删除骨骼等）

4. **更新文档**
   - 若修改了公共API，更新函数docstring
   - 若修改了关键规则（如roll计算），更新 `MEMORY.md`

5. **提交信息规范**
   - 格式：`类型: 简短描述`（类型：fix/feat/refactor/docs/test/chore）
   - 示例：`fix: 修复IK约束不生效的问题`

### 2.2 审查阶段（审查者执行）

**审查优先级**（按重要性排序）：

🔴 **Blocker（阻塞项）** - 必须修复后才能合并
🟡 **Suggestion（建议项）** - 建议修复，提升质量
💭 **Nit（次要项）** - 可选优化，不影响功能

**审查内容**：

| 类别 | 审查点 | 优先级 | 说明 |
|------|--------|--------|------|
| **正确性** | Blender API调用是否正确 | 🔴 | 例如：`context.mode` vs `mode_set` 枚举不兼容 |
| **正确性** | 模式切换顺序 | 🔴 | "EDIT建骨 → OBJECT同步 → 加约束" 顺序 |
| **正确性** | pose.bones 访问前是否已同步 | 🔴 | 编辑模式创建骨骼后必须切到OBJECT模式 |
| **正确性** | 空值检查与异常处理 | 🔴 | 避免 `KeyError` / `NameError`，使用 `.get()` |
| **安全性** | 用户输入验证 | 🟡 | 防止恶意命名导致SQL注入（本插件无DB，但需防路径注入） |
| **性能** | O(N) 循环内是否有O(N)操作 | 🟡 | 避免在 `for bone in edit_bones:` 内调用 `context.scene.objects` |
| **可维护性** | 函数职责单一 | 🟡 | 单函数不超过50行（例外：复杂几何算法可放宽至100行） |
| **可维护性** | 命名清晰 | 💭 | 避免单字母变量（`i/j/k`除外于循环索引） |
| **可维护性** | 注释与文档字符串 | 💭 | 公共函数必须有docstring（Args/Returns/说明） |
| **测试** | 边缘情况覆盖 | 🟡 | 已知边缘：零长度骨骼、已删除骨骼、非MMD骨架 |

### 2.3 批准条件

**合并前的检查清单**：

- [ ] 所有 🔴 Blocker 项已修复
- [ ] 关键 🟡 Suggestion 项已讨论并决定（或明确推迟）
- [ ] 语法校验通过（无 `SyntaxError`）
- [ ] Blender 4.0-4.3+ 测试通过（无运行时崩溃）
- [ ] 本地功能测试通过（标准MMD骨架上验证）
- [ ] 代码符合项目规范（见第三章）

---

## 三、代码质量标准

### 3.1 Blender API 专项规范

**规则1：模式枚举转换**

❌ **错误示例**：
```python
# TypeError: enum "EDIT_ARMATURE" not found
bpy.ops.object.mode_set(mode=context.mode)  # context.mode = 'EDIT_ARMATURE'
```

✅ **正确示例**：
```python
# 使用项目内置转换函数
restore_mode = bone_utils.context_mode_to_mode_set(context.mode)
bpy.ops.object.mode_set(mode=restore_mode)
```

**规则2：编辑模式 → 姿态数据同步**

❌ **错误示例**：
```python
# KeyError: '右肩C' not found
bpy.ops.object.mode_set(mode='EDIT')
edit_bones.new('右肩C')
# 错误：直接访问 pose.bones，但 EDIT 模式下 pose.bones 未更新
pose_bone = obj.pose.bones['右肩C']
```

✅ **正确示例**：
```python
bpy.ops.object.mode_set(mode='EDIT')
edit_bones.new('右肩C')
# 正确：先切到OBJECT模式同步姿态数据
bpy.ops.object.mode_set(mode='OBJECT')
pose_bone = obj.pose.bones.get('右肩C')  # 使用 .get() + 空值检查
if not pose_bone:
    self.report({'ERROR'}, "同步姿态数据失败：右肩C 未找到")
    return {'CANCELLED'}
```

**规则3：约束添加时机**

❌ **错误示例**：
```python
# 编辑模式添加约束 → 不生效
bpy.ops.object.mode_set(mode='EDIT')
edit_bones.new('左足ＩＫ')
ik_constraint = obj.pose.bones['左足'].constraints.new('IK')  # pose.bones 仍是旧数据
```

✅ **正确示例**：
```python
# 正确顺序：EDIT建骨 → OBJECT同步 → 加约束
bpy.ops.object.mode_set(mode='EDIT')
edit_bones.new('左足ＩＫ')
bpy.ops.object.mode_set(mode='OBJECT')
ik_constraint = obj.pose.bones['左足'].constraints.new('IK')  # 此时 pose.bones 已更新
ik_constraint.target = obj
ik_constraint.subtarget = '左足ＩＫ'
```

### 3.2 Python 通用规范

**规则1：空值检查**

❌ **错误示例**：
```python
bone = edit_bones.get('左腕')
bone.roll = 0.0  # 若 bone=None，抛出 AttributeError
```

✅ **正确示例**：
```python
bone = edit_bones.get('左腕')
if bone:
    bone.roll = 0.0
else:
    self.report({'WARNING'}, "骨骼「左腕」不存在，已跳过")
```

**规则2：循环内避免重复计算**

❌ **错误示例**：
```python
for bone in edit_bones:
    # 每次循环都计算 inv_rot，性能差
    inv_rot = obj.matrix_world.to_3x3().inverted()
    local_z = inv_rot @ Vector((0,0,1))
    bone.align_roll(local_z)
```

✅ **正确示例**：
```python
# 循环外计算一次
inv_rot = obj.matrix_world.to_3x3().inverted()
local_z = inv_rot @ Vector((0,0,1))
for bone in edit_bones:
    bone.align_roll(local_z)
```

**规则3：文档字符串规范**

✅ **正确示例**：
```python
def calculate_auto_bone_roll(edit_bones, armature_obj=None):
    """按骨骼名分类并分别计算扭转（roll），复刻 Blender「Shift+N 重算扭转」的全局轴语义。

    规则（不同类别算法不同）：
    - 局部轴骨骼（LOCAL：手臂主骨/手指/扭转骨）：
        左臂(名以「左」开头) → 全局 +Z（Shift+N → Global +Z）
        右臂(名以「右」开头) → 全局 -Z（Shift+N → Global -Z）
      即把局部 Z 轴对齐到世界 ±Z（按骨架世界矩阵转到骨架局部空间，处理骨架自身旋转）。
    - 其余所有骨骼（躯干/头/腿/重心/IK/末端虚骨等）→ 全局 ±Y：
        head 世界Z > tail 世界Z（头高于尾）→ 全局 +Y
        否则 → 全局 -Y

    Args:
        edit_bones (EditBones): 编辑模式的骨骼集合
        armature_obj (Object, optional): 骨架对象，用于世界→局部坐标转换

    Returns:
        tuple[int, int, int]: (总调整数, 局部轴骨骼数, 其余骨骼数)

    Raises:
        ReferenceError: 骨骼已被移除（内部捕获，不抛出）
    """
    # 实现...
```

### 3.3 项目特定规范

**规则1：骨骼操作符必须恢复模式**

```python
original_mode = context.mode
try:
    # 执行操作...
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    # 处理逻辑...
finally:
    # 恢复原始模式
    if context.mode != original_mode:
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)
        bpy.ops.object.mode_set(mode=restore_mode)
```

**规则2：删除前先清除旧数据**

```python
# 添加前先清除旧约束（避免叠加）
for c in bone.constraints:
    if c.name in ('IK', 'mmd_ik_limit_override', 'mmd_ik_target_override'):
        bone.constraints.remove(c)
# 再添加新约束
new_constraint = bone.constraints.new('IK')
```

**规则3：零长度骨骼跳过**

```python
direction = (bone.tail - bone.head).normalized()
if direction.length < 1e-6:
    continue  # 零长度骨骼，无法定义方向，跳过
```

---

## 四、常见问题清单（基于历史修复记录）

### 4.1 🔴 Blocker 级别问题

| 问题 | 触发场景 | 典型报错 | 修复方案 |
|------|----------|----------|----------|
| 模式枚举不兼容 | 恢复模式时直接传 `context.mode` 给 `mode_set` | `TypeError: enum "EDIT_ARMATURE" not found` | 使用 `bone_utils.context_mode_to_mode_set()` 转换 |
| pose.bones 未同步 | 编辑模式创建骨骼后立即访问 `pose.bones` | `KeyError: '右肩C' not found` | 先 `mode_set(mode='OBJECT')` 同步姿态数据 |
| IK约束不生效 | 编辑模式添加约束 | 约束创建但不工作 | 先退出编辑模式再添加约束 |
| 空值异常 | 直接访问字典/列表不检查键存在 | `KeyError` / `NameError` / `AttributeError` | 使用 `.get()` + 空值检查 |

### 4.2 🟡 Suggestion 级别问题

| 问题 | 触发场景 | 典型表现 | 修复方案 |
|------|----------|----------|----------|
| 循环内重复计算 | 在 `for bone in edit_bones:` 内计算矩阵逆 | 性能下降（尤其骨骼多时） | 循环外计算一次 |
| 函数过长 | 单函数超过50行 | 难以理解、难以测试 | 拆分为多个小函数 |
| 缺少文档字符串 | 公共函数无docstring | 他人难以理解接口意图 | 添加标准格式docstring（Args/Returns/说明） |
| 硬编码字符串 | 骨骼名称、约束名称直接写死 | 难以维护、易出错 | 提取为常量（模块级 `_CONSTANTS`） |

### 4.3 💭 Nit 级别问题

| 问题 | 触发场景 | 典型表现 | 修复方案 |
|------|----------|----------|----------|
| 命名不清晰 | 单字母变量（非循环索引） | `x, y, z` 混淆含义 | 改为语义化名称（如 `inv_rot`, `local_z`） |
| 注释冗余 | 注释重复代码内容 | 增加维护负担 | 删除冗余注释，保留设计意图说明 |
| 未使用的导入 | `import` 后未使用 | 污染命名空间 | 删除或用 `# noqa` 标注 |

---

## 五、审查工具与自动化检查

### 5.1 必需工具

**1. 语法检查**
```bash
python -m py_compile <file.py>
```
**时机**：提交前、合并前  
**结果**：无输出 = 通过；有 `SyntaxError` = 阻塞

**2. 静态类型检查（可选）**
```bash
mypy <file.py> --ignore-missing-imports
```
**用途**：捕获类型错误（如 `Vector` 未导入）
**优先级**：🟡 建议

**3. 代码格式化（可选）**
```bash
black <file.py> --line-length=100
```
**用途**：统一缩进、空格、行宽（Blender插件常用100字符）
**优先级**：💭 可选

### 5.2 项目特有检查脚本

**检查1：模式枚举使用**
```bash
grep -rn "mode_set(mode=context.mode)" E:/Onedrive/Code/addons/Convert-to-MMD
```
**预期结果**：无匹配（应使用 `context_mode_to_mode_set`）

**检查2：pose.bones 访问前模式**
```bash
grep -A5 "mode_set(mode='EDIT')" E:/Onedrive/Code/addons/Convert-to-MMD/*.py | grep -B3 "pose.bones\["
```
**预期结果**：无匹配（应先切到OBJECT模式）

**检查3：硬编码骨骼名**
```bash
grep -rn "'右肩' '左腕'" E:/Onedrive/Code/addons/Convert-to-MMD --include="*.py"
```
**预期结果**：仅在常量定义中出现，不应分散在函数内

---

## 六、审查模板与检查清单

### 6.1 PR/Review 模板

**审查者填写的评论模板**：

```
## 整体评价
[ ] 通过 | [ ] 需修改 | [ ] 阻塞

## 🔴 Blocker 问题（必须修复）
- [ ] 问题1：位置/原因/建议

## 🟡 Suggestion 问题（建议修复）
- [ ] 问题1：位置/原因/建议

## 💭 Nit 问题（可选优化）
- [ ] 问题1：位置/原因/建议

## 💡 好的做法（值得表扬）
- 良好实践1：位置/原因

## 其他备注
- 需要跟进的点
```

### 6.2 提交前自查清单

**开发者勾选**：

- [ ] 语法校验通过：`python -m py_compile` 无错误
- [ ] Blender 4.0-4.3+ 测试通过（本地运行无崩溃）
- [ ] 修改涉及Blender API，已在标准MMD骨架上测试
- [ ] 修改了公共API，已更新docstring
- [ ] 修改了关键规则（如roll计算），已更新 `MEMORY.md`
- [ ] 代码符合项目规范（见第三章）
- [ ] 无硬编码字符串（骨骼名/约束名已提取为常量）
- [ ] 空值检查完整（`.get()` + 空值处理）
- [ ] 模式切换正确（使用 `context_mode_to_mode_set`）
- [ ] 提交信息格式正确：`类型: 简短描述`

### 6.3 合并前检查清单

**审查者/维护者勾选**：

- [ ] 所有 🔴 Blocker 项已修复
- [ ] 关键 🟡 Suggestion 项已讨论并决定
- [ ] 语法校验通过
- [ ] Blender 4.0-4.3+ 测试通过
- [ ] 本地功能测试通过（标准MMD骨架上验证）
- [ ] 代码符合项目规范
- [ ] 提交信息格式正确
- [ ] 文档已更新（若有公共API变更）

---

## 七、常见场景审查要点

### 7.1 新增操作符（Operator）

**必须检查**：
- [ ] 继承自 `bpy.types.Operator`
- [ ] 定义了 `bl_idname`（唯一标识符）
- [ ] 定义了 `bl_label`（UI显示名）
- [ ] 实现了 `execute()` 方法（返回 `{'FINISHED'}` / `{'CANCELLED'}`）
- [ ] 使用 `REGISTER` / `UNDO` 选项
- [ ] 模式切换正确（若涉及编辑模式）
- [ ] 错误处理完整（用 `try/except` 捕获，返回 `CANCELLED` 并报错）
- [ ] 清理逻辑（删除临时对象、恢复模式）

**示例**：
```python
class OBJECT_OT_calculate_bone_rolls(bpy.types.Operator):
    """按骨骼名分类（局部轴/全局轴），分别计算扭转（roll）"""
    bl_idname = "object.calculate_bone_rolls"
    bl_label = "设置骨骼扭转"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "未选中骨架对象")
            return {'CANCELLED'}

        original_mode = context.mode
        try:
            # 处理逻辑...
            self.report({'INFO'}, "已完成")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"处理失败：{e}")
            return {'CANCELLED'}
        finally:
            if context.mode != original_mode:
                restore_mode = bone_utils.context_mode_to_mode_set(original_mode)
                bpy.ops.object.mode_set(mode=restore_mode)
```

### 7.2 修改几何计算函数

**必须检查**：
- [ ] 坐标系转换正确（世界坐标 ↔ 局部坐标）
- [ ] 矩阵运算正确（`matrix_world` / `to_3x3()` / `inverted()`）
- [ ] 零向量处理（`length < 1e-6` 跳过）
- [ ] 并行向量处理（叉乘结果为零向量时回退方案）
- [ ] 数值精度合理（使用 `1e-6` 而非 `0.0`）
- [ ] 文档字符串清晰（说明算法原理、参数含义）

### 7.3 修改骨骼命名/映射逻辑

**必须检查**：
- [ ] 日文标准名与英文别名的映射完整
- [ ] 未破坏已有命名规则（如 `.L` / `.R` 后缀）
- [ ] 考虑了非标准MMD骨架（用户自定义骨骼）
- [ ] 删除旧命名前已检查引用（无残留调用）
- [ ] 提供降级方案（重命名失败时回滚）

---

## 八、持续改进机制

### 8.1 审查记录追踪

**使用项目记忆**（`.workbuddy/memory/`）记录：
- 每次审查发现的关键问题（存入 `YYYY-MM-DD.md`）
- 常见模式与反模式（存入 `MEMORY.md`）
- 新增的最佳实践（及时更新文档）

### 8.2 定期回顾

**每月进行一次代码质量回顾**：
- 统计本月Blocker/Suggestion/Nit数量
- 分析高频问题（如模式切换错误反复出现）
- 更新检查清单（补充新发现的陷阱）
- 评审审查标准（是否需要调整优先级）

### 8.3 工具改进

**自动化检查脚本**（待开发）：
```bash
# 预检查脚本
python .workbuddy/scripts/pre_commit_check.py <file.py>
```
**功能**：
- 语法校验
- 模式枚举检查
- 硬编码字符串检查
- 空值检查（静态分析）
- 生成检查报告

---

## 九、快速参考卡片

### 9.1 Blocker 快速检查（5分钟）

```python
# 1. 检查模式枚举转换
if "mode_set(mode=context.mode)" in code:
    ❌ 阻塞：必须用 context_mode_to_mode_set()

# 2. 检查 pose.bones 访问前模式
if "mode_set(mode='EDIT')" in code and "pose.bones[" in code:
    ❌ 阻塞：EDIT → pose.bones 未同步，必须先切到OBJECT

# 3. 检查空值处理
if ".roll = " in code and ".get(" not in code:
    ❌ 阻塞：可能抛出 AttributeError，需用 .get() + 空值检查

# 4. 检查约束添加时机
if "mode_set(mode='EDIT')" in code and "constraints.new" in code:
    ❌ 阻塞：编辑模式添加约束不生效，需先退出编辑模式
```

### 9.2 常用代码片段

**模式恢复**：
```python
original_mode = context.mode
try:
    # 处理逻辑...
finally:
    if context.mode != original_mode:
        restore_mode = bone_utils.context_mode_to_mode_set(original_mode)
        bpy.ops.object.mode_set(mode=restore_mode)
```

**空值检查**：
```python
bone = edit_bones.get('骨骼名')
if not bone:
    self.report({'WARNING'}, "骨骼「骨骼名」不存在，已跳过")
    return {'CANCELLED'}
```

**零长度跳过**：
```python
direction = (bone.tail - bone.head).normalized()
if direction.length < 1e-6:
    continue
```

---

## 十、附录

### 10.1 参考资料

- [Blender Python API 官方文档](https://docs.blender.org/api/5.1/)
- [MMD 模型标准规范](https://gist.github.com/hokein/243a61f26a47c78a5436)
- [Python PEP 8 代码风格指南](https://peps.python.org/pep-0008/)
- [项目历史修复记录](.workbuddy/memory/2026-08-26.md)

### 10.2 联系方式

- **代码审查请求**：提交PR并标记标签 `request-review`
- **紧急问题**：直接联系维护者（查看 `README.md`）
- **标准讨论**：项目Issue区

---

**文档版本**：v1.0  
**最后更新**：2026-08-27  
**维护者**：Convert-to-MMD 团队