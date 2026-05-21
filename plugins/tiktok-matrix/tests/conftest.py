"""pytest 配置 — 让本 plugin 的 skills/xcmo-download/download.py 可导入。"""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent  # plugins/tiktok-matrix/
sys.path.insert(0, str(PLUGIN_ROOT / "skills" / "xcmo-download"))
