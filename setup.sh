#!/usr/bin/env bash
# ops-skills 一键安装脚本
#
# 用法：
#   bash setup.sh
#
# 平台支持：
#   - macOS（Apple Silicon / Intel）：完全支持
#   - Linux：部分支持（Chrome cookies 路径需要 Chrome 已装在标准位置）
#   - Windows：未测试，建议用 WSL2 跑 Linux 模式
#
# 这个脚本会：
#   1. 检测平台 / Python / Chrome 是否就绪
#   2. 装 yt-dlp（Homebrew or pip）
#   3. 装 Python 包：qrcode pillow PyYAML playwright playwright-stealth
#   4. 装 Playwright chromium（~200MB 一次性下载）
#   5. 引导你从 Chrome 导出 TikTok cookies 到 /tmp/tiktok-cookies.txt
#
# 跑完后你就能用 Claude 跑「跑一次 TK 模板」/「跑一次热点」等口令。

set -euo pipefail

# ─────────────────────────────────────────────────────────
# 颜色 + 工具
# ─────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠️${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }
step() { echo -e "\n${BLUE}→${NC} $*"; }

# ─────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ops-skills 一键安装"
echo "════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────
# 1. 平台检测
# ─────────────────────────────────────────────────────────

step "1/6 检测平台..."
OS="$(uname -s)"
case "$OS" in
  Darwin)
    PLATFORM=macos
    ok "macOS 平台支持完整"
    ;;
  Linux)
    PLATFORM=linux
    warn "Linux 部分支持。Chrome cookies 解密可能需要手动指定 --cookies-from-browser <path>。"
    ;;
  *)
    err "不支持的平台: $OS。仅支持 macOS / Linux（Windows 请用 WSL2）。"
    exit 1
    ;;
esac

# ─────────────────────────────────────────────────────────
# 2. Python 检测
# ─────────────────────────────────────────────────────────

step "2/6 检测 Python..."
if ! command -v python3 &> /dev/null; then
  err "缺 python3。请先装 Python 3.10+：https://www.python.org/downloads/"
  exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  err "Python 版本太旧（当前 $PY_VER）。需要 3.10+。"
  exit 1
fi
ok "Python: $PY_VER"

# ─────────────────────────────────────────────────────────
# 3. Chrome 检测
# ─────────────────────────────────────────────────────────

step "3/6 检测 Chrome..."
if [ "$PLATFORM" = "macos" ]; then
  if [ ! -d "/Applications/Google Chrome.app" ]; then
    err "Chrome 未装在 /Applications/Google Chrome.app。请先装 Chrome：https://www.google.com/chrome/"
    exit 1
  fi
  ok "Chrome 已装"
else
  if ! command -v google-chrome &> /dev/null && ! command -v chromium &> /dev/null; then
    warn "未检测到 google-chrome / chromium。tk-template-scout 严格 24h 模式需要 Chrome 真登录 tiktok.com。"
  else
    ok "Chrome / Chromium 已装"
  fi
fi

# ─────────────────────────────────────────────────────────
# 4. yt-dlp
# ─────────────────────────────────────────────────────────

step "4/6 装 yt-dlp..."
if command -v yt-dlp &> /dev/null; then
  ok "yt-dlp 已装: $(yt-dlp --version 2>&1 | head -1)"
else
  if [ "$PLATFORM" = "macos" ] && command -v brew &> /dev/null; then
    brew install yt-dlp
  else
    pip3 install --user --break-system-packages yt-dlp
  fi
  if command -v yt-dlp &> /dev/null; then
    ok "yt-dlp 装好: $(yt-dlp --version 2>&1 | head -1)"
  else
    err "yt-dlp 装失败。手动跑：pip3 install --user yt-dlp"
    exit 1
  fi
fi

# ─────────────────────────────────────────────────────────
# 5. Python 包
# ─────────────────────────────────────────────────────────

step "5/6 装 Python 依赖（qrcode pillow PyYAML playwright playwright-stealth）..."
pip3 install --user --break-system-packages --quiet \
  qrcode pillow PyYAML playwright playwright-stealth 2>&1 | tail -3 || {
  warn "pip 装包有错，重试不带 --quiet 看具体错..."
  pip3 install --user --break-system-packages \
    qrcode pillow PyYAML playwright playwright-stealth
}
ok "Python 包装好"

# ─────────────────────────────────────────────────────────
# 6. Playwright chromium（最大一项）
# ─────────────────────────────────────────────────────────

step "6/6 装 Playwright chromium（约 200MB，1-2 分钟）..."

# 找 playwright 可执行文件
PLAYWRIGHT_BIN=""
if command -v playwright &> /dev/null; then
  PLAYWRIGHT_BIN="playwright"
else
  USER_BIN="$(python3 -c 'import site; print(site.USER_BASE)')/bin"
  if [ -x "$USER_BIN/playwright" ]; then
    PLAYWRIGHT_BIN="$USER_BIN/playwright"
  fi
fi

if [ -n "$PLAYWRIGHT_BIN" ]; then
  "$PLAYWRIGHT_BIN" install chromium 2>&1 | tail -5 || {
    warn "playwright install 出错，尝试 python -m..."
    python3 -m playwright install chromium
  }
else
  python3 -m playwright install chromium
fi
ok "Playwright chromium 装好"

# ─────────────────────────────────────────────────────────
# Cookies 引导
# ─────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  最后一步：导出 TikTok cookies"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "tk-template-scout 严格 24h 模式需要你 Chrome 真登录 TikTok 后导出 cookies。"
echo ""
echo "请按顺序做："
echo "  1. 打开 Chrome 浏览器"
echo "  2. 访问 https://www.tiktok.com"
echo "  3. 用任意 TikTok 账号登录（建议美区账号匹配运营目标）"
echo "  4. 登录后**保持 Chrome 打开**"
echo "  5. 回到这里按回车继续"
echo ""
read -p "登录完了按回车继续（Ctrl+C 退出）..."

step "导出 cookies 到 /tmp/tiktok-cookies.txt..."
yt-dlp --cookies-from-browser chrome \
       --cookies /tmp/tiktok-cookies.txt \
       --skip-download \
       --no-warnings \
       --quiet \
       'https://www.tiktok.com/@tiktok' 2>&1 | tail -3 || true

if [ ! -f /tmp/tiktok-cookies.txt ]; then
  err "Cookies 文件没生成。检查 Chrome 是否真登录了 tiktok.com。"
  exit 2
fi

COOKIE_COUNT=$(wc -l < /tmp/tiktok-cookies.txt)
if grep -qE '^\.tiktok\.com\s+.*\s+sessionid\s' /tmp/tiktok-cookies.txt 2>/dev/null \
   || grep -qE '^\.www\.tiktok\.com\s+.*\s+sessionid\s' /tmp/tiktok-cookies.txt 2>/dev/null \
   || awk -F'\t' '$1 ~ /tiktok\.com/ && $6 == "sessionid"' /tmp/tiktok-cookies.txt | grep -q .; then
  ok "Cookies 导出成功，包含 tiktok.com sessionid（真登录）"
  ok "Cookies 文件：/tmp/tiktok-cookies.txt（$COOKIE_COUNT 行）"
else
  warn "Cookies 导出了但**没找到 tiktok.com sessionid**。"
  warn "你的 Chrome 可能只是浏览过 TikTok，没有真登录。"
  warn ""
  warn "排查："
  warn "  1. 在 Chrome 打开 https://www.tiktok.com 确认头像在右上角（= 登录态）"
  warn "  2. 如果没登录态：在 Chrome 里完成登录"
  warn "  3. 跑：rm /tmp/tiktok-cookies.txt && bash setup.sh 重试"
  exit 3
fi

# ─────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ 安装完成"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "下一步可以用了："
echo ""
echo "  方式 A（推荐）：跟 Claude 说"
echo "    跑一次 TK 模板"
echo "    跑一次热点"
echo "    下载 <你邮箱> <日期> 的内容"
echo ""
echo "  方式 B：直接命令行"
echo "    python3 skills/tk-template-scout/scout_strict.py \\"
echo "      --keywords skills/tk-template-scout/tk_keywords.yaml \\"
echo "      | python3 skills/tk-template-scout/render_briefing.py"
echo ""
echo "Cookies 过期了（一般 7-30 天）→ 在 Chrome 重新登录 TikTok，然后："
echo "    rm /tmp/tiktok-cookies.txt && bash setup.sh"
echo ""
