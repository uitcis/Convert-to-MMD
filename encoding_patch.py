"""
中文控制台编码修复模块

修复 Blender 控制台中文乱码问题。
"""
import sys

_patch_applied = False


def set_console_encoding():
    """设置控制台编码为UTF-8，处理Windows中文乱码问题"""
    try:
        # 只在 Windows 系统上应用
        if sys.platform == 'win32':
            import ctypes
            # Windows 控制台设置为 UTF-8
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)  # CP_UTF8
            kernel32.SetConsoleCP(65001)
    except Exception:
        # 如果失败（比如非Windows系统或权限问题），忽略错误
        pass


def apply_encoding_patch():
    """应用编码补丁（只应用一次）"""
    global _patch_applied
    if not _patch_applied:
        set_console_encoding()
        _patch_applied = True


def remove_encoding_patch():
    """移除编码补丁（空操作，因为控制台编码设置是全局的）"""
    global _patch_applied
    _patch_applied = False
