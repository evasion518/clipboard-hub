"""
Clipboard Hub — PyInstaller 入口脚本
用法: pyinstaller clipboard_hub_launcher.spec
"""
import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.main import main

if __name__ == "__main__":
    main()
