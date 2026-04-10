import bpy
import math
from mathutils import Vector
from ..bone_utils import create_or_update_bone

# 足D相关骨骼配置字典（按创建顺序排序）
# 注意：head_position和tail_position会在运行时根据原始骨骼位置动态计算



class OBJECT_OT_add_leg_d_bones(bpy.types.Operator):
    """添加MMD腿部D骨骼"""
    bl_idname = "object.add_leg_d_bones"
    bl_label = "添加腿部D骨骼"
    
    def execute(self, context):
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "请选择一个骨架")
            return {'CANCELLED'}
        
        # 切换到编辑模式
        if context.mode != 'EDIT_ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature.data.edit_bones
        D_bone_properties = {
            # 右侧骨骼
            "右足D": {
                "original_bone": "右足",
                "head_position": edit_bones["右足"].head,
                "tail_position": edit_bones["右足"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "下半身",
                "use_deform": True
            },
            "_dummy_右足D": {
                "original_bone": "右足",
                "head_position": edit_bones["右足"].head,
                "tail_position": edit_bones["右足"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "右足",
                "use_deform": False
            },
            "_shadow_右足D": {
                "original_bone": "右足",
                "head_position": edit_bones["右足"].head,    
                "tail_position": edit_bones["右足"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "下半身",
                "use_deform": False
            },
            "右ひざD": {
                "original_bone": "右ひざ",
                "head_position": edit_bones["右ひざ"].head,
                "tail_position": edit_bones["右ひざ"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "右足D",
                "use_deform": True
            },
            "_dummy_右ひざD": {
                "original_bone": "右ひざ",
                "head_position": edit_bones["右ひざ"].head,
                "tail_position": edit_bones["右ひざ"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "右ひざ",
                "use_deform": False
            },
            "_shadow_右ひざD": {
                "original_bone": "右ひざ",
                "head_position": edit_bones["右ひざ"].head,
                "tail_position": edit_bones["右ひざ"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "右足",
                "use_deform": False
            },
            "右足首D": {
                "original_bone": "右足首",
                "head_position": edit_bones["右足首"].head,
                "tail_position": edit_bones["右足首"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "右ひざD",
                "use_deform": True
            },
            "_dummy_右足首D": {
                "original_bone": "右足首",
                "head_position": edit_bones["右足首"].head,
                "tail_position": edit_bones["右足首"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "右足首",
                "use_deform": False
            },
            "_shadow_右足首D": {
                "original_bone": "右足首",
                "head_position": edit_bones["右足首"].head,
                "tail_position": edit_bones["右足首"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "右ひざ",
                "use_deform": False
            },
            "右足先EX": {
                "original_bone": "右足先EX",
                "head_position": edit_bones["右足先EX"].head,
                "tail_position": edit_bones["右足先EX"].tail,
                "use_connect": False,
                "parent_name": "右足首D",
                "use_deform": True
            },
            
            # 左侧骨骼
            "左足D": {
                "original_bone": "左足",
                "head_position": edit_bones["左足"].head,
                "tail_position": edit_bones["左足"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "下半身",
                "use_deform": True
            },
            "_dummy_左足D": {
                "original_bone": "左足",
                "head_position": edit_bones["左足"].head,
                "tail_position": edit_bones["左足"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "左足",
                "use_deform": False
            },
            "_shadow_左足D": {
                "original_bone": "左足",
                "head_position": edit_bones["左足"].head,
                "tail_position": edit_bones["左足"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "下半身",
                "use_deform": False
            },
            "左ひざD": {
                "original_bone": "左ひざ",
                "head_position": edit_bones["左ひざ"].head,
                "tail_position": edit_bones["左ひざ"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "左足D",
                "use_deform": True
            },
            "_dummy_左ひざD": {
                "original_bone": "左ひざ",
                "head_position": edit_bones["左ひざ"].head,
                "tail_position": edit_bones["左ひざ"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "左ひざ",
                "use_deform": False
            },
            "_shadow_左ひざD": {
                "original_bone": "左ひざ",
                "head_position": edit_bones["左ひざ"].head,
                "tail_position": edit_bones["左ひざ"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "左足",
                "use_deform": False
            },
            "左足首D": {
                "original_bone": "左足首",
                "head_position": edit_bones["左足首"].head,
                "tail_position": edit_bones["左足首"].head+Vector((0, 0, 0.1)),
                "use_connect": False,
                "parent_name": "左ひざD",
                "use_deform": True
            },
            "_dummy_左足首D": {
                "original_bone": "左足首",
                "head_position": edit_bones["左足首"].head,
                "tail_position": edit_bones["左足首"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "左足首",
                "use_deform": False
            },
            "_shadow_左足首D": {
                "original_bone": "左足首",
                "head_position": edit_bones["左足首"].head,
                "tail_position": edit_bones["左足首"].head+Vector((0, 0, 0.08)),
                "use_connect": False,
                "parent_name": "左ひざ",
                "use_deform": False
            },
            "左足先EX": {
                "original_bone": "左足先EX",
                "head_position": edit_bones["左足先EX"].head,
                "tail_position": edit_bones["左足先EX"].tail,
                "use_connect": False,
                "parent_name": "左足首D",
                "use_deform": True
            }
        }        
        # 检查是否已经存在D骨骼
        existing_d_bones = []
        for bone in edit_bones:
            if bone.name.endswith('D') and ('足' in bone.name or 'ひざ' in bone.name or '足首' in bone.name):
                existing_d_bones.append(bone.name)
        
        if existing_d_bones:
            self.report({'INFO'}, f"已经存在D骨骼: {', '.join(existing_d_bones)}，跳过操作")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}
        
        bones_added = 0
        
        # 保存需要处理约束的原始骨骼名称
        original_bones_to_process = set()
        
        # 创建所有骨骼 
        for bone_name, properties in D_bone_properties.items():
            create_or_update_bone(
                edit_bones, bone_name, 
                properties["head_position"], 
                properties["tail_position"], 
                properties.get("use_connect", False), 
                properties["parent_name"], 
                properties.get("use_deform", True)
            )
            # 记录需要处理约束的原始骨骼
            original_bone_name = properties["original_bone"]
            
            if not bone_name.startswith('_') and not bone_name.endswith('EX'):
                original_bones_to_process.add(original_bone_name)
            
            bones_added += 1
        
        # 处理约束和顶点组
        if original_bones_to_process:
            # 切换到物体模式以添加约束和修改顶点组
            bpy.ops.object.mode_set(mode='OBJECT')
            
            for original_name in original_bones_to_process:
                d_name = original_name + 'D'
                
                if d_name not in armature.pose.bones:
                    continue
                
                # 获取D骨骼的骨骼对象
                d_pose_bone = armature.pose.bones[d_name]
                
                # 锁定腿部D骨骼的移动以及X和Z轴的旋转
                # 锁定移动
                d_pose_bone.lock_location[0] = True
                d_pose_bone.lock_location[1] = True
                d_pose_bone.lock_location[2] = True
                # 为D骨骼添加TRANSFORM约束
                transform_constraint = d_pose_bone.constraints.new('TRANSFORM')
                transform_constraint.name = "mmd_additional_rotation"
                transform_constraint.target = armature
                transform_constraint.subtarget = f"_shadow_{d_name}"
                transform_constraint.influence = 1.0
                transform_constraint.use_motion_extrapolate = True
                # 设置所有者空间为局部空间
                transform_constraint.owner_space = 'LOCAL'
                # 设置目标空间为局部空间
                transform_constraint.target_space = 'LOCAL'
                # 设置从旋转映射到旋转
                transform_constraint.map_from = 'ROTATION'
                transform_constraint.map_to = 'ROTATION'
                # 设置映射自的模式为XYZ欧拉
                transform_constraint.from_rotation_mode = 'XYZ'
                # 设置映射模式为XYZ欧拉
                transform_constraint.to_euler_order = 'XYZ'
                # 设置混合选项为初始后
                transform_constraint.mix_mode_rot = 'AFTER'
                
                # 设置旋转范围（将角度转换为弧度）
                transform_constraint.from_min_x_rot = math.radians(-180.0)
                transform_constraint.from_min_y_rot = math.radians(-180.0)
                transform_constraint.from_min_z_rot = math.radians(-180.0)
                transform_constraint.from_max_x_rot = math.radians(180.0)
                transform_constraint.from_max_y_rot = math.radians(180.0)
                transform_constraint.from_max_z_rot = math.radians(180.0)
                transform_constraint.to_min_x_rot = math.radians(-180.0)
                transform_constraint.to_min_y_rot = math.radians(-180.0)
                transform_constraint.to_min_z_rot = math.radians(-180.0)
                transform_constraint.to_max_x_rot = math.radians(180.0)
                transform_constraint.to_max_y_rot = math.radians(180.0)
                transform_constraint.to_max_z_rot = math.radians(180.0)
                
                # 为shadow骨骼添加COPY_TRANSFORMS约束
                shadow_bone_name = f"_shadow_{d_name}"
                if shadow_bone_name in armature.pose.bones:
                    shadow_bone = armature.pose.bones[shadow_bone_name]
                    # 清除现有约束
                    for constraint in list(shadow_bone.constraints):
                        shadow_bone.constraints.remove(constraint)
                    # 添加COPY_TRANSFORMS约束
                    shadow_constraint = shadow_bone.constraints.new('COPY_TRANSFORMS')
                    shadow_constraint.name = "mmd_tools_at_dummy"
                    shadow_constraint.target = armature
                    shadow_constraint.subtarget = f"_dummy_{d_name}"
                    shadow_constraint.influence = 1.0
                    # 设置为姿态空间
                    shadow_constraint.owner_space = 'POSE'
                    shadow_constraint.target_space = 'POSE'
                    # 移除目标剪切
                    shadow_constraint.remove_target_shear = False
                
                # 把标准骨骼对应的顶点组名字改成D骨骼的名字
                for mesh in bpy.context.scene.objects:
                    if mesh.type == 'MESH' and mesh.parent == armature:
                        if original_name in mesh.vertex_groups:
                            # 重命名顶点组
                            vg = mesh.vertex_groups[original_name]
                            vg.name = d_name
        
        # 返回物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 对创建的骨骼进行分组
        bpy.ops.object.create_bone_group()
        
        self.report({'INFO'}, f"已添加 {bones_added} 个腿部D骨骼")
        return {'FINISHED'}


# 注册操作类
def register():
    bpy.utils.register_class(OBJECT_OT_add_leg_d_bones)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_leg_d_bones)


if __name__ == "__main__":
    register()
