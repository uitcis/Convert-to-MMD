import bpy
import os

from .operators.load_preset_operator import OBJECT_OT_load_preset


class OBJECT_PT_skeleton_hierarchy(bpy.types.Panel):
    bl_label = "Convert to MMD"
    bl_idname = "OBJECT_PT_convert_to_mmd"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Convert to MMD"

    def draw(self, context):
        layout = self.layout
        scene = context.scene


        # 检查活动对象是否为骨架
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            layout.menu("TOPBAR_MT_file_import", text="Import", icon='IMPORT')
            return

        # 添加带有标签、prop_search用于骨骼和填充按钮的行的函数
        def add_bone_row_with_button(layout, label_text, prop_name):
            row = layout.row(align=True)
            split_name = row.split(factor=0.1, align=True)
            # 左侧部分：骨骼名称
            split_name.label(text=label_text)
            # action部分占用剩余的0.8
            split_action = split_name.split(factor=1)
            sub_split = split_action.split(factor=(0.49*0.1), align=True)
            # 按钮部分
            sub_split.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = prop_name
            # 选择框部分
            sub_split.prop_search(
                scene,
                prop_name,
                obj.data,
                "bones",
                text=""
            )
        def add_symmetric_bones_with_buttons(layout, label_text, left_prop, right_prop):
            # 第一层划分：将行分为 0.2 和 0.8 两部分
            row = layout.row(align=True)
            # 骨骼名字（Name）使用0.2
            split_name = row.split(factor=0.1, align=True)
            split_name.label(text=label_text)  # 显示骨骼名字
            # split() 的比例是基于当前容器的剩余空间
            # action部分使用name剩下的0.8
            split_action = split_name.split(factor=1, align=True)

            # 左侧操作部分 使用action的0.49
            split_left_action = split_action.split(factor=0.49, align=True)  # 使用相对比例
            col_left_action = split_left_action.column(align=True)
            row_left_action = col_left_action.row(align=True)

            # 在左侧操作部分进一步划分为 Button 和 Search Box
            sub_split_left_button = row_left_action.split(factor=0.1, align=True)
            sub_split_left_button.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = left_prop  # 左侧按钮（Button）
            sub_split_left_button.prop_search(
                scene,
                left_prop,
                obj.data,
                "bones",
                text=""  # 左侧选择框（Search Box）
            )

            # 中间部分使用left_action剩下的0.51划分0.02/(0.02+0.49)给中间分割符
            split_divider = split_left_action.split(factor=(0.02/(0.02+0.49)), align=True)  # 动态计算剩余比例
            split_divider.label(text="|")  # 使用 "|" 模拟分割线

            # 右侧操作部分使用剩下的0.49
            split_right_action = split_divider.split(factor=1,align=True)
            col_right_action = split_right_action.column(align=True)
            row_right_action = col_right_action.row(align=True)

            # 在右侧操作部分进一步划分为 Button 和 Search Box
            sub_split_right_button = row_right_action.split(factor=0.1, align=True)
            sub_split_right_button.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = right_prop  # 右侧按钮（Button）
            sub_split_right_button.prop_search(
                scene,
                right_prop,
                obj.data,
                "bones",
                text=""  # 右侧选择框（Search Box）
            )
        def add_finger_bones_with_buttons(layout, label_text, first_prop, second_prop, third_prop):
            
            divider_ratio = 0.02
            split_ratio = (1-2*divider_ratio)/3
            # 第一层划分：将行分为 0.2 和 0.8 两部分
            row = layout.row(align=True)
            # 骨骼名字（Name）使用0.2
            split_name = row.split(factor=0.1, align=True)
            split_name.label(text=label_text)  # 显示骨骼名字
            # split() 的比例是基于当前容器的剩余空间
            # action部分使用name剩下的0.8
            split_action = split_name.split(factor=1, align=True)

            # 右侧操作区域划分为三列：split_ratio divider_ratio split_ratio divider_ratio split_ratio
            # 第一个操作区域（0.32）
            split_first_action = split_action.split(factor=split_ratio, align=True)
            col_first_action = split_first_action.column(align=True)
            row_first_action = col_first_action.row(align=True)
            # 在右侧操作部分进一步划分为 Button 和 Search Box
            sub_split_first_button = row_first_action.split(factor=0.1, align=True)
            sub_split_first_button.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = first_prop  # 右側按钮（Button）
            sub_split_first_button.prop_search(
                scene,
                first_prop,
                obj.data,
                "bones",
                text=""  # 右側选择框（Search Box）
            )
            # 中间分割线（{divider_ratio}）
            split_divider1 = split_first_action.split(factor=divider_ratio/(1-split_ratio), align=True)
            split_divider1.label(text="|")  # 分割线
            # 第二个操作区域（0.32）
            split_second_bone = split_divider1.split(factor=split_ratio/(1-split_ratio-divider_ratio), align=True)
            col_second_bone = split_second_bone.column(align=True)
            row_second_bone = col_second_bone.row(align=True)
            # 在右侧操作部分进一步划分为 Button 和 Search Box
            sub_split_second_button = row_second_bone.split(factor=0.1, align=True)
            sub_split_second_button.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = second_prop  # 右側按钮（Button）
            sub_split_second_button.prop_search(
                scene,
                second_prop,
                obj.data,
                "bones",
                text=""  # 右側选择框（Search Box）
            )
            # 中间分割线（{divider_ratio}）
            split_divider2 = split_second_bone.split(factor=divider_ratio/(1-split_ratio*2-divider_ratio), align=True)
            split_divider2.label(text="|")
            
            # 第三个操作区
            split_third_bone = split_divider2.split(factor=1, align=True)
            col_third_bone = split_third_bone.column(align=True)
            row_third_bone = col_third_bone.row(align=True)
            # 在右侧操作部分进一步划分为 Button 和 Search Box
            sub_split_third_button = row_third_bone.split(factor=0.1, align=True)
            sub_split_third_button.operator(
                "object.fill_from_selection_specific",
                text="",
                icon='ZOOM_SELECTED'
            ).bone_property = third_prop  # 右側按钮（Button）
            sub_split_third_button.prop_search(
                scene,
                third_prop,
                obj.data,
                "bones",
                text=""  # 右側选择框（Search Box）
            )
        # 添加选项卡按钮 - 移动到条件判断外部，使其始终可见
        row = layout.row()
        row.prop(scene, "my_enum", expand=True)
        if scene.my_enum == 'option1':

            row = layout.row(align=True)
            row.prop(scene, "preset_enum", text="")
            row.operator("object.import_preset", text="导入预设")
            row.operator("object.export_preset", text="导出预设")
            row.operator("object.clear_bone_selection", text="", icon='X')
        
            main_col = layout.column(align=True)
            # 全ての親到腰部分
            full_body_box = main_col.box()
            col = full_body_box.column()
            add_bone_row_with_button(col, "操作中心", "control_center_bone")
            add_bone_row_with_button(col, "全ての親", "all_parents_bone")
            add_bone_row_with_button(col, "センター", "center_bone")
            add_bone_row_with_button(col, "グルーブ", "groove_bone")
            add_bone_row_with_button(col, "腰", "hip_bone")

            # 上半身到頭部分
            upper_body_box = main_col.box()
            col = upper_body_box.column()
            add_bone_row_with_button(col, "上半身*", "upper_body_bone")
            # 上半身2~5由系统根据上半身和首骨骼自动检测
            add_bone_row_with_button(col, "首*", "neck_bone")
            add_bone_row_with_button(col, "頭*", "head_bone")
            add_symmetric_bones_with_buttons(col, "目", "left_eye_bone", "right_eye_bone")
            add_symmetric_bones_with_buttons(col, "肩*", "left_shoulder_bone", "right_shoulder_bone")
            add_symmetric_bones_with_buttons(col, "腕*", "left_upper_arm_bone", "right_upper_arm_bone")
            add_symmetric_bones_with_buttons(col, "ひじ*", "left_lower_arm_bone", "right_lower_arm_bone")
            add_symmetric_bones_with_buttons(col, "手首*", "left_hand_bone", "right_hand_bone")

            # 下半身到足首部分
            lower_body_box = main_col.box()
            col = lower_body_box.column()
            add_bone_row_with_button(col, "下半身", "lower_body_bone")
            add_symmetric_bones_with_buttons(col, "足*", "left_thigh_bone", "right_thigh_bone")
            add_symmetric_bones_with_buttons(col, "ひざ*", "left_calf_bone", "right_calf_bone")
            add_symmetric_bones_with_buttons(col, "足首*", "left_foot_bone", "right_foot_bone")
            add_symmetric_bones_with_buttons(col, "足先EX", "left_toe_bone", "right_toe_bone")

            fingers_box = main_col.box()
            col = fingers_box.column()
            add_finger_bones_with_buttons(col, "左親指", "left_thumb_0", "left_thumb_1", "left_thumb_2")
            add_finger_bones_with_buttons(col, "左人指", "left_index_1", "left_index_2", "left_index_3")
            add_finger_bones_with_buttons(col, "左中指", "left_middle_1", "left_middle_2", "left_middle_3")
            add_finger_bones_with_buttons(col, "左薬指", "left_ring_1", "left_ring_2", "left_ring_3")
            add_finger_bones_with_buttons(col, "左小指", "left_pinky_1", "left_pinky_2", "left_pinky_3")

            add_finger_bones_with_buttons(col, "右親指", "right_thumb_0", "right_thumb_1", "right_thumb_2")
            add_finger_bones_with_buttons(col, "右人指", "right_index_1", "right_index_2", "right_index_3")
            add_finger_bones_with_buttons(col, "右中指", "right_middle_1", "right_middle_2", "right_middle_3")
            add_finger_bones_with_buttons(col, "右薬指", "right_ring_1", "right_ring_2", "right_ring_3")
            add_finger_bones_with_buttons(col, "右小指", "right_pinky_1", "right_pinky_2", "right_pinky_3")

            row = layout.row()
            # 添加T-Pose到A-Pose转换按钮
            row.operator("object.convert_to_apose", text="转换为A-Pose")
            # 添加第 0 步归正骨骼按钮
            row.operator("object.correct_bones", text="归正骨架位置")
            
            # 添加重命名按钮和补全缺失骨骼按钮到同一行
            row = layout.row()
            row.operator("object.rename_to_mmd", text="1.重命名为MMD")
            row.operator("object.complete_missing_bones", text="2.补全缺失骨骼")

            # 添加IK按钮和创建骨骼集合按钮到同一行
            row = layout.row()
            row.operator("object.add_mmd_ik", text="3.添加MMD IK")
            row.operator("object.create_bone_group", text="4.创建骨骼集合")

            # 添加“使用mmdtools转换格式”按钮到最下方
            layout.operator("object.use_mmd_tools_convert", text="5.使用mmdtools转换格式")
        # 其他工具选项卡
        elif scene.my_enum == 'option2':
            # 上部分：次标准骨骼
            secondary_bones_box = layout.box()
            secondary_bones_box.label(text="次标准骨骼", icon='BONE_DATA')
            
            # 添加合并足部骨骼链按钮
            row = secondary_bones_box.row()
            row.operator("object.merge_leg_bones", text="1.合并足部骨骼链", icon='MOD_VERTEX_WEIGHT')
            # 添加腿部D骨骼按钮
            row = secondary_bones_box.row()
            row.operator("object.add_leg_d_bones", text="2.添加腿部D骨骼", icon='BONE_DATA')
            # 添加合并手臂骨骼链按钮
            row = secondary_bones_box.row()
            row.operator("object.merge_arm_bones", text="1.合并手臂骨骼链", icon='MOD_VERTEX_WEIGHT')
            #添加捩骨骼按钮
            row = secondary_bones_box.row()
            row.operator("object.add_twist_bone", text="2.添加捩骨骼", icon='BONE_DATA')
            #添加肩P骨骼按钮
            row = secondary_bones_box.row()
            row.operator("object.add_shoulder_p_bones", text="3.添加肩P骨骼", icon='BONE_DATA')
            
            # 下部分：通用工具
            general_tools_box = layout.box()
            general_tools_box.label(text="通用工具", icon='TOOL_SETTINGS')

            row = general_tools_box.row()
            row.operator("object.clear_all_bone_constraints", text="清除所有骨骼约束", icon='CONSTRAINT')
            row.operator("object.clear_all_bone_drivers", text="清除所有骨骼驱动器", icon='DRIVER')
            row = general_tools_box.row()
            row.operator("object.clear_unweighted_bones", text="清理无权重骨骼", icon='X')
            row = general_tools_box.row()
            row.operator("object.auto_connect_parent_bones", text="自动连接父级骨骼", icon='BONE_DATA')
            row.operator("object.unlock_all_bones", text="解锁所有骨骼", icon='UNLOCKED')
            row = general_tools_box.row()
            row.operator("object.align_forearm_straight", text="伸直小臂", icon='ARROW_LEFTRIGHT')
            row = general_tools_box.row()
            row.operator("object.align_forearm_from_selection", text="对齐选中骨骼的小臂", icon='BONE_DATA')
            row = general_tools_box.row()
            row.operator("object.convert_bones_rotation_to_quaternion", text="转换为四元数旋转", icon='ORIENTATION_GLOBAL')
            row.operator("object.split_bones_to_individual_objects", text="拆分骨骼为独立物体", icon='UNLINKED')
            row = general_tools_box.row(align=True)
            row.operator("object.merge_selected_bones_weights", text="合并所选骨骼权重", icon='MOD_VERTEX_WEIGHT')
            row.prop(scene, "merge_bones_also", text="合并骨骼")


            row = general_tools_box.row()
            row.operator("object.export_selected_bones_info", text="导出所选骨骼信息", icon='EXPORT')
            row.operator("object.export_selected_bones_constraints", text="导出所选骨骼约束关系", icon='EXPORT')


            chest_physics_box = layout.box()
            chest_physics_box.label(text="胸物理", icon='PHYSICS')

            col = chest_physics_box.column(align=True)
            
            # 胸親父级骨骼选择
            add_bone_row_with_button(col, "胸親父级", "breast_parent_bone")
            
            # 胸上 2 骨骼选择（左右对称）
            add_symmetric_bones_with_buttons(col, "权重骨（胸上 2）", "left_chest_bone", "right_chest_bone")

            chest_physics_box.separator(factor=0.5)

            hint = chest_physics_box.column(align=True)
            hint.scale_y = 0.75
            hint.label(text="选中已有权重骨骼，自动构建胸物理：", icon='INFO')
            hint.label(text="→ 重命名为 左胸上2 / 右胸上2")
            hint.label(text="→ 创建 左/右胸上 / 左/右胸親 / 左/右胸下 父级骨骼链")
            hint.label(text="→ 创建 8 个刚体 + 9 个弹簧约束")

            chest_physics_box.separator(factor=0.5)
            row = chest_physics_box.row()
            row.scale_y = 1.4
            row.operator("object.auto_physics_builder", text="自动构建胸部物理", icon='PLAY')

            # 身体刚体构建
            body_rigid_box = layout.box()
            body_rigid_box.label(text="身体刚体", icon='PHYSICS')

            body_rigid_box.separator(factor=0.3)

            hint = body_rigid_box.column(align=True)
            hint.scale_y = 0.75
            hint.label(text="尝试通过计算网格自动设置身体刚体", icon='INFO')

            body_rigid_box.separator(factor=0.3)

            row = body_rigid_box.row()
            row.scale_y = 1.2
            row.operator("object.build_simple_body_rigid", text="构建简易身体刚体", icon='ADD')