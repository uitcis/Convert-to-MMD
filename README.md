# Convert to MMD Addon for Blender

## 描述
该插件用于将Blender中的其他骨骼结构转换为符合MMD（MikuMikuDance）格式的骨骼名称和结构。插件提供了多种功能，包括骨骼重命名、缺失骨骼补全、预设导出与导入以及IK链的添加。

## 主要功能
1. **骨骼重命名**：将选中的骨骼重命名为MMD格式的名称。
2. **缺失骨骼补全**：自动创建并定位MMD格式中缺失的骨骼。
3. **预设导出与导入**：导出当前骨骼配置为预设文件，或从预设文件导入骨骼配置。
4. **IK链添加**：为角色添加MMD格式的IK链，便于动画制作。

## 使用方法
1. **安装插件**：
   - 将插件文件夹复制到Blender的addons目录中。
   - 在Blender中，进入`Edit > Preferences > Add-ons`，搜索`Convert to MMD`并启用。

2. **选择对应骨骼**：
   - 选择一个骨架对象。
   - 在右侧的`Convert to MMD`面板中，选择需要操作的骨骼。

3. **重命名骨骼**：
   - 在`Convert to MMD`面板中，选择需要重命名的骨骼，并点击`Rename to MMD`按钮。

4. **缺失骨骼补全**：
   - 点击`Convert to MMD`面板中的`Complete Missing Bones`按钮，插件会自动创建并定位缺失的骨骼。

5. **IK链设置**：
   - 点击`Convert to MMD`面板中的`Add MMD IK`按钮，插件会为角色添加MMD格式的IK链。

6. **导入导出预设**：
   - 导出预设：点击`Export Preset`按钮，选择保存路径。
   - 导入预设：点击`Import Preset`按钮，选择预设文件。

## 注意事项
- 确保在使用插件前备份您的项目。
- 如果遇到问题，请参考插件文档或联系开发者。