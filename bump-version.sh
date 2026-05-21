#!/usr/bin/env bash
# bump-version.sh — 同步更新 plugin.json 和 marketplace.json 的 version 字段。
#
# Plugin Code 的 version 必须在 .claude-plugin/plugin.json 和
# .claude-plugin/marketplace.json 两处保持一致，否则 /plugin upgrade 行为不可预测。
# 本脚本一次改两份，防止漏改。
#
# 用法:
#   ./bump-version.sh 1.1.0
#
# 跑完手动:
#   1. 编辑 CHANGELOG.md 加新版段
#   2. git add -A && git commit -m "chore: release v<NEW_VERSION>"
#   3. git tag v<NEW_VERSION>
#   4. git push && git push --tags

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "用法: $0 <new-version>"
  echo "示例: $0 1.1.0"
  exit 1
fi

NEW_VERSION="$1"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_ROOT"

python3 - "$NEW_VERSION" <<'PYEOF'
"""同步更新 plugin.json 和 marketplace.json 的 version。"""
import json
import sys
from pathlib import Path

new_version = sys.argv[1]

# 1) plugin.json
plugin_path = Path(".claude-plugin/plugin.json")
plugin_data = json.loads(plugin_path.read_text(encoding="utf-8"))
old_plugin = plugin_data["version"]
plugin_data["version"] = new_version
plugin_path.write_text(
    json.dumps(plugin_data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"  plugin.json:      {old_plugin} → {new_version}")

# 2) marketplace.json — 找名字匹配 plugin.json["name"] 的条目
mp_path = Path(".claude-plugin/marketplace.json")
mp_data = json.loads(mp_path.read_text(encoding="utf-8"))
plugin_name = plugin_data["name"]

matched = False
for plugin in mp_data["plugins"]:
    if plugin["name"] == plugin_name:
        old_mp = plugin.get("version", "?")
        plugin["version"] = new_version
        matched = True
        print(f"  marketplace.json: {old_mp} → {new_version}  (plugin '{plugin_name}')")
        break

if not matched:
    print(f"✗ marketplace.json plugins[] 没找到 '{plugin_name}'", file=sys.stderr)
    sys.exit(1)

mp_path.write_text(
    json.dumps(mp_data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PYEOF

echo ""
echo "✓ version 已同步到 $NEW_VERSION"
echo ""
echo "下一步："
echo "  1. 编辑 CHANGELOG.md 加 [$NEW_VERSION] 段"
echo "  2. git add -A && git commit -m \"chore: release v$NEW_VERSION\""
echo "  3. git tag v$NEW_VERSION"
echo "  4. git push && git push --tags"
