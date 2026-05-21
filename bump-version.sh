#!/usr/bin/env bash
# bump-version.sh — 同步更新指定 plugin 的 plugin.json + 根 marketplace.json
#
# 多 plugin 架构下，version 必须在两处保持一致：
#   plugins/<plugin>/.claude-plugin/plugin.json::version
#   .claude-plugin/marketplace.json::plugins[name=<plugin>].version
# 漏改任何一处，/plugin upgrade 行为不可预测。本脚本一键改两处。
#
# 用法:
#   ./bump-version.sh <plugin-name> <new-version>
#
# 示例:
#   ./bump-version.sh tiktok-matrix 1.0.1
#
# 跑完手动:
#   1. 编辑 plugins/<plugin>/CHANGELOG.md 加新版段
#   2. git add -A && git commit -m "feat(<plugin>): release v<new-version>"
#   3. git tag <plugin>-v<new-version>
#   4. git push && git push --tags

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "用法: $0 <plugin-name> <new-version>"
  echo "示例: $0 tiktok-matrix 1.0.1"
  echo ""
  echo "当前 marketplace 里的 plugin:"
  python3 -c "
import json
data = json.load(open('.claude-plugin/marketplace.json'))
for p in data['plugins']:
    print(f'  - {p[\"name\"]} (current v{p[\"version\"]})')
"
  exit 1
fi

PLUGIN_NAME="$1"
NEW_VERSION="$2"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_ROOT"

python3 - "$PLUGIN_NAME" "$NEW_VERSION" <<'PYEOF'
"""同步更新指定 plugin 的 plugin.json 和 marketplace.json 条目的 version。"""
import json
import sys
from pathlib import Path

plugin_name = sys.argv[1]
new_version = sys.argv[2]

# 1) marketplace.json 找到目标 plugin
mp_path = Path(".claude-plugin/marketplace.json")
mp_data = json.loads(mp_path.read_text(encoding="utf-8"))

target = None
for p in mp_data["plugins"]:
    if p["name"] == plugin_name:
        target = p
        break

if not target:
    available = [p["name"] for p in mp_data["plugins"]]
    print(f"✗ marketplace.json 没有名为 '{plugin_name}' 的 plugin", file=sys.stderr)
    print(f"  可选: {', '.join(available)}", file=sys.stderr)
    sys.exit(1)

# 2) 通过 source 解析 plugin 物理位置
source = target.get("source", "./")
if source == "./":
    plugin_dir = Path(".")
else:
    plugin_dir = Path(source.lstrip("./"))

plugin_json_path = plugin_dir / ".claude-plugin" / "plugin.json"
if not plugin_json_path.exists():
    print(f"✗ 找不到 plugin.json: {plugin_json_path}", file=sys.stderr)
    sys.exit(1)

# 3) 改 plugin.json
plugin_data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
old_plugin = plugin_data["version"]
plugin_data["version"] = new_version
plugin_json_path.write_text(
    json.dumps(plugin_data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"  {plugin_json_path}: {old_plugin} → {new_version}")

# 4) 改 marketplace.json 里的条目
old_mp = target["version"]
target["version"] = new_version
mp_path.write_text(
    json.dumps(mp_data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"  marketplace.json[{plugin_name}]: {old_mp} → {new_version}")
PYEOF

echo ""
echo "✓ '$PLUGIN_NAME' version 已同步到 $NEW_VERSION"
echo ""
echo "下一步："
echo "  1. 编辑 plugins/$PLUGIN_NAME/CHANGELOG.md 加 [$NEW_VERSION] 段"
echo "  2. git add -A && git commit -m \"feat($PLUGIN_NAME): release v$NEW_VERSION — <一句话>\""
echo "  3. git tag $PLUGIN_NAME-v$NEW_VERSION"
echo "  4. git push && git push --tags"
