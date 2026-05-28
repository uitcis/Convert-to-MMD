# Convert to MMD Addon for Blender

一个用于将外部骨骼格式自动转换为MMD（MikuMikuDance）格式的Blender插件。

## 更新渠道

- **Gitee**（更新较快，可能包含新功能）：[Convert to MMD](https://gitee.com/UITCIS/Convert-to-MMD)
- **B站**（稳定版本，打包好的压缩包）：[空想幻灵](https://space.bilibili.com/43768997)

## 功能特性

### 主骨骼管理（主面板）

1. **预设系统**
   - 支持20+种预设配置：Mixamo、VRoid、VRM、Bip_001、3ds Max、DAZ Poser、iClone等
   - 支持导入/导出自定义预设
   - 自动检测上半身骨骼链

2. **骨骼映射**
   - 可视化骨骼选择界面
   - 自动填充手指骨骼链
   - 自动检测对称骨骼

3. **一键转换流程**
   - **转换为A-Pose**：将T-Pose骨架转换为A-Pose
   - **归正骨架位置**：设置原点并清除动画
   - **1.重命名为MMD**：将骨骼重命名为标准MMD格式
   - **2.补全缺失骨骼**：自动创建缺失的MMD标准骨骼
   - **3.添加MMD IK**：为腿部添加IK约束
   - **4.创建骨骼集合**：按MMD标准分组骨骼
   - **5.使用mmdtools转换格式**：调用mmdtools完成最终转换

### 次标准骨骼管理（工具面板）

1. **骨骼优化工具**
   - 合并足部骨骼链
   - 添加腿部D骨骼
   - 合并手臂骨骼链
   - 添加捩骨骼（Twist Bone）
   - 添加肩P骨骼

2. **通用工具**
   - 清除所有骨骼约束
   - 清除所有骨骼驱动器
   - 清理无权重骨骼
   - 自动连接父级骨骼
   - 解锁所有骨骼
   - 合并所选骨骼权重
   - 导出骨骼信息/约束关系

3. **物理系统**
   - 自动构建胸部物理（8个刚体 + 9个弹簧约束）
   - 构建简易身体刚体

## 支持的预设格式

| 预设名称 | 说明 |
|---------|------|
| MixamoCTMMD | Mixamo自动绑定骨骼 |
| VRoidStudioCTMMD | VRoid Studio导出模型 |
| VRMformatCTMMD | VRM格式模型 |
| Bip_001 | 3ds Max Biped骨骼 |
| 3ds_max | 3ds Max标准骨骼 |
| biped_3ds_max | 3ds Max Biped |
| biped_sfm | Source Filmmaker骨骼 |
| daz_poser | DAZ/Poser骨骼 |
| iClone7 | iClone 7骨骼 |
| makehuman_mhx | MakeHuman MHX骨骼 |
| manuel_bastioni_lab | Manuel Bastioni Lab |
| mblab | MB-Lab骨骼 |
| motion_builder | MotionBuilder骨骼 |
| valvebiped | Valve Biped (Source引擎) |
| mmd_japanese | MMD日语标准骨骼 |
| mmd_english | MMD英语骨骼 |
| project_mirai | Project Mirai风格 |
| sims_2 | 模拟人生2骨骼 |
| sims_3 | 模拟人生3骨骼 |
| type_x | Type-X骨骼 |
| xna_lara | XNA Lara骨骼 |
| bepu | BEPU物理引擎骨骼 |
| base_rigify | Blender Rigify基础骨骼 |

## 安装方法

1. 下载插件压缩包
2. 打开Blender，进入 `编辑 > 偏好设置 > 插件 > 安装`
3. 选择下载的压缩包进行安装
4. 启用插件：在插件列表中找到 "Convert to MMD" 并勾选启用

## 使用方法

### 基础转换流程

1. **导入模型**：将外部模型导入Blender（支持FBX、OBJ等格式）
2. **选择预设**：在侧边栏"Convert to MMD"面板中选择对应的预设
3. **骨骼映射**（可选）：检查并调整骨骼映射关系
4. **执行转换**：
   - 点击「转换为A-Pose」（如果模型是T-Pose）
   - 点击「归正骨架位置」
   - 依次点击「1.重命名为MMD」→「2.补全缺失骨骼」→「3.添加MMD IK」→「4.创建骨骼集合」
   - 点击「5.使用mmdtools转换格式」完成最终转换

### 骨骼映射技巧

- 使用放大镜按钮快速从选择的骨骼填充
- 手指骨骼选择第一节后会自动填充后续骨骼
- 对称骨骼会自动检测并填充另一侧

### 高级功能

#### 胸部物理构建

1. 在「次标准骨骼管理」面板中找到「胸物理」区域
2. 设置「胸親父级」骨骼和左右「权重骨（胸上2）」
3. 点击「自动构建胸部物理」按钮

#### 自定义预设

1. 在主面板中配置好骨骼映射
2. 点击「导出预设」按钮保存为JSON文件
3. 可在其他项目中通过「导入预设」加载

## 注意事项

1. 使用「5.使用mmdtools转换格式」前需要先安装 [mmd_tools](https://extensions.blender.org/add-ons/mmd-tools/) 插件
2. 转换前建议备份项目文件
3. 插件会自动创建备份骨架（名称带_backup后缀）
4. 建议在转换前清除模型的动画数据
5. 对于非标准骨骼，可能需要手动调整骨骼映射

## 版本要求

- Blender 3.0.0 或更高版本
- mmd_tools 插件（用于最终格式转换）

## 开发者信息

- **作者**：UITCIS (空想幻灵)

