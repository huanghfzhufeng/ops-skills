#!/usr/bin/env bash
# install.command — macOS 双击安装 ops-skills（最小白玩法）
#
# 朋友怎么用：
#   1. 在 GitHub 上下载这个文件（点 install.command → 右上角下载按钮 ⬇）
#   2. 在「下载」文件夹里找到 install.command
#   3. 右键 → 打开（第一次会问"无法验证开发者"→ 点「打开」）
#   4. 终端窗口自动弹出来，自动开始装
#   5. 看到 ✅ 装好了！ → 完全退出 Claude Desktop App（⌘+Q）再打开

set -e
cd "$(dirname "$0")"

clear
cat <<'BANNER'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                 ops-skills 安装器

   美区 TikTok 矩阵运营 Claude 工具集
   两个工具：us-trend-scout + xcmo-mobile
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

us-trend-scout — 每天自动抓美区 TikTok 热点
                 + 配 26 数字角色出创意

xcmo-mobile    — 按邮箱+日期拉 xcmo 视频
                 + 起本地服务 + 手机扫码看
                 + 一键复制文案标签

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

按 Enter 继续安装，或直接关闭窗口取消...
BANNER

read -r

echo ""
echo "→ Step 1: 下载代码（约 2-5 秒）..."
TMP=$(mktemp -d)
git clone --depth=1 https://github.com/huanghfzhufeng/ops-skills.git "$TMP/repo" >/dev/null 2>&1
echo "  ✓ 下载完成"

echo ""
echo "→ Step 2: 安装 skill 到 ~/.claude/skills/ ..."
mkdir -p "$HOME/.claude/skills"
cp -r "$TMP/repo/skills/"* "$HOME/.claude/skills/"
echo "  ✓ 装好 us-trend-scout"
echo "  ✓ 装好 xcmo-mobile"

echo ""
echo "→ Step 3: 装 Python 依赖（qrcode + pillow，xcmo-mobile 用）..."
if pip3 install --user --break-system-packages --quiet qrcode pillow 2>/dev/null; then
  echo "  ✓ 依赖装好"
else
  echo "  ⚠️  pip3 装失败（可能 Python 未装）"
  echo "     us-trend-scout 不受影响，xcmo-mobile 暂不可用"
  echo "     装 Python: https://www.python.org/downloads/"
fi

echo ""
echo "→ Step 4: 清理临时文件..."
rm -rf "$TMP"
echo "  ✓ 完成"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ 装好了！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "接下来这 2 步必须做："
echo ""
echo "  1. 完全退出 Claude Desktop App（按 ⌘+Q，不是关窗口）"
echo "  2. 重新打开 Claude Desktop App"
echo ""
echo "然后跟 Claude 说这句话试试："
echo ""
echo "    跑一次热点"
echo ""
echo "Claude 会抓美区 TikTok 热点 + 配数字角色给你看选题。"
echo ""
echo "有问题问 huanghfzhufeng@github 或 https://github.com/huanghfzhufeng/ops-skills/issues"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "按 Enter 关闭本窗口..."
read -r
