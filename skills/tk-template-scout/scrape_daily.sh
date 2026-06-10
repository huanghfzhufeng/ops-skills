#!/usr/bin/env bash
# tk 两段式·第一段：只抓取 + 落地数据。不渲染、不翻译、不推送。
#
# 为什么拆两段（v6.2）：v6 把「14 分钟抓取 + Top3 + 翻译 + 推送」塞在一个定时
# Claude session 里，实测连续两天（6/9、6/10）session 没跑满就结束 → 漏推。
# 拆开后：本脚本由 08:30 的定时任务用 nohup 后台启动（session 秒退，shell 继续跑，
# 该机制 run_daily.sh 已验证可行）；09:00 的第二段 session 直接读现成数据做短活
# （Top3 + 翻译 + 渲染 + 推，~6 分钟），不再赌长 session。
#
# 用法（定时任务里）：nohup bash scrape_daily.sh > /dev/null 2>&1 &
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$HOME/.cache/ops-skills"
RESULT="$OUT_DIR/tk-daily-result.json"
LOG="$OUT_DIR/tk-daily-strict.log"
TMP="$RESULT.tmp"

mkdir -p "$OUT_DIR"
echo "[$(date '+%F %T')] scrape start (strict 24h, both, top-n 3)" > "$LOG"

# 原子写：先写 .tmp，成功才 mv 成正式文件，第二段绝不会读到半截 JSON
if python3 "$SKILL_DIR/scout_strict.py" --keywords "$SKILL_DIR/tk_keywords.yaml" \
     --max-age-hours 24 --top-n 3 --source both --parallel 4 --yt-dlp-parallel 4 \
     --min-likes-warn 500 > "$TMP" 2>> "$LOG"; then
  mv "$TMP" "$RESULT"
  echo "[$(date '+%F %T')] scrape ok -> $RESULT ($(wc -c < "$RESULT" | tr -d ' ') bytes)" >> "$LOG"
else
  rm -f "$TMP"
  echo "[$(date '+%F %T')] scrape FAILED (exit != 0), result not updated" >> "$LOG"
  exit 1
fi
