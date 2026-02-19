import os
import sys
import winshell
from win32com.client import Dispatch

def create_shortcut():
    # 获取桌面路径
    desktop = winshell.desktop()
    shortcut_path = os.path.join(desktop, "Pry.lnk")
    
    # 获取当前项目的根目录和执行文件
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_script = os.path.join(base_dir, "src", "window_monitor.py")
    
    # 找到 pythonw.exe (无控制台)
    # 通常在 venv/Scripts 目录下，如果没有则尝试系统路径
    pythonw_executable = os.path.join(base_dir, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(pythonw_executable):
        pythonw_executable = sys.executable.replace("python.exe", "pythonw.exe")

    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    
    shortcut.TargetPath = pythonw_executable
    shortcut.Arguments = f'"{target_script}"'
    shortcut.WorkingDirectory = base_dir
    shortcut.WindowStyle = 7  # 隐藏窗口
    
    # 设置图标 (如果存在 .ico 文件，否则暂用 python 图标)
    ico_path = os.path.join(base_dir, "src", "pry.ico")
    if os.path.exists(ico_path):
        shortcut.IconLocation = ico_path
    
    shortcut.save()
    print(f"✅ 桌面快捷方式已创建: {shortcut_path}")
    print(f"   使用程序: {pythonw_executable}")
    print(f"   执行脚本: {target_script}")

if __name__ == "__main__":
    try:
        create_shortcut()
    except Exception as e:
        print(f"❌ 创建快捷方式失败: {e}")
        print("请确保已安装 pywin32 和 winshell: pip install pywin32 winshell")
