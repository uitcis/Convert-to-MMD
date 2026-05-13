这是一个非常硬核且专业的 MMD 模型物理化需求。要实现“依据网格、权重、截面和曲率反推刚体参数并自动生成”，我们需要将 Blender 的 Python API (bpy) 与基础的 3D 几何算法结合起来。

下面我为你提供一个完整的实现思路和核心代码框架。

2-1. 网格分析：权重、截面与曲率变化

这一步的核心是遍历模型的顶点，结合骨骼权重找出“肉感”区域，并通过法线变化判断曲率。

import bpy
import math
from mathutils import Vector

def analyze_mesh(obj, bone_name):
    """
    分析指定骨骼影响下的网格区域，提取截面半径和曲率特征
    """
    mesh = obj.data
    vertex_group = obj.vertex_groups.get(bone_name)
    
    if not vertex_group:
        return []

    vg_index = vertex_group.index
    # 找出所有受该骨骼显著影响的顶点（权重 > 0.1）
    influenced_verts = [v for v in mesh.vertices if any(g.group == vg_index and g.weight > 0.1 for g in v.groups)]
    
    if not influenced_verts:
        return []

    # 1. 计算该区域的几何中心（作为刚体基准位置）
    center = sum((v.co for v in influenced_verts), Vector()) / len(influenced_verts)
    
    # 2. 计算平均截面半径（通过顶点到中心的平均距离估算）
    avg_radius = sum((v.co - center).length for v in influenced_verts) / len(influenced_verts)
    
    # 3. 曲率变化分析（通过相邻面法线的夹角变化来估算）
    # 这里简化处理：如果顶点分布非常集中且法线方向变化剧烈，说明曲率大（适合做球形刚体）
    normal_changes = []
    for v in influenced_verts:
        for edge in v.link_edges:
            other_vert = edge.other_vert(v)
            # 计算两个相连顶点法线的夹角（曲率的离散近似）
            angle = v.normal.angle(other_vert.normal)
            normal_changes.append(angle)
            
    avg_curvature = sum(normal_changes) / len(normal_changes) if normal_changes else 0
    
    return {
        "center": center,
        "radius": avg_radius,
        "curvature": avg_curvature,
        "vertex_count": len(influenced_verts)
    }

2-2. 依据分析结果计算刚体参数

根据上一步的分析数据，我们可以制定一套规则来自动计算刚体的位置、数量、长度和角度。

def calculate_rigidbody_params(analysis_data, bone_obj):
    """
    根据网格分析结果，计算刚体的物理参数
    """
    params = []
    
    for bone_name, data in analysis_data.items():
        # 规则1：如果曲率非常大且顶点集中，判定为“球形刚体”（如胸部、关节肉）
        if data["curvature"] > 0.8: 
            params.append({
                "type": "SPHERE",
                "location": data["center"], # 刚体位置
                "size": data["radius"],     # 刚体半径
                "bone_target": bone_name
            })
        # 规则2：如果曲率较小且分布较长，判定为“胶囊刚体”（如手臂、大腿、长发）
        else:
            # 长度可以根据顶点在骨骼轴向上的极值距离计算，这里做简化估算
            length = data["radius"] * 2.5 
            params.append({
                "type": "CAPSULE",
                "location": data["center"],
                "size": (data["radius"], length), # 胶囊的半径和高度
                "rotation": bone_obj.pose.bones[bone_name].matrix.to_euler(), # 跟随骨骼角度
                "bone_target": bone_name
            })
    return params

2-3. 身体刚体创建代码

最后，我们将计算好的参数转化为 Blender 中实际的刚体物理对象，并设置好与骨骼的约束关系。

        # 1. 创建物理碰撞体网格

        
        # 2. 设置刚体物理属性

        
        # 3. 创建约束，让刚体跟随目标骨骼

        # 4. 隐藏刚体网格（通常物理碰撞体在渲染时不可见）

        rigid_body_obj.hide_render = True
        
        created_bodies.append(rigid_body_obj)
        
    return created_bodies

