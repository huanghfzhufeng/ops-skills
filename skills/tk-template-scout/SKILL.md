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
3. **（严格 24h 模式才需要）Playwright 已装**：

```bash
pip install -r <skill-dir>/requirements.txt
playwright install chromium
```

约占 200MB 磁盘。MVP 模式不需要。

**想推飞书群**（可选）：

```bash
mkdir -p ~/.config/ops-skills
cat > ~/.config/ops-skills/tk-template-scout.yaml <<'EOF'
feishu_webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
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

## 选择模式

听用户口令决定走哪条：

- **MVP 模式**（默认）：用户说"跑一次 tk 模板"、"TK 模板日推"。走下面 Step 1-8。简报会标注"数据多数命中 7d/all（Google 索引滞后）"。
- **严格 24h 模式**：用户说"跑一次 TK 模板 严格 24h"、"TK 模板严格模式"、"tk 严格 24h"。**跳过** Step 3-5，改走 [严格 24h 模式](#严格-24h-模式) 那一节。Step 1 / 2 / 6 / 7 / 8 仍然一样。

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

### Step 6 - 拼简报

读 `result.json`，按 persona 分组写简报。每个 persona 段：

```
{emoji} {Persona 名} | @{handle}
人设：{persona 的一句话定位}

1. {标题（截断到 50 字）} | {点赞数} | {发布日期}
   {webpage_url}
   模板：{1 句概括拍法套路（机位/转场/钩子）}
   仿拍：{1 句基于此人设的具体改造建议（30 字内，含场景动作）}

2. ...
3. ...
```

**模板和仿拍这两行由 Claude 基于视频标题 + 人设定位生成**，不是从 yt-dlp 来的。

**Persona 顺序**：按赛道分组，组内随机不要按字母（让简报视觉错落）：
1. 穿搭/彩妆/护肤（💄）：Sophie / Ava / Ezra / Riley / Silver / Nari
2. 健康/健身/成分党（💪）：Clara / Leila / Ryan / Max / Avery / Joey
3. 数码/AI 工具（📱）：Mia / Charlotte / Priya / Ro / Spencer
4. 泛娱乐/情绪共鸣（🎭）：Eleanor / Iris / Leo / Caden / Mason / Kai / Jesse / Emma / Jade

### Step 7 - 推飞书（如配置了）

如果 `~/.config/ops-skills/tk-template-scout.yaml` 存在且 `feishu_webhook_url` 不含 `xxxxx`：

简报字符数估算 26 × 350 ≈ 9000 字符，单条飞书 text 消息（30000 上限）能装下。

```bash
WEBHOOK=$(grep '^feishu_webhook_url:' ~/.config/ops-skills/tk-template-scout.yaml | sed 's/^feishu_webhook_url: *"\(.*\)"$/\1/')

python3 -c "
import json, sys
with open('briefing.txt') as f:
    text = f.read()
print(json.dumps({'msg_type': 'text', 'content': {'text': text}}, ensure_ascii=False))
" > briefing.json

curl -sS -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d @briefing.json
```

webhook 返回非 200 → 把 response body dump 给用户，简报继续 dump 对话。

### Step 8 - 输出 + 报告

把整份简报**直接 dump 到对话**。然后简要报告：
- 简报字符数
- 78 路 search 成功率
- yt-dlp 抓取成功 / 失败数
- 多少 persona 命中 24h `fresh` / 多少降级 `7d` / 多少 `all`
- 飞书推送状态码（如配置）

---

## 输出格式（纯文本）

```
TK 模板日推 | 5月22日（周五）

💄 Sophie | @sophie.fits2
人设：西村画廊女孩，纽约 24 岁策展助理

1. 3 tips to creating the quiet luxury aesthetic | 4.53 万赞 | 2024-06-18
   https://www.tiktok.com/@lydiajanetomlinson/video/7381897890278493472
   模板：3 个穿搭 tip 平铺直叙，每个 tip 一个场景切镜
   仿拍：Sophie 拍 "策展女孩 3 个 quiet luxury 单品测评，西村画廊试穿"

2. ...
3. ...

💄 Ava | @ava.glow3
人设：中东系公关大美女，LA 25 岁时尚公关

1. ...
（重复 26 人）

数据说明
全部 78 路 search 成功，yt-dlp 抓取 73/78（5 条失败已跳过）
26 人中 4 人命中 24h fresh，12 人放宽 7d，10 人 all（Google 索引 TikTok 有延迟，要严格 24h 需加 Playwright）
```

赛道 emoji：穿搭 💄 / 健康 💪 / 数码 📱 / 娱乐 🎭

## 文体约束

- 全中文。专有名词（TikTok / quiet luxury / vlog / ootd）保留英文
- **不用 em dash（—）**，用逗号、句号、冒号
- **不用 markdown 格式符号**（不要 `**bold**` / `## header` / `- list`）
- 数字角色名首字母大写（Sophie / Caden），handle 用 `@xxx` 格式
- 点赞数中文化：4.53 万赞、120 万赞，不要 `45.3K likes`
- 视频标题保留原英文（不翻译，以免歪曲），过长截到 50 字符加省略号

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
2. Playwright headless Chrome 抓 `https://www.tiktok.com/tag/<hashtag>`（按时间倒序）
3. 解析每个视频 URL 的 ID，`timestamp = video_id >> 32`（snowflake 高位编码）
4. 硬过滤 timestamp >= now - 24h
5. yt-dlp 给候选 URL 补 like_count / title / uploader
6. 按 like_count 取 Top 3

**单条命令**（替代 MVP 模式的 Step 3-5）：

```bash
python3 "<skill-dir>/scout_strict.py" \
  --keywords "$KEYWORDS" \
  --max-age-hours 24 \
  --top-n 3 \
  --parallel 4 \
  --min-likes-warn 500 \
  > result.json 2> strict.log
```

参数：
- `--parallel 4`：Playwright worker 数（每个复用 1 个 browser context 跑多个 hashtag，避免重复创建）
- `--scrolls 3`：每个 hashtag 页滚动加载次数
- `--retry 2`：单 hashtag 失败重试次数
- `--min-likes-warn 500`：Top1 点赞低于这个值的 persona 会被标 `low_heat_warning: true`，简报里要明示

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

**简报输出特殊规则**（严格 24h 模式专用）：

- 每个 persona 段标题后加一行统计：`候选 12 / 抓取成功 12 / 24h 内最高赞 9.7K`
- `low_heat_warning: true` 的 persona 在最高赞数后加 ⚠️ + "24h 内无爆款，可选不仿"
- 简报末尾"统计"段加：
  - `严格 24h 模式 | Playwright + ID 解码硬过滤`
  - `78/78 hashtag 抓取 + 348/349 元数据补全`
  - `26 人有数据 / 其中 N 人 24h 内热度低`

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
