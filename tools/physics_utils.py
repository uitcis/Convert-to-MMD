"""
物理构建共享工具模块

包含：
    1. 内存监控与垃圾回收辅助函数
    2. MMD Tools 兼容性导入
    3. 数学工具（特征值分解、旋转矩阵构建）
"""

import bpy
import math
import gc

from mathutils import Vector, Matrix

CHUNK_SIZE = 2000
MAX_MEMORY_PERCENTAGE = 80

from .. import bone_utils

try:
    from bl_ext.blender_org.mmd_tools.core.rigid_body import FnRigidBody
    from bl_ext.blender_org.mmd_tools.core.model import FnModel
    MMD_TOOLS_AVAILABLE = True
except ImportError:
    try:
        from mmd_tools.core.rigid_body import FnRigidBody
        from mmd_tools.core.model import FnModel
        MMD_TOOLS_AVAILABLE = True
    except ImportError:
        FnRigidBody = None
        FnModel = None
        MMD_TOOLS_AVAILABLE = False


# ---------------------------------------------------------------------------
# 内存监控与垃圾回收辅助函数
# ---------------------------------------------------------------------------

def _get_memory_info():
    """获取系统内存信息（使用 Blender API 和系统 API）"""
    result = {
        'memory_percent': None,
        'used_gb': None,
        'available_gb': None,
        'peak_gb': None
    }

    try:
        result['used_gb'] = bpy.app.debug_memory_usage() / (1024**3)
        result['peak_gb'] = bpy.app.debug_memory_peak() / (1024**3)
    except:
        pass

    import os
    if os.name == 'nt':
        try:
            from ctypes import windll, Structure, c_ulonglong, byref
            class MEMORYSTATUSEX(Structure):
                _fields_ = [("dwLength", c_ulonglong), ("dwMemoryLoad", c_ulonglong),
                            ("ullTotalPhys", c_ulonglong), ("ullAvailPhys", c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = c_ulonglong(24)
            if windll.kernel32.GlobalMemoryStatusEx(byref(stat)):
                result['memory_percent'] = stat.dwMemoryLoad
                result['used_gb'] = (stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3)
                result['available_gb'] = stat.ullAvailPhys / (1024**3)
        except:
            pass
    else:
        try:
            total_mem = None
            avail_mem = None
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        total_mem = int(line.split()[1]) * 1024
                    elif line.startswith('MemAvailable:'):
                        avail_mem = int(line.split()[1]) * 1024
            if total_mem and avail_mem:
                result['memory_percent'] = ((total_mem - avail_mem) / total_mem) * 100
                result['used_gb'] = (total_mem - avail_mem) / (1024**3)
                result['available_gb'] = avail_mem / (1024**3)
        except:
            pass

    return result


def _check_memory_and_gc(force=False):
    """
    检查内存使用并在必要时触发垃圾回收

    当内存使用率超过 GC_MEMORY_THRESHOLD (70%) 时触发 gc.collect()，
    当内存使用率超过 MAX_MEMORY_PERCENTAGE (80%) 时返回 False 阻止继续处理。

    Args:
        force: 是否强制执行内存检查和GC

    Returns:
        bool: True=继续处理，False=内存不足应停止
    """
    GC_MEMORY_THRESHOLD = 70

    mem_info = _get_memory_info()
    memory_percent = mem_info['memory_percent'] if mem_info else None

    # 强制触发GC（只在force=True或内存超过阈值时）
    if force or (memory_percent is not None and memory_percent > GC_MEMORY_THRESHOLD):
        collected = gc.collect()

        if force and collected > 0:
            mem_info2 = _get_memory_info()
            parts = [f"GC回收: {collected}"]
            if mem_info2 and mem_info2['memory_percent'] is not None:
                parts.append(f"使用率: {mem_info2['memory_percent']:.1f}%")
            print(f"[GC] {' | '.join(parts)}")

        if memory_percent is not None and memory_percent > GC_MEMORY_THRESHOLD and not force:
            parts = [f"已回收 {collected} 个对象"]
            if mem_info['used_gb'] is not None:
                parts.append(f"已使用: {mem_info['used_gb']:.2f} GB")
            if memory_percent is not None:
                parts.append(f"使用率: {memory_percent:.1f}%")
            print(f"[GC] {' | '.join(parts)}")

    if memory_percent is not None and memory_percent > MAX_MEMORY_PERCENTAGE:
        parts = [f"[内存警告] 内存使用率过高 ({memory_percent:.1f}% > {MAX_MEMORY_PERCENTAGE}%)，正在终止操作..."]
        if mem_info['used_gb'] is not None:
            parts.append(f"已使用: {mem_info['used_gb']:.2f} GB")
        if mem_info['available_gb'] is not None:
            parts.append(f"可用: {mem_info['available_gb']:.2f} GB")
        print('\n'.join(parts))
        return False
    return True


# ---------------------------------------------------------------------------
# 数学工具
# ---------------------------------------------------------------------------

def _solve_eigen_3x3_sym(m):
    """
    求解3x3对称矩阵的特征值和特征向量（使用Jacobi迭代法，数值稳定）

    参数:
        m: 3x3对称矩阵，列表形式 [[a,b,c],[b,d,e],[c,e,f]]

    返回:
        eigenvalues: 特征值列表 [lambda1, lambda2, lambda3]，按升序排列
        eigenvectors: 特征向量列表 [[x1,y1,z1], [x2,y2,z2], [x3,y3,z3]]
    """
    a = [[m[i][j] for j in range(3)] for i in range(3)]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]

    max_iter = 100
    for _ in range(max_iter):
        max_val = 0.0
        p = 0
        q = 1
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(a[i][j]) > max_val:
                    max_val = abs(a[i][j])
                    p = i
                    q = j

        if max_val < 1e-10:
            break

        if a[p][p] == a[q][q]:
            theta = math.pi / 4 if a[p][q] > 0 else -math.pi / 4
        else:
            theta = 0.5 * math.atan(2 * a[p][q] / (a[p][p] - a[q][q]))

        c = math.cos(theta)
        s = math.sin(theta)

        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]

        a[p][p] = c * c * app - 2 * c * s * apq + s * s * aqq
        a[q][q] = s * s * app + 2 * c * s * apq + c * c * aqq
        a[p][q] = 0.0
        a[q][p] = 0.0

        for r in range(3):
            if r != p and r != q:
                apr = a[p][r]
                aqr = a[q][r]
                a[p][r] = c * apr - s * aqr
                a[r][p] = a[p][r]
                a[q][r] = s * apr + c * aqr
                a[r][q] = a[q][r]

        for r in range(3):
            vpr = v[p][r]
            vqr = v[q][r]
            v[p][r] = c * vpr - s * vqr
            v[q][r] = s * vpr + c * vqr

    eigenvalues = [a[i][i] for i in range(3)]
    eigenvectors = [[v[i][j] for i in range(3)] for j in range(3)]

    idx = sorted(range(3), key=lambda i: eigenvalues[i])
    eigenvalues = [eigenvalues[i] for i in idx]
    eigenvectors = [eigenvectors[i] for i in idx]

    return eigenvalues, eigenvectors


def _build_rotation_matrix(axis):
    """构建将世界Z轴旋转到给定轴方向的旋转矩阵"""
    z_axis = Vector((0, 0, 1))

    if axis.dot(z_axis) > 0.9999:
        return Matrix.Identity(3)
    if axis.dot(z_axis) < -0.9999:
        return Matrix.Rotation(math.pi, 3, 'X')

    rot_axis = z_axis.cross(axis)
    if rot_axis.length < 0.0001:
        return Matrix.Identity(3)
    rot_axis.normalize()
    angle = math.acos(max(-1.0, min(1.0, axis.dot(z_axis))))

    return Matrix.Rotation(angle, 3, rot_axis)
