import bpy
import mathutils

class OBJECT_OT_auto_physics_builder(bpy.types.Operator):
    """自动构建胸部物理系统"""
    bl_idname = "object.auto_physics_builder"
    bl_label = "自动构建胸部物理"
    bl_description = "自动为角色构建胸部物理系统"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # 检查是否选中了骨架
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架对象")
            return {'CANCELLED'}
        
        armature = obj
        
        # 获取场景中的胸部骨骼属性
        left_chest_bone = context.scene.left_chest_bone
        right_chest_bone = context.scene.right_chest_bone
        
        # 检查用户是否选择了胸部骨骼
        if not left_chest_bone or not right_chest_bone:
            self.report({'ERROR'}, "请选择左侧和右侧胸部骨骼")
            return {'CANCELLED'}
        
        # 检查选择的骨骼是否存在
        if left_chest_bone not in armature.data.bones:
            self.report({'ERROR'}, f"左侧胸部骨骼 '{left_chest_bone}' 不存在")
            return {'CANCELLED'}
        
        if right_chest_bone not in armature.data.bones:
            self.report({'ERROR'}, f"右侧胸部骨骼 '{right_chest_bone}' 不存在")
            return {'CANCELLED'}
        
        # 保存当前模式
        original_mode = armature.mode
        
        try:
            # 1. 分析胸部骨骼结构
            chest_bones = self.analyze_chest_bones(armature, left_chest_bone, right_chest_bone)
            
            # 2. 切换到对象模式并创建刚体
            bpy.ops.object.mode_set(mode='OBJECT')
            self.create_rigid_bodies(armature, chest_bones)
            
            # 3. 创建空物体作为控制节点
            self.create_control_empties(armature, chest_bones)
            
            # 4. 创建约束关系
            self.create_constraints(armature, chest_bones)
            
            self.report({'INFO'}, "胸部物理系统构建完成")
        except Exception as e:
            self.report({'ERROR'}, f"构建失败: {str(e)}")
            return {'CANCELLED'}
        finally:
            # 恢复原始模式
            if original_mode != 'OBJECT':
                # 确保模式值是有效的
                valid_modes = {'EDIT', 'POSE', 'OBJECT'}
                if original_mode in valid_modes:
                    try:
                        bpy.ops.object.mode_set(mode=original_mode)
                    except Exception:
                        # 如果切换失败，至少确保回到对象模式
                        bpy.ops.object.mode_set(mode='OBJECT')
                else:
                    # 如果模式无效，回到对象模式
                    bpy.ops.object.mode_set(mode='OBJECT')
        
        return {'FINISHED'}
    
    def analyze_chest_bones(self, armature, left_chest_bone, right_chest_bone):
        """分析胸部骨骼结构"""
        chest_bones = {
            'left_primary': left_chest_bone,
            'right_primary': right_chest_bone,
            'left_bones': [],
            'right_bones': []
        }
        
        # 收集左侧胸部相关骨骼
        left_bone = armature.data.bones.get(left_chest_bone)
        if left_bone:
            # 收集子骨骼
            def collect_children(bone):
                children = []
                for child in bone.children:
                    children.append(child.name)
                    children.extend(collect_children(child))
                return children
            
            chest_bones['left_bones'] = [left_chest_bone] + collect_children(left_bone)
        
        # 收集右侧胸部相关骨骼
        right_bone = armature.data.bones.get(right_chest_bone)
        if right_bone:
            chest_bones['right_bones'] = [right_chest_bone] + collect_children(right_bone)
        
        return chest_bones
    
    def create_chest_bones(self, armature):
        """创建胸部骨骼结构"""
        edit_bones = armature.data.edit_bones
        
        # 检查是否存在上半身骨骼
        upper_body = edit_bones.get('上半身') or edit_bones.get('上半身')
        if not upper_body:
            raise Exception("未找到上半身骨骼，请确保骨架有'上半身'骨骼")
        
        # 创建胸部调整骨骼
        if 'おっぱい調整' not in edit_bones:
            chest_adjust = edit_bones.new('おっぱい調整')
            chest_adjust.parent = upper_body
            chest_adjust.head = upper_body.tail
            chest_adjust.tail = upper_body.tail + mathutils.Vector((0, 0.1, 0))
        else:
            chest_adjust = edit_bones['おっぱい調整']
        
        # 创建左侧胸部骨骼
        left_chest_bones = [
            ('左胸親', (0.05, -0.05, 0.07)),
            ('左胸', (0.04, -0.02, -0.04)),
            ('左胸先', (0.05, -0.05, -0.03)),
            ('左胸下', (0.06, -0.12, 0.07)),
            ('左胸下先', (0.06, -0.12, -0.08))
        ]
        
        for bone_name, offset in left_chest_bones:
            if bone_name not in edit_bones:
                bone = edit_bones.new(bone_name)
                if bone_name in ['左胸親', '左胸下']:
                    bone.parent = chest_adjust
                    bone.head = chest_adjust.head + mathutils.Vector(offset)
                elif bone_name == '左胸':
                    bone.parent = edit_bones['左胸親']
                    bone.head = edit_bones['左胸親'].head + mathutils.Vector(offset)
                elif bone_name == '左胸下':
                    bone.parent = upper_body
                    bone.head = upper_body.tail + mathutils.Vector(offset)
                elif bone_name == '左胸下先':
                    bone.parent = edit_bones['左胸下']
                    bone.head = edit_bones['左胸下'].head + mathutils.Vector(offset)
                bone.tail = bone.head + mathutils.Vector((0, 0.01, 0))
        
        # 创建右侧胸部骨骼
        right_chest_bones = [
            ('右胸親', (-0.05, -0.05, 0.07)),
            ('右胸', (-0.04, -0.02, -0.04)),
            ('右胸先', (-0.05, -0.05, -0.03)),
            ('右胸下', (-0.06, -0.12, 0.07)),
            ('右胸下先', (-0.06, -0.12, -0.08)),
            ('右胸下先', (-0.06, -0.12, -0.01))
        ]
        
        for bone_name, offset in right_chest_bones:
            if bone_name not in edit_bones:
                bone = edit_bones.new(bone_name)
                if bone_name in ['右胸親', '右胸下']:
                    bone.parent = chest_adjust
                    bone.head = chest_adjust.head + mathutils.Vector(offset)
                elif bone_name == '右胸':
                    bone.parent = edit_bones['右胸親']
                    bone.head = edit_bones['右胸親'].head + mathutils.Vector(offset)
                elif bone_name == '右胸下':
                    bone.parent = upper_body
                    bone.head = upper_body.tail + mathutils.Vector(offset)
                elif bone_name == '右胸下先':
                    bone.parent = edit_bones['右胸下']
                    bone.head = edit_bones['右胸下'].head + mathutils.Vector(offset)
                elif bone_name == '右胸下先':
                    bone.parent = edit_bones['右胸下']
                    bone.head = edit_bones['右胸下'].head + mathutils.Vector(offset)
                bone.tail = bone.head + mathutils.Vector((0, 0.01, 0))
    
    def create_rigid_bodies(self, armature, chest_bones):
        """创建刚体"""
        # 确保物理引擎启用
        bpy.context.scene.rigidbody_world.enabled = True
        
        # 创建胸部主刚体
        chest_rb = self.create_rigid_body(armature, '胸', 1.0)
        
        # 为左侧胸部骨骼创建刚体
        for bone_name in chest_bones['left_bones']:
            # 根据骨骼位置设置质量
            mass = 0.1 if '先' in bone_name else 0.2 if '親' in bone_name else 0.15
            self.create_rigid_body(armature, bone_name, mass)
        
        # 为右侧胸部骨骼创建刚体
        for bone_name in chest_bones['right_bones']:
            # 根据骨骼位置设置质量
            mass = 0.1 if '先' in bone_name else 0.2 if '親' in bone_name else 0.15
            self.create_rigid_body(armature, bone_name, mass)
    
    def create_rigid_body(self, armature, bone_name, mass):
        """为指定骨骼创建刚体"""
        # 检查骨骼是否存在
        if bone_name not in armature.data.bones:
            return
        
        # 保存当前活动对象和选择状态
        original_active = bpy.context.view_layer.objects.active
        original_selected = [obj for obj in bpy.context.selected_objects]
        
        try:
            # 确保在对象模式
            if bpy.context.active_object:
                if bpy.context.active_object.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            
            # 创建一个空物体作为刚体容器
            rb_obj = bpy.data.objects.new(f"{bone_name}_rb", None)
            bpy.context.collection.objects.link(rb_obj)
            
            # 确保物理引擎启用
            if not bpy.context.scene.rigidbody_world:
                bpy.context.scene.rigidbody_world = bpy.data.worlds.new("RigidBodyWorld")
            
            # 选择并激活空物体
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            bpy.context.view_layer.objects.active = rb_obj
            rb_obj.select_set(True)
            
            # 尝试添加刚体
            try:
                bpy.ops.rigidbody.object_add()
                if rb_obj.rigid_body:
                    rb_obj.rigid_body.type = 'ACTIVE'
                    rb_obj.rigid_body.mass = mass
            except Exception:
                # 如果添加刚体失败，至少创建空物体
                pass
            
            # 位置跟随骨骼
            rb_obj.location = armature.data.bones[bone_name].head_local
            
            return rb_obj
        finally:
            # 恢复原始选择和活动对象
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            for obj in original_selected:
                obj.select_set(True)
            if original_active:
                bpy.context.view_layer.objects.active = original_active
    
    def create_control_empties(self, armature, chest_bones):
        """创建空物体作为控制节点"""
        # 为左侧胸部骨骼创建控制空物体
        for i, bone_name in enumerate(chest_bones['left_bones']):
            empty_name = f"00{i}_J.{bone_name}"
            # 检查是否已存在
            if empty_name not in bpy.data.objects:
                empty = bpy.data.objects.new(empty_name, None)
                bpy.context.collection.objects.link(empty)
                empty.empty_display_type = 'ARROWS'
                empty.empty_display_size = 0.05
                # 位置跟随骨骼
                if bone_name in armature.data.bones:
                    empty.location = armature.data.bones[bone_name].head_local
        
        # 为右侧胸部骨骼创建控制空物体
        for i, bone_name in enumerate(chest_bones['right_bones']):
            empty_name = f"00{i+len(chest_bones['left_bones'])}_J.{bone_name}"
            # 检查是否已存在
            if empty_name not in bpy.data.objects:
                empty = bpy.data.objects.new(empty_name, None)
                bpy.context.collection.objects.link(empty)
                empty.empty_display_type = 'ARROWS'
                empty.empty_display_size = 0.05
                # 位置跟随骨骼
                if bone_name in armature.data.bones:
                    empty.location = armature.data.bones[bone_name].head_local
    
    def create_constraints(self, armature, chest_bones):
        """创建约束关系"""
        # 切换到姿态模式
        bpy.ops.object.mode_set(mode='POSE')
        
        # 为左侧胸部骨骼添加约束
        for i, bone_name in enumerate(chest_bones['left_bones']):
            if bone_name in armature.pose.bones:
                p_bone = armature.pose.bones[bone_name]
                
                # 添加复制位置约束
                copy_loc = p_bone.constraints.new('COPY_LOCATION')
                copy_loc.name = f"复制位置_{bone_name}"
                
                # 查找对应的控制空物体
                empty_name = f"00{i}_J.{bone_name}"
                if empty_name in bpy.data.objects:
                    copy_loc.target = bpy.data.objects[empty_name]
        
        # 为右侧胸部骨骼添加约束
        for i, bone_name in enumerate(chest_bones['right_bones']):
            if bone_name in armature.pose.bones:
                p_bone = armature.pose.bones[bone_name]
                
                # 添加复制位置约束
                copy_loc = p_bone.constraints.new('COPY_LOCATION')
                copy_loc.name = f"复制位置_{bone_name}"
                
                # 查找对应的控制空物体
                empty_name = f"00{i+len(chest_bones['left_bones'])}_J.{bone_name}"
                if empty_name in bpy.data.objects:
                    copy_loc.target = bpy.data.objects[empty_name]

        # 恢复到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

def register():
    bpy.utils.register_class(OBJECT_OT_auto_physics_builder)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_auto_physics_builder)

if __name__ == "__main__":
    register()
