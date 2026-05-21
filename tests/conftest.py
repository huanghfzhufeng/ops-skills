"""pytest 共享配置 — 让 download.py 可导入。"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "xcmo-download"))
