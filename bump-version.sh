#!/usr/bin/env bash
# bump-version.sh — 同步更新 plugin.json 和 marketplace.json 的 version。
#
# 单 plugin 架构下两份 JSON 必须保持 version 一致，否则 /plugin upgrade
# 行为不可预测。本脚本一行改两处。
#
# 用法:
#   ./bump-version.sh 3.0.1
#
# 跑完手动:
#   1. 编辑 CHANGELOG.md 加新版段
#   2. git add -A && git commit -m "chore: release v<new-version>"
#   3. git tag v<new-version>
#   4. git push && git push --tags

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "用法: $0 <new-version>"
  echo "示例: $0 3.0.1"
  exit 1
fi

NEW_VERSION="$1"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_ROOT"

python3 - "$NEW_VERSION" <<'PYEOF'
"""同步更新 plugin.json + marketplace.json[0] 的 version。"""
import json
import sys
from pathlib import Path

new_version = sys.argv[1]

# 1) plugin.json
pj = Path(".claude-plugin/plugin.json")
data = json.loads(pj.read_text(encoding="utf-8"))
old = data["version"]
data["version"] = new_version
pj.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"  plugin.json:      {old} → {new_version}")

# 2) marketplace.json plugins[0]
mj = Path(".claude-plugin/marketplace.json")
mdata = json.loads(mj.read_text(encoding="utf-8"))
plugin = mdata["plugins"][0]  # 单 plugin
old = plugin.get("version", "?")
plugin["version"] = new_version
mj.write_text(
    json.dumps(mdata, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"  marketplace.json: {old} → {new_version}")
PYEOF

echo ""
echo "✓ version 已同步到 $NEW_VERSION"
echo ""
echo "下一步："
echo "  1. 编辑 CHANGELOG.md 加 [$NEW_VERSION] 段"
echo "  2. git add -A && git commit -m \"chore: release v$NEW_VERSION\""
echo "  3. git tag v$NEW_VERSION"
echo "  4. git push && git push --tags"
