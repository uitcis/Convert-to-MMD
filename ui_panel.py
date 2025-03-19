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
            split = row.split(factor=0.85, align=True)
            split.prop_search(scene, prop_name, obj.data, "bones", text=label_text)
            op = split.operator("object.fill_from_selection_specific", text="", icon='ZOOM_SELECTED')
            op.bone_property = prop_name
            
        def add_symmetric_bones_with_buttons(layout, label_text, left_prop, right_prop):
            row = layout.row(align=True)
            split1 = row.split(factor=0.2, align=True)
            split1.label(text=label_text)
            split2 = split1.split(factor=0.5, align=True)
            col_left = split2.column(align=True)
            col_right = split2.column(align=True)
            
            add_bone_row_with_button(col_left, "left", left_prop)
            add_bone_row_with_button(col_right, "right", right_prop)

        main_col = layout.column(align=True)

        # 全ての親到腰部分
        full_body_box = main_col.box()
        col = full_body_box.column()

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

        # 可選骨骼部分
        opt_box = main_col.box()
            
        add_bone_row_with_button(opt_box, "操作中心:", "control_center_bone")

        add_symmetric_bones_with_buttons(opt_box, "目:", "left_eye_bone", "right_eye_bone")
        add_symmetric_bones_with_buttons(opt_box, "足先EX:", "left_toe_bone", "right_toe_bone")

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

        fingers_box = opt_box.column(align=True)
        for LR_base_finger_name, segments, label_text in finger_labels:
            side = "left" if "left" in LR_base_finger_name else "right"
            
            row = fingers_box.row(align=True)
            row.label(text=f"{label_text}:")

            for segment in segments:
                prop_name = f"{LR_base_finger_name}_{segment}"  # 修改: 直接使用 LR_base_finger_name
                row.prop_search(scene, prop_name, obj.data, "bones", text=f" {segment}")
                op = row.operator("object.fill_from_selection_specific", text="", icon='ZOOM_SELECTED')
                op.bone_property = prop_name
                
        # 添加T-Pose到A-Pose转换按钮
        layout.operator("object.convert_to_apose", text="转换为A-Pose")

        # 添加重命名按钮
        layout.operator("object.rename_to_mmd", text="重命名为MMD")

        # 添加补全缺失骨骼按钮
        layout.operator("object.complete_missing_bones", text="补全缺失骨骼")

        # 添加导入预设按钮
        layout.operator("object.import_preset", text="导入预设")

        # 添加导出预设按钮
        layout.operator("object.export_preset", text="导出预设")

        # 添加IK按钮
        layout.operator("object.add_mmd_ik", text="添加MMD IK")
