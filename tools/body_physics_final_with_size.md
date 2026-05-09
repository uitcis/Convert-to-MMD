基于你之前的提问和 MMD 物理模拟的需求，通过加权网格顶点来计算刚体参数是最准确的方法，这能让刚体完美贴合蒙皮变形后的模型体积。

以下是计算刚体位置、长度、直径（半径）、旋转角度和数量的完整算法流程。

🎯 核心思路：基于“顶点组”的统计分析
不要只看骨骼，要看受该骨骼（或刚体）影响的所有网格顶点。我们将这些顶点视为一团“点云”，通过统计学方法计算这团点云的几何特征。

刚体数量：自动分段算法
对于手臂、腿、尾巴等长条形部位，一个刚体是不够的，你需要计算需要多少个刚体。

输入：该部位的所有顶点（例如“左臂”顶点组）。
算法逻辑：
    提取中心线：
        沿着骨骼的主轴（例如 Y 轴），将顶点按高度切片。
        计算每一层切片的中心点，连成一条曲线（中心线）。
    曲率检测与分段：
        计算中心线的曲率。
        在曲率变化大（弯曲剧烈）的地方，或者长度超过阈值（例如每 5cm）的地方进行切割。
    确定数量：
        切割出的段数 = 刚体数量。
       参考：PMDEditor 的自动测量功能就是基于极值点检测和中心线提取来实现的。

位置：加权质心
刚体的位置应该是它所包裹的那部分网格的质量中心。

计算步骤：
    获取属于当前刚体段的所有顶点集合 V = {v_1, v_2, ..., v_n}。
    获取每个顶点对该刚体骨骼的权重 w_i。
    加权平均公式：
        P_{center} = frac{sum_{i=1}^{n} (v_i cdot w_i)}{sum_{i=1}^{n} w_i}
    *结果 P_{center} 即为刚体的世界坐标位置。*

旋转角度：主成分分析
这是最关键的一步。刚体的朝向必须跟随网格的弯曲方向。

算法逻辑：
    去中心化：将所有顶点坐标减去质心 P_{center}。
    构建协方差矩阵：
        计算这团点云在 X, Y, Z 轴上的分布相关性。
        C = sum_{i=1}^{n} w_i cdot (v_i - P_{center})^T cdot (v_i - P_{center})
    特征值分解：
        计算协方差矩阵的特征向量。
        最大特征值对应的特征向量 = 主轴方向（长度方向）。
        次大特征值对应的特征向量 = 次轴方向（宽度方向）。
    构建旋转矩阵：
        将这三个特征向量归一化后，直接组成一个 3times3 的旋转矩阵，再转换为四元数。
    *这就是该刚体最精准的旋转角度。*

长度与直径：投影极值法
有了主轴方向后，我们可以将三维顶点投影到一维轴线上来计算尺寸。

计算长度：
    将所有顶点 v_i 投影到主轴方向向量上。
    找到投影值的最大值 Max_{proj} 和 最小值 Min_{proj}。
    长度 L = Max_{proj} - Min_{proj}。
   建议增加一点余量（例如 times 1.1）以防止穿模。

计算直径（半径）：
    计算每个顶点到主轴的垂直距离（点到直线的距离）。
    取这些距离的加权平均值或 90% 分位值（排除噪点）。
    直径 D = 2 times text{平均垂直距离}。
   如果是胶囊体刚体，半径 R = D/2。

💻 Python 代码实现示例 (基于 NumPy)

这段代码展示了如何利用顶点数据计算上述参数：

import numpy as np

def calculate_rigid_body_params(vertices, weights):
    """
    vertices: (N, 3) 数组，顶点的当前世界坐标
    weights:  (N,)   数组，顶点对该刚体的权重
    """
    
    # 1. 计算加权质心 (位置)
    total_weight = np.sum(weights)
    center = np.sum(vertices * weights[:, np.newaxis], axis=0) / total_weight
    
    # 2. 去中心化
    centered_vertices = vertices - center
    
    # 3. 计算协方差矩阵并进行 SVD 分解 (求旋转/朝向)
    # 协方差矩阵 C = X^T * X
    # 使用 SVD 可以直接得到主轴方向
    cov_matrix = np.cov(centered_vertices.T, aweights=weights)
    eigen_vals, eigen_vecs = np.linalg.eigh(cov_matrix)
    
    # 特征向量即为主轴。按特征值大小排序，最大的为主轴 (长度方向)
    order = np.argsort(eigen_vals)[::-1]
    principal_axis = eigen_vecs[:, order] # 长度方向向量
    secondary_axis = eigen_vecs[:, order] # 宽度方向向量
    
    # 构建旋转矩阵 (这里简化处理，实际需构建正交基)
    # 注意：需处理坐标系手性，确保矩阵行列式为 1
    rotation_matrix = np.column_stack((secondary_axis, eigen_vecs[:, order], principal_axis))
    
    # 4. 计算长度和直径
    # 将顶点投影到主轴上
    projections = np.dot(centered_vertices, principal_axis)
    length = np.max(projections) - np.min(projections)
    
    # 计算点到主轴的距离 (垂直距离)
    # 距离 = |向量 x 主轴方向|
    cross_prods = np.cross(centered_vertices, principal_axis)
    distances = np.linalg.norm(cross_prods, axis=1)
    
    # 直径取加权平均或最大值
    radius = np.average(distances, weights=weights) * 1.2 # 增加 20% 包裹余量
    
    return {
        "position": center,
        "length": length,
        "radius": radius,
        "direction": principal_axis, # 可用于计算四元数
        "rotation_matrix": rotation_matrix
    }

📌 总结对照表
参数   计算方法   核心数学工具
数量   中心线曲率分析 / 长度阈值分段   几何切片、曲率计算

位置   顶点的加权平均   加权质心公式

旋转   点云分布的主轴方向   协方差矩阵 + 特征值分解 (或 SVD)

长度   顶点在主轴上的投影跨度   向量投影、极值差

| 直径 | 顶点到主轴的平均垂直距离 | 点到直线距离公式 |

通过这种方法生成的刚体，在手臂弯曲时，刚体也会呈现自然的弯曲排列，而不是僵硬地跟随骨骼旋转，能极大提升 MMD 物理模拟（如头发、衣服碰撞）的真实感。