"""pytest 配置 — 让各 skill 下的 .py 可导入。"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "xcmo-mobile"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "tk-template-scout"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "tk-niche-scout"))
