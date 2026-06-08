#!/usr/bin/env bash
# tk-template-scout 每日自动推送：抓取 → 渲染 → 推 template 群，全程脚本完成。
#
# 为什么有这个脚本：tk 严格 24h 抓取要 ~14 分钟，原来放在 Claude 定时任务的
# fresh session 里跑完整流程（抓 + 翻译 + 渲染 + 推），太重、经常没跑完整导致漏推。
# 改成脚本一把梭（像 analyzer/sge 的 watch.py），定时任务只需后台启动本脚本即可，
# 不再赌 session 跑完整。代价：用原文标题、无 Claude 仿拍 brief（要 brief 走手动增强）。
#
# 用法（定时任务里）：nohup bash run_daily.sh >/tmp/tk-daily.log 2>&1 &
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULT="/tmp/tk-daily-result.json"
BRIEFING="/tmp/tk-daily-briefing.txt"
log() { echo "[$(date '+%F %T')] $*"; }

log "tk 每日抓取开始（严格 24h, both 双源, ~14 分钟）"
if ! python3 "$SKILL_DIR/scout_strict.py" --keywords "$SKILL_DIR/tk_keywords.yaml" \
     --max-age-hours 24 --source both --top-n 3 > "$RESULT"; then
  log "抓取失败，退出（不推）"; exit 1
fi

python3 "$SKILL_DIR/render_briefing.py" --json "$RESULT" > "$BRIEFING"
if [ ! -s "$BRIEFING" ]; then
  log "渲染结果为空，退出（不推）"; exit 1
fi
log "渲染完成：$(wc -l < "$BRIEFING") 行"

WEBHOOK=$(grep '^feishu_webhook_template:' "$HOME/.config/ops-skills/tk-template-scout.yaml" 2>/dev/null \
          | sed 's/^feishu_webhook_template: *"\(.*\)"$/\1/')
if [ -z "${WEBHOOK:-}" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then
  log "feishu_webhook_template 未配，简报只落地 $BRIEFING，不推送"; exit 0
fi

python3 "$SKILL_DIR/push_feishu_card.py" --briefing "$BRIEFING" --webhook "$WEBHOOK"
log "tk 每日推送完成 → template 群"
