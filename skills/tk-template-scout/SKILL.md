---
name: tk-template-scout
description: 美区 TikTok 每日模板搜索。两种模式：(1) MVP 模式 = WebSearch + yt-dlp，受 Google 索引延迟限制，多数命中 7d/全量；(2) 严格 24h 模式 = Playwright 抓 hashtag 页 + video_id 解码 timestamp 硬过滤，能拿到真过去 24h 内的视频。按 26 个数字角色 × 3 关键词跑，每人按点赞排序取 Top 3，输出"运营选题用"中文简报到对话（有飞书 webhook 也推飞书群）。触发：用户说"TK 模板日推"、"tk 模板"、"tk-template"、"tk-template-scout"、"跑一次 tk 模板"、"跑一次 TK 模板 严格 24h"，或被 /schedule 定时触发。
---

# TK Template Scout

每天给运营产 26 个数字角色的 TikTok 热门模板清单，**便于按人设找参考视频去仿拍**。

数据源：TikTok 官方网页（通过 yt-dlp + 用户浏览器 cookies 抓取，非 hack，等同 Chrome 访问的数据）。

简报**直接 dump 到对话**给运营看；如果用户配了飞书 webhook（复用 us-trend-scout 的 config 路径），同时推送飞书群。

## 首次使用

无需任何配置即可使用。前置：

1. **yt-dlp 已装**：`brew install yt-dlp` 或 `pip install yt-dlp`
2. **Chrome 浏览器登录过 TikTok**：`https://www.tiktok.com` 已**真实登录**任意账号（cookies 必须含 sessionid，不只是 ttwid）
3. **（严格 24h 模式才需要）patchright + Playwright 已装**：

```bash
pip install -r <skill-dir>/requirements.txt
playwright install chromium
python3 -m patchright install chromium
```

约占 200-300MB 磁盘。MVP 模式不需要。

> **为什么用 patchright**（v5.1 起）：vanilla playwright headless chromium 会被 TikTok 反爬识别为机器人，弹滑块 CAPTCHA 导致所有 hashtag/search 页拿不到视频列表。patchright 是 playwright 的反检测 fork，补了 ~50 处指纹漏洞，能正常过 TikTok search 路径。scout_strict.py 自动优先用 patchright，ImportError 时 fallback 到 vanilla playwright（不带反检测能力）。

**想推飞书群**（可选）：

```bash
mkdir -p ~/.config/ops-skills
cat > ~/.config/ops-skills/tk-template-scout.yaml <<'EOF'
feishu_webhook_trend: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"      # us-trend-scout 推热点群
feishu_webhook_template: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"   # tk-template-scout 推模板群（本 skill 实际读这个）
EOF
```

没填或填了占位符就跳过推送，简报只 dump 到对话。

**想自定义 26 个角色或关键词**（可选）：

```bash
cp <skill-dir>/tk_keywords.yaml ~/.config/ops-skills/tk-keywords.yaml
$EDITOR ~/.config/ops-skills/tk-keywords.yaml

# 人设定义共用 us-trend-scout 的（赛道映射 / 人设描述）
cp <us-trend-scout-dir>/personas.yaml ~/.config/ops-skills/personas.yaml
$EDITOR ~/.config/ops-skills/personas.yaml
```

跨 plugin 升级保留。

## v6 默认流程（严格 24h + 全平台 Top3 挑战 + 26 角色，可靠版）

**用户说"跑一次 TK 模板" → 默认走这个流程**。两块缺一不可，**质量第一、绝不空推**：
① 【全平台热门挑战 Top 3】放最顶部，运营最看重（Claude 创意判断 + 脚本验证样本）
② 【26 个数字角色 24h Top 模板】脚本抓取 + Claude 翻译

```
Step A: 后台启动 scout_strict.py 抓 26 人 × 24h（both 双源，~14 分钟）
        —— 必须【后台跑 + 轮询】，绝不前台 wait（前台 Bash 600 秒被杀 = 漏推根因）
Step B: 等抓取的同时，Claude WebSearch 找【补充候选】（纯格式类，scout 关键词覆盖不到的）
        —— 只搜不抓 TikTok，别抢限流；WebSearch 只当补充，必须过 D 的验证 + 赞地板
Step C: 轮询等 scout 完成（pgrep -f scout_strict.py + $RESULT 是否合法 JSON）
Step D: scout 完成后 → derive_challenges.py 数据驱动出主候选（跨 persona 高频高赞 hashtag）
        + 合并 WebSearch 补充候选 → grab_viral_challenges.py 验真样本(7 天内)
        → 赞地板 ≥1万 闸门 → 按借鉴价值挑 Top3 + Claude 翻译 26 角色 + 写回 viral_challenges
Step E: render_briefing.py 渲染（--min-likes 500 滤 26 角色噪声 + Top3 透明标注）→ push_feishu_card.py 推飞书
```

**可靠性关键（v6 就是修这个）**：14 分钟抓取**后台跑 + 轮询**，不要用前台 Bash 死等——
前台 Bash 最多 600 秒就被杀，scout 没跑完简报就空了，这是以前定时任务漏推的根因。

**Top3 来源可靠性（v6.1）**：Top3 主候选来自 **scout 真抓数据**（`derive_challenges.py` 跨 persona
聚合高频高赞 hashtag，客观可证实，不靠 WebSearch 猜——如 #monacogp 跨 2 角色聚合 50 万赞自然冒出）；
WebSearch 只出补充候选（纯格式类）。两路都必须过 **grab 验证 7 天内真样本 + 赞地板 ≥1万**，
render 把每条样本赞 / 抓取时间 / 来源透明标出让运营可核。解决了「WebSearch 当源头不稳 + 猜 hashtag 漏热点」。

**绝不空推 · 降级链**：
- Top3 一条没验证到 → 留空，仍推 26 角色（render 自动跳过 Top3 块）
- 翻译失败/来不及 → 原文标题兜底（render 的 `title_cn or title`），仍推
- 抓取超时/失败但 Top3 有货 → 只推 Top3 + 标注「26 角色稍后补」
- 全失败 → 推一条「抓取失败，查 cookies / 代理」报警，不静默

**定时任务（v6.2 起两段式）**：v6 把整条流程塞一个定时 Claude session，实测连续两天
（6/9、6/10）session 没跑满就结束 → 漏推。v6.2 拆成两个定时任务根治：
- **第一段 `tk-scrape-daily`（08:30）**：session 只后台 `nohup` 启动 `scrape_daily.sh` 即退出；
  脚本自己跑完 14 分钟抓取，数据**原子写入** `~/.cache/ops-skills/tk-daily-result.json`。
- **第二段 `tk-template-scout-daily`（09:00）**：读第一段现成数据 + Top3 + 翻译 + 渲染
  （--min-likes 500）+ 推正式 template 群，全程 ~6 分钟短活，一定跑得完。
  失败报警走测试群。runbook 见 `~/.claude/scheduled-tasks/tk-template-scout-daily/SKILL.md`。

上面 Step A-E 的单 session 流程仍适用于**手动**「跑一次 tk 模板」（交互 session 不会被掐）。

**旧 MVP 模式 / v4.6.0 Top1 单条**：废弃，代码保留备用，默认不走。

## 选择模式（旧文档保留作历史）

听用户口令决定走哪条：

- **MVP 模式**（旧 v4.2，废弃）：仅历史代码保留
- **v4.6.0 默认**：跑严格 24h + Top 1 ≤15s + 全平台挑战块

## 工作流（MVP 模式，按顺序执行）

### Step 1 - 加载 yaml

按以下优先级加载两份 yaml：

**personas.yaml**（人设定位 / 赛道映射，复用 us-trend-scout）：
1. 优先 `~/.config/ops-skills/personas.yaml`
2. fallback `<us-trend-scout-skill-dir>/personas.yaml`

**tk_keywords.yaml**（每人 3 个 TikTok 搜索关键词）：
1. 优先 `~/.config/ops-skills/tk-keywords.yaml`
2. fallback `<this-skill-dir>/tk_keywords.yaml`

```bash
USER_PERSONAS="$HOME/.config/ops-skills/personas.yaml"
USER_KEYWORDS="$HOME/.config/ops-skills/tk-keywords.yaml"
SKILL_DIR="<this-skill-dir>"
US_TREND_DIR="<us-trend-scout-skill-dir>"

[ -f "$USER_PERSONAS" ] && PERSONAS="$USER_PERSONAS" || PERSONAS="$US_TREND_DIR/personas.yaml"
[ -f "$USER_KEYWORDS" ] && KEYWORDS="$USER_KEYWORDS" || KEYWORDS="$SKILL_DIR/tk_keywords.yaml"
```

### Step 2 - 算日期

用 Bash `date` 拿当前北京时间。美东日期 = 北京日期 - 1。简报日期格式 `5月22日（周五）`。

### Step 3 - 并行 WebSearch 拿 URL

对 **26 人 × 3 关键词 = 78 个 query** 并行跑 WebSearch。

**分批策略**：Claude 单 message 最多稳定支持约 13 个并行 tool 调用，分 **6 批 × 13 个** 跑（顺序提交，每批内并行）。

**query 模板**：
```
site:tiktok.com {keyword}
```

例如 sophie 三个关键词：
- `site:tiktok.com old money outfit`
- `site:tiktok.com quiet luxury`
- `site:tiktok.com skincare routine heiress`

### Step 4 - 抽取 video URL

每个 WebSearch 结果里筛符合下面正则的 URL：

```
^https://www\.tiktok\.com/@[\w._-]+/(video|photo)/\d+
```

- 保留：`/video/` 和 `/photo/` 单帖 URL
- 丢弃：`/discover/`、`/tag/`、`/search`、`shop.tiktok.com` 等聚合或商城页

收集成 `urls.txt`，**每行格式 `persona_key:url`**。

### Step 5 - 跑 scout.py 抓元数据

```bash
python3 "<skill-dir>/scout.py" --urls-file urls.txt --max-age-hours 24 --top-n 3 > result.json
```

scout.py 用 yt-dlp + `--cookies-from-browser chrome` 抓每个 URL 的真实点赞 / 发布时间 / 文案。

**降级规则**（脚本内置）：
- 24h 内 ≥ 3 条 → `age_tag: "fresh"`
- 24h 内 < 3 条 → 放宽到 7 天，`age_tag: "7d"`
- 7 天内仍 < 3 条 → 全量取最高赞，`age_tag: "all"`

**第一次跑失败**（Chrome cookies 报错 / 单视频抓不到）：
- 提示用户去 `https://www.tiktok.com` 登录任意账号刷新 cookies
- 复跑 scout.py 一次再失败 → 不阻塞，标记该 persona 数据为空，继续后续

### Step 0 - 抓全平台热门挑战 Top 3（v4.6.0 新增，必做）

**作用 >>> 细分赛道模板**。这是简报最重要的板块，放在最顶部。

挑战 = 跨赛道传播的 viral phenomenon，**有具体玩法 / 文化梗 / 名字**（如冰桶挑战、韩国棒球应援）。不是简单的格式或 sound trend。

**步骤**：

1. Claude 并行 3 路 WebSearch（同 message 一次发，**v4.6.0 中性化 query，不预设答案**）：
   - `TikTok viral content cross-niche this week {date} US 2026`
   - `TikTok cross-niche participatory format {date} platform-wide`
   - `TikTok hottest cultural moment {date} all genres participation`

   **核心锚定**：「**cross-niche participatory**」（跨圈层可参与）。
   **不要**在 query 里 hardcode 挑战类型（dance/non-dance/format/meme/skit/POV/ritual）—— 这都是 hardcode 偏好（包括"非"什么），都会切碎信号空间。让 viral 程度 + 跨圈层 + 仿拍可行性自己说话。

2. Claude 从结果里筛 Top 3 具体可证实的挑战。**筛选标准**：
   - ✅ 保留：有具体名字 + 有玩法 + 跨赛道传播
   - ❌ 排除：单个赛道的 niche trend、不具名的 micro-format、个人 viral 视频

3. **必须抓样本视频验证时间窗**（v4.6.0 防回声室关键）：
   - 对每个候选挑战，去 `https://www.tiktok.com/tag/<hashtag>` 抓真实样本
   - **样本视频发布时间必须在过去 7 天内**（不要拿 2024 年的爆款充数）
   - 如果某个挑战找不到 7 天内的真样本 → 丢弃换下一个候选
   - 这一步用 yt-dlp `--dump-json` 拿 timestamp 验证

3. 对每个挑战，调 scout_strict.py 抓 1 个样本视频（**挑战样本不限时长**，看格式不是看仿拍）：
   ```bash
   python3 scout_strict.py --keywords <(echo "ch1: { keywords: ['<挑战 hashtag 名>'] }") \
     --source both --top-n 1 --tight-max 9999 --max-age-hours 168 \
     > /tmp/challenge-sample-1.json
   ```
   `--tight-max 9999` 关闭时长过滤（挑战样本不看时长只看格式）；`--max-age-hours 168` 放宽到 1 周（挑战样本不要求 24h 内）

4. 把 3 个挑战的元数据写到 `result.json` 的 `viral_challenges` 字段：
   ```json
   {
     "viral_challenges": [
       {
         "name": "Hold the moan（憋反应对比格式）",
         "desc": "正式场合表情 vs 私下情绪反应，1-2 秒强对比",
         "sample_url": "https://www.tiktok.com/@x/video/...",
         "sample_likes": 500000,
         "fanpai_brief": "26 人都能蹭，建议 Iris / Caden / Ezra 先拍"
       },
       ...（共 3 条）
     ],
     "personas": { ... }
   }
   ```

5. render_briefing.py 自动渲染到简报顶部"🔥 全平台热门挑战 Top 3"段。

**格式约束**：
- `name`：英文原名（中文括号说明），如 `"Hold the moan（憋反应对比格式）"`
- `desc`：1-2 句玩法描述，让运营 1 秒看懂怎么玩
- `sample_url`：1 个真实样本视频 URL（看到格式即可，不强求 24h 内）
- `sample_likes`：样本视频的点赞数（用于读者判断热度）
- `fanpai_brief`：1 句仿拍建议（适配的 persona + 简单 brief）

### Step 6 - Claude 翻译 + 生成仿拍 brief（v4.5.0 新增，必做）

**v4.5.0 起简报必须中文化 + 含仿拍建议**。这一步由 **Claude 主线**完成（不靠
外部 API），按 `translate_prompt.md` 的规则**一次性**翻译 + 生成。

```bash
# 1. 读 prompt 规则
cat "<skill-dir>/translate_prompt.md"

# 2. 读 scout 数据
cat result.json

# 3. 读 personas（拿每人人设描述）
cat "<us-trend-scout-skill-dir>/personas.yaml"
```

Claude 按 prompt 规则，对每条 video 生成两个字段并写回 JSON：

- `title_cn`：20-40 字中文化标题（保留专有名词英文 / 标视频形式 / 用「」标金句）
- `fanpai_brief`：30 字内的仿拍 brief（句首 `<Persona> 拍...` + 具体场景 + 动作 + 钩子）

输出 `translated.json`（保留所有原字段 + 加这两个新字段）。

**重要约束**：
- ❌ 不要分多次小 API 调用（浪费 context）
- ❌ 不要漏 video（必须每条 video 都有 title_cn 和 fanpai_brief）
- ❌ 不要重新解释 persona 人设（briefing 已有 handle，brief 句首 `<Persona> 拍...` 即可）
- ✅ 严格按 translate_prompt.md 里的例子风格

### Step 6.5 - 渲染简报（调 render_briefing.py，不要 Claude 即兴拼）

```bash
python3 "<skill-dir>/render_briefing.py" --json translated.json > briefing.txt
```

`render_briefing.py` 优先用 `title_cn`（v4.5.0 新增），有 `fanpai_brief` 时在
视频条目后加一行 `→ <brief>`。格式 100% 代码固化，Claude **不要二次加工**。

### Step 7 - 推飞书（v4.5.0 双 webhook）

`~/.config/ops-skills/tk-template-scout.yaml` 存两个独立 webhook：

```yaml
feishu_webhook_trend: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
feishu_webhook_template: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
```

tk-template-scout 推 `feishu_webhook_template`（v4.8.0 改用 `push_feishu_card.py`，富文本卡片，
能渲染 `**加粗**` / 链接 / emoji 标题）：

```bash
WEBHOOK=$(grep '^feishu_webhook_template:' ~/.config/ops-skills/tk-template-scout.yaml | sed 's/^feishu_webhook_template: *"\(.*\)"$/\1/')

if [ -z "$WEBHOOK" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then
  echo "skip 飞书推送：webhook 未配置"
else
  python3 <skill-dir>/push_feishu_card.py \
    --briefing briefing.txt \
    --webhook "$WEBHOOK"
fi
```

`push_feishu_card.py` 行为：
- 简报第一行 → 卡片 header title（自动选配色，「模板」→ 浅蓝、「热点/趋势」→ 蓝）
- 其余 → markdown body（飞书 markdown 元素，支持 `**bold**` / `[link](url)`）
- 返回非 `code:0` → 退出码 1 + dump 飞书响应到 stderr

us-trend-scout 用 `feishu_webhook_trend` 同套路推（见 us-trend-scout/SKILL.md）。

### Step 8 - 输出 + 报告

把 `briefing.txt` **直接 dump 到对话**（render_briefing.py 已固化格式，
**不要二次加工**）。然后基于 `result.json` 的 `stats` 段简要报告：

- 简报字符数（`wc -c briefing.txt`）
- 78 路抓取成功率 / 多少 errors
- yt-dlp 元数据补全率
- `personas_with_data / 26`（多少人有数据）
- `personas_low_heat`（多少人 24h 内 Top1 < 500 赞）
- 最大爆款 sample（如 "Mia 23.6 万 / working mom"）
- 飞书推送状态码（如配置）

---

## 输出格式（render_briefing.py 固化）

**重要**：简报格式**不靠 Claude 即兴拼**，由 `render_briefing.py` 代码固化。
原因：实测靠 Claude 读 SKILL.md 后手工拼简报会反复偏离用户原 spec（emoji
分组、统计行、⚠️ 标记等装饰被自动加上）。代码固化后 100% 一致。

**严格按用户原 spec 输出**：

```
TK模板日推 | 5月24日（周日）

Sophie (@sophie.fits2)

<视频标题> | <点赞> | <URL>
<视频标题> | <点赞> | <URL>
<视频标题> | <点赞> | <URL>

Ava (@ava.glow3)

(24h 内 0 命中)

Ezra (@ezra.style2)

<视频标题> | <点赞> | <URL>
...
（26 人按固定顺序展开，每人 3 条；24h 内无命中显示「(24h 内 0 命中)」）
```

格式约束（render_briefing.py 内置，不需要 Claude 维护）：
- Persona 名格式：`Name (@handle)` （不是 `Name | @handle`，不是 `💄 Name`）
- 视频条目格式：`标题 | 点赞 | URL` 三段式（无 1./2./3. 序号、无日期、无 @uploader 单独行、无"模板""仿拍"建议行）
- 点赞中文化：`1.2万赞 / 3.5K赞 / 234赞`
- Persona 顺序固定 26 人（见 render_briefing.py 的 DISPLAY_ORDER）
- 0 命中 persona 仍显示 segment 标题 + 「(24h 内 0 命中)」
- 无 emoji 分组、无统计行、无 ⚠️ low_heat 标、无"数据说明"段、无"人设：xxx"

**Claude 在 Step 7 调 render_briefing.py 直接拿成品输出，不要二次加工**。

## /schedule 自动化

每天北京 9:00 自动跑：

```
/schedule create "0 1 * * *" "run skill tk-template-scout"
```

UTC 01:00 = 北京 09:00（美东前一天晚上 8-9 点）。

## 失败处理

- **WebSearch 单路失败**：跳过那个关键词的 URL 收集，记入"成功率"
- **yt-dlp 全军覆没**（说明 Chrome cookies 失效）：报错 + 提示登录 `tiktok.com` 刷新 cookies
- **yt-dlp 单条失败**：跳过该 URL，不阻塞
- **yaml 缺失**：明确报错路径 + 提示
- **24h 内不足 3 条**：自动降级到 7d → all，简报数据说明里标注

## 严格 24h 模式

**何时用**：用户口令含 "严格 24h" / "strict 24h" / "真 24h" 时启用。MVP 模式因 Google 索引滞后通常拿不到 24h 内视频，本模式直接抓 TikTok 网页拿真实当天数据。

**技术路径**：
1. 关键词 → hashtag（空格删掉小写：`old money outfit` → `oldmoneyoutfit`）
2. patchright headless chromium（v5.1 起）抓 search URL `tiktok.com/search/video?q=<keyword>&publish_time=1&sort_type=2`（v4.8 默认 source=search；hashtag 路径仍被 TikTok 反爬挡）
3. 解析每个视频 URL 的 ID，`timestamp = video_id >> 32`（snowflake 高位编码）
4. 硬过滤 timestamp >= now - 24h
5. yt-dlp 给候选 URL 补 like_count / title / uploader
6. tier fallback（v5.1 起）：
   - **tier 1（tight）**：≤15s + 仅竖版（`height > width`）
   - **tier 2（relaxed，0 命中时启用）**：≤30s + 横竖不限
7. 按 like_count 取 Top N（默认 1）

**v6 单条命令**（默认 Top 3 + ≤15s 硬过滤；**长跑务必后台 + 轮询，别前台死等**——前台 Bash 600 秒会被杀）：

```bash
# 后台跑：末尾 & + nohup，然后轮询 result.json 变成合法 JSON 即抓完（中途为空）
nohup python3 "<skill-dir>/scout_strict.py" \
  --keywords "$KEYWORDS" \
  --max-age-hours 24 \
  --top-n 3 \
  --source both \
  --parallel 4 \
  --yt-dlp-parallel 4 \
  --min-likes-warn 500 \
  > result.json 2> strict.log &
```

参数：
- `--top-n 1`（v4.6.0 默认）：每 persona 只取最热 1 条
- `--source both`（v5.3 默认，原为 search）：search + hashtag 双源。search 源单独跑偶尔抽风（某些词返回 0 raw），hashtag 源补上漏抓，覆盖率从 ~12 提到 ~18-20。代价：抓取翻倍（~14 分钟）
- 时长用默认 `--tight-max 15` / `--relaxed-max 30`（tier 1 ≤15s，0 命中兜底 ≤30s）。**注：不存在 `--max-duration` 参数，旧文档写错了，加了会 exit 2**
- `--parallel 4`：Playwright worker 数（每个复用 1 个 browser context）
- `--yt-dlp-parallel 4`（v5.3 从 6 降到 4）：yt-dlp 并发。配合 `fetch_metadata_for_all` 的抗限流重试（失败率 ≥40% 判定限流 → sleep 后只重试失败的，最多 2 轮），避免 both 双源抓太多触发 TikTok 限流、元数据整批全挂（v5.2 踩过：63 候选 yt-dlp 全 fail、personas_with_data=0）
- `--scrolls 3`：每页滚动加载次数（**别调高，scrolls 6 + both 实测会触发限流**）
- `--retry 2`：单页失败重试次数
- `--min-likes-warn 500`：Top1 点赞低于这个值的 persona 会被标 `low_heat_warning: true`

脚本会自动从 Chrome 导 cookies 到 `/tmp/tiktok-cookies.txt`，如果 cookies 已存在则直接复用。

**输出 JSON 结构**：

```json
{
  "mode": "strict_24h_playwright",
  "stats": {
    "total_jobs": 78,
    "candidates_total": 349,
    "metadata_ok": 348,
    "personas_with_data": 26,
    "personas_low_heat": 4
  },
  "personas": {
    "sophie": {
      "videos": [{"url": "...", "title": "...", "like_count": 9700, "timestamp": 1779....}, ...],
      "candidates_total": 12,
      "fetched_count": 12,
      "max_likes": 9700,
      "low_heat_warning": false
    },
    ...
  }
}
```

**简报输出**：由 `render_briefing.py` 固化（不在 SKILL.md 描述格式细节）：

```bash
python3 "<skill-dir>/render_briefing.py" --json result.json
```

或用管道：

```bash
python3 "<skill-dir>/scout_strict.py" --keywords "$KEYWORDS" --source search \
  | python3 "<skill-dir>/render_briefing.py"
```

render_briefing.py 自动按用户原 spec 渲染（见上面"输出格式"段）。
**Claude 不要二次加工**——拿到输出直接 dump 对话 + 推飞书。

JSON 里的 `low_heat_warning` / `candidates_by_source` / `stats` 等字段**用于
跑完后单独的报告**（"X/26 人有数据、Y 人 0 命中、最大爆款 Mia 23.6 万"），
**不入简报正文**。

**关键限制（要老实告诉用户的）**：

- ID 解码假设 `timestamp = video_id >> 32` 没二次验证。万一 TikTok 改 ID 格式会静默错。
- 没有 cross-persona dedup，同一爆款视频可能同时出现在多个 persona 的 Top 3 里。
- 关键词 → hashtag 映射粗暴，5+ 词的关键词（如 `skincare routine heiress`）经常 0 命中（因 TikTok 创作者真实 hashtag 短得多）。

## 数据时效说明（MVP 模式）

MVP 模式用 WebSearch 借 Google 索引拿 URL，**Google 索引 TikTok 视频比发布晚几天到几周**，所以"过去 24h 内"硬约束往往无法满足，多数会降级到 7d 或全量高赞。这对"运营找模板做选题"够用（"哪个模板火过、值得仿拍"），但不适合"实时追当天热度"。

要严格 24h 实时 → 用上面的 [严格 24h 模式](#严格-24h-模式)。

## 与 us-trend-scout 的区别

- **us-trend-scout**：跨平台 6 路热点搜索（健康/美妆/健身/科技 + 平台格式 + 文化情绪），筛 5-8 条**人类筛过的热点话题**配人设
- **tk-template-scout**（本 skill）：26 人 × 3 词的**机器抓取真实 TikTok 视频 URL + 点赞数**，每人 Top 3 作模板参考

两者互补：trend-scout 给"今天该聊什么话题"，template-scout 给"按这个话题该看哪些样板视频去仿拍"。
