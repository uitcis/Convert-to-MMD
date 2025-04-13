import bpy

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
            split_name = row.split(factor=0.2, align=True)
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
            split_name = row.split(factor=0.2, align=True)
            split_name.label(text=label_text)  # 显示骨骼名字
            # split() 的比例是基于当前容器的剩余空间
            # advtion部分使用name剩下的0.8
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
        main_col = layout.column(align=True)
        # 全ての親到腰部分
        full_body_box = main_col.box()
        col = full_body_box.column()
        add_bone_row_with_button(col, "操作中心:", "control_center_bone")
        add_bone_row_with_button(col, "全ての親", "all_parents_bone")
        add_bone_row_with_button(col, "センター", "center_bone")
        add_bone_row_with_button(col, "グルーブ", "groove_bone")
        add_bone_row_with_button(col, "腰", "hip_bone")

        # 上半身到頭部分
        upper_body_box = main_col.box()
        col = upper_body_box.column()
        add_bone_row_with_button(col, "上半身", "upper_body_bone")
        add_bone_row_with_button(col, "上半身2", "upper_body2_bone")
        add_bone_row_with_button(col, "首", "neck_bone")
        add_bone_row_with_button(col, "頭", "head_bone")
        add_symmetric_bones_with_buttons(col, "目:", "left_eye_bone", "right_eye_bone")
        add_symmetric_bones_with_buttons(col, "肩:", "left_shoulder_bone", "right_shoulder_bone")
        add_symmetric_bones_with_buttons(col, "腕:", "left_upper_arm_bone", "right_upper_arm_bone")
        add_symmetric_bones_with_buttons(col, "ひじ:", "left_lower_arm_bone", "right_lower_arm_bone")
        add_symmetric_bones_with_buttons(col, "手首:", "left_hand_bone", "right_hand_bone")

        # 下半身到足首部分
        lower_body_box = main_col.box()
        col = lower_body_box.column()
        add_bone_row_with_button(col, "下半身", "lower_body_bone")
        add_symmetric_bones_with_buttons(col, "足:", "left_thigh_bone", "right_thigh_bone")
        add_symmetric_bones_with_buttons(col, "ひざ:", "left_calf_bone", "right_calf_bone")
        add_symmetric_bones_with_buttons(col, "足首:", "left_foot_bone", "right_foot_bone")
        add_symmetric_bones_with_buttons(col, "足先EX:", "left_toe_bone", "right_toe_bone")
        # 手指部分
        finger_labels = [
            ("left_thumb", ["0", "1", "2"], "左親指"),
            ("left_index", ["1", "2", "3"], "左人指"),
            ("left_middle", ["1", "2", "3"], "左中指"),
            ("left_ring", ["1", "2", "3"], "左薬指"),
            ("left_pinky", ["1", "2", "3"], "左小指"),
            ("right_thumb", ["0", "1", "2"], "右親指"),
            ("right_index", ["1", "2", "3"], "右人指"),
            ("right_middle", ["1", "2", "3"], "右中指"),
            ("right_ring", ["1", "2", "3"], "右薬指"),
            ("right_pinky", ["1", "2", "3"], "右小指")
        ]
            
        
        fingers_box = main_col.box()
        col = fingers_box.column()
        
        for LR_base_finger_name, segments, label_text in finger_labels:
            side = "left" if "left" in LR_base_finger_name else "right"
            
            row = col.row(align=True)
            row.label(text=f"{label_text}:")

            for segment in segments:
                prop_name = f"{LR_base_finger_name}_{segment}"  # 修改: 直接使用 LR_base_finger_name
                row.operator("object.fill_from_selection_specific", text="", icon='ZOOM_SELECTED').bone_property = prop_name
                row.prop_search(scene, prop_name, obj.data, "bones", text=f"")

                
        # 添加导入/导出预设按钮
        row = layout.row()
        row.operator("object.import_preset", text="导入预设")
        row.operator("object.export_preset", text="导出预设")

        # 添加T-Pose到A-Pose转换按钮
        layout.operator("object.convert_to_apose", text="转换为A-Pose")

        # 添加重命名按钮和补全缺失骨骼按钮到同一行
        row = layout.row()
        row.operator("object.rename_to_mmd", text="1.重命名为MMD")
        row.operator("object.complete_missing_bones", text="2.补全缺失骨骼")

        # 添加IK按钮和创建骨骼集合按钮到同一行
        row = layout.row()
        row.operator("object.add_mmd_ik", text="3.添加MMD IK")
        row.operator("object.create_bone_grouping", text="4.创建骨骼集合")

        # 添加“使用mmdtools转换格式”按钮到最下方
        layout.operator("object.use_mmd_tools_convert", text="使用mmdtools转换格式")