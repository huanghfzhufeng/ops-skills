---
name: us-trend-scout
description: 美区 24h 真热点抓取 + 26 数字角色创意配对。v5.3 改进：Reddit 封了 .json 端点（一律 403），scout_reddit.py 改走 RSS（/top/.rss?t=day，零配置任何 UA 可达，无 ups/comments，热度用 feed 内 rank 表达）+ 并发降到 3 加重试防限流。拉 16 个精选 sub（含 r/OutOfTheLoop 文化引爆点金矿 + 美妆/健康/科技/影视）+ Google Trends 侧路 cross-check + Claude 端 WebSearch enrichment + 3 yes 定性判断 + 7 天跨天去重 + 涌现式输出。卢雨悦每天必用。触发：用户说"热点日报"、"美区热点"、"us trend"、"trend scout"、"跑一次热点"，或被 /schedule 定时触发。
---

# US Trend Scout

抓美区 24h 真热点（事件型，非慢趋势）+ 26 数字角色创意配对，作为运营选题灵感。每天北京时间 9:00 自动跑（= 美东前一天晚上 8-9 点）。

简报**直接 dump 到对话**给运营看，同时推送飞书（如配置 webhook）。

## v5.0 设计原则（critical）

四条原则：

1. **24h 硬窗口** — 脚本层用 Reddit RSS `t=day` 原生过滤 + `published` 时间戳二次校验；超 24h 任何形式 drop。不靠 query 文本提示。
2. **质量第一 → 宁缺勿滥** — 不为完成而完成。今天涌现几条出几条，**禁止凑数**。不达标赛道留空。
3. **跨天去重** — 7 天指纹库，重复热点 drop（保持每天新鲜）。
4. **TikTok 外的跨平台热点** — 跟 tk-template-scout 错位。TikTok 平台内热点由那个 skill 接管，本 skill 专补 Reddit/Google Trends 等 TikTok 外冒头但即将蔓延的事件。

## 信源（v5.0 重构）

**第一层（scout_reddit.py 脚本，v5.3 走 RSS）**：
- Reddit 16 个精选 sub（每 sub `/top/.rss?t=day` 拉 25 条，全局按 rank 取前 120）：
  - 核心：r/OutOfTheLoop（文化引爆点金矿，自带"为什么 X 爆了"解释）
  - 美妆：r/AsianBeauty / r/Sephora / r/30PlusSkinCare
  - 时尚：r/streetwear / r/femalefashionadvice
  - 健康：r/loseit / r/biohackers
  - 科技：r/artificial / r/technology / r/OpenAI
  - 大盘：r/popular / r/news（噪声大，靠 source-sub 黑名单清）
  - 影视：r/movies / r/television / r/popculture
- **为什么是 RSS 不是 .json**：Reddit 已封 .json 端点（无 OAuth 一律 403，换浏览器 UA / old.reddit.com 都没用）。RSS 是唯一零配置可达端点，代价是没有 ups/comments，热度改用 feed 内排名（`rank`，#1 = 该 sub 当日最热）。RSS 同样有滑动窗口限流，故并发降到 3 + 失败重试（403/429 退避重试 2 次）。
- Google Trends Realtime US RSS（10 条，仅用于 cross-check 加分）

**第二层（Claude 用 WebSearch enrichment）**：
- 对 selftext 不足以判断引爆点 / 写 brief 的候选，做 1-2 次 WebSearch：
  - 跨平台验证（Twitter/TikTok/主流媒体也爆了吗）
  - 找仿拍参考（TikTok 已有作品多少 → 判断红利窗口）
  - 补 Reddit selftext 没讲清的引爆点细节

**为什么不用通用 WebSearch 当主路**（v4.8.0 的错）：
- WebSearch 无原生 24h 过滤 → "past 24 hours" query 是软提示
- 搜索引擎索引延迟 1-3 天 → 拿不到今天的事
- 拿到的是行业报告/年度展望，不是 24h 内事件
- v5.0 实测：5 路 query + 24h 文本 → 42 条 link 里 **0 条 24h 内**

## 首次使用

无需任何配置即可使用。前置条件：

1. **Python 3.8+**（脚本只用标准库 urllib + json + xml.etree，无需 pip install）
2. **网络可访问 reddit.com 和 trends.google.com**

**想自定义 26 个数字角色**（可选）：

```bash
mkdir -p ~/.config/ops-skills
cp <skill-dir>/personas.yaml ~/.config/ops-skills/personas.yaml
$EDITOR ~/.config/ops-skills/personas.yaml
```

跨 plugin 升级保留。

## 工作流（按顺序执行）

### Step 1 - 读 personas.yaml

```bash
USER_PERSONAS="$HOME/.config/ops-skills/personas.yaml"
[ -f "$USER_PERSONAS" ] && PERSONAS="$USER_PERSONAS" || PERSONAS="<skill-dir>/personas.yaml"
```

### Step 2 - 算日期

用 Bash `date` 拿当前北京时间。美东日期 = 北京日期 - 1。简报日期格式："5月27日（周二）"。

### Step 3 - 跑 scout_reddit.py 拉候选

```bash
python3 <plugin-root>/skills/us-trend-scout/scout_reddit.py \
  --output /tmp/us-trend-candidates.json
```

脚本输出 `/tmp/us-trend-candidates.json`，结构：

```json
{
  "generated_at": "2026-05-28T01:00:00+00:00",
  "source": "reddit RSS (/top/.rss?t=day) — .json 端点已被 Reddit 封禁",
  "heat_signal": "rank = RSS feed 内 24h top 排名（越小越热）；RSS 无 ups/comments",
  "stats": {
    "subs_attempted": 16,
    "subs_succeeded": 16,
    "total_raw_posts": 307,
    "passed_filter": 266,
    "intra_dedup_dropped": 1,
    "history_deduped": 0,
    "cap_dropped": 145,
    "final_candidates": 120,
    "trends_items": 10
  },
  "per_sub": {"OutOfTheLoop": {"raw": 3, "passed": 3}, ...},
  "candidates": [
    {
      "title": "...",
      "rank": 1,
      "age_h": 7.3,
      "permalink": "https://www.reddit.com/r/technology/comments/.../",
      "url": "...（站外链接；self post 回落到 permalink）",
      "fetched_from": "technology",
      "source_sub": "technology",
      "post_id": "t3_xxx",
      "selftext": "..."
    }
  ],
  "google_trends": [{"term": "...", "traffic": "1000+", "news_titles": [...]}]
}
```

脚本已经做完了 2 层闸门：(1) 24h 硬过滤（RSS `t=day` + `published` 校验）(2) 主题/形态/source-sub 排除 + 同跑内去重 + 7 天历史去重 + 按 `rank` 排序取前 120。Claude **不需要重做这些**。（v5.3 走 RSS 后没有 ups/comments，故删掉 v5.0 的注意力阈值闸门和 flair 闸门，热度看 `rank` 字段。）

### Step 4 - 定性判断 + WebSearch enrichment（Claude 端核心思考）

读 `/tmp/us-trend-candidates.json` 的 `candidates` 数组 + `google_trends` 数组。**对每条先过"文化趋势"第一道筛（v5.4 cici 需求），通过了再做 3 句定性判断**：

**第一道筛 — 文化趋势优先（最高优先级，v5.4）**

运营做 TikTok 数字角色内容，要的是能配角色出片的**文化趋势**，不是硬社会新闻。先给每条归类：

- ✅ **文化趋势（优先进）**：生活方式 / 审美潮流 / meme 网络梗 / 情绪态度 / 时尚美妆趋势 / 影视娱乐现象 / 消费趋势 / 亚文化圈层。例：某种穿搭审美爆火、一个 meme 病毒式传播、某剧引发的集体情绪、一种价值观在年轻人中流行。
- ❌ **硬社会新闻（默认 drop）**：政治法律监管 / 商业财经（估值融资裁员诉讼）/ 硬科技新闻 / 灾难犯罪。例：Florida 诉 OpenAI、SpaceX 估值腰斩、某公司裁员、AI 监管法案。

**关键收口**：硬社会新闻**即使"有角色能写 hot take"也默认 drop**（这是之前社会新闻泛滥的病根）。唯一例外：一条硬新闻**已经在年轻人中发酵成文化现象 / 集体情绪**（不是新闻本身，而是它引爆的文化反应），才当文化趋势进。例：单纯"AI 抢工作"就业新闻 → drop；但"全网年轻人集体拿 AI 焦虑玩梗 / 反 AI 情绪刷屏"的文化现象 → 进。

**过了第一道筛（确认是文化趋势）后，再过 3 个 yes**：

1. **今天有人在讨论这事吗**（不是慢趋势）—— 脚本已保证 candidates 数组 24h 内（Reddit RSS `t=day` + `published` 二次校验）；`rank` 越小说明在该 sub 当日越热；GT 数组看 traffic 估算
2. **26 角色里有谁能写出具体仿拍 brief**（场景 + 动作 + 钩子，不是泛言"可以蹭"）—— 写不出来就 drop
3. **这条推给运营能产 1-2 条视频选题吗** —— Claude 综合判断

**3 yes 进简报，任一 no 直接 drop**。不打分、不算总分、不卡阈值。

**WebSearch enrichment（可选，只对 Step 2 写不清楚 brief 的做）**：

如果 Reddit selftext 不足以判断引爆点 / 写仿拍 brief，做 1-2 次 WebSearch：

1. **跨平台验证 query**：`"[热点关键词]" Twitter TikTok past 24 hours`
2. **仿拍参考 query**：`"[热点关键词]" TikTok video viral creators`

enrichment 拿到的信息回到 Step 2 重新判断"能不能写具体 brief"。

**v5.4 修正（cici 需求，社会新闻泛滥的病根在此）**：之前"有角色能写 hot take 就进"是病根——它让 AI 监管 / 政治 / 财经硬新闻只要 priya/ro/iris 能"hot take"就大量涌入，挤掉了真正的文化趋势。现在收口：**硬社会新闻即使能 hot take 也默认 drop，优先真正的文化趋势**（见第一道筛）。政治/法律/灾难类除非已发酵成文化现象 / 集体情绪，否则 drop。

### Step 5 - 涌现式输出（不为完成而完成）

按"文化趋势强度 + 仿拍价值"排序进简报（v5.4 起：文化趋势 > 社会新闻，硬新闻类即使个别进了也限 2-3 条以内）。**核心原则**：

- ❌ 不强求 5 赛道平均分配
- ❌ 不强求 26 角色平均覆盖
- ❌ 不为凑数硬塞（3 yes 没全过的坚决不进）
- ❌ 不让硬社会新闻占多数（v5.4：政治/财经/监管硬新闻整体压到 2-3 条以内，把位置留给文化趋势）
- ✅ 候选池现在稳定 100+ 条（v5.3 RSS），**正常一天应能涌现 8-15 条**，别过度保守只挑三五条
- ✅ 但质量第一：宁可某天 6 条全是好的，不要 12 条注水
- ✅ 真没有才说 0 条（很罕见，多数日子美区舆论场都有料）

**人设配对**：每条找**最贴合的 1-3 个**角色，给具体仿拍 brief（场景 + 动作 + 钩子）。**简报里不写"为什么选这条"**——把判断展示给运营会显得 Claude 在自辩，运营要的是"选完的结果"。

### Step 6 - 拼简报（v5.0 涌现式格式）

**markdown 富文本**（飞书 card 渲染 `**加粗**` / `[文字](url)` 链接）。

每条结构 5 行（v5.2 去掉 `[TAEP X/25]` 标签）：

```
#N
🔥 **热点 title 简短描述**
📊 r/sub · 24h top #N · Zh ago  （或 Google Trends traffic: X）
🔗 来源：[Reddit 原帖](url) | [跨平台报道](url) | [TikTok 参考](url)
🎭 人设：A 拍「具体场景+动作+钩子」；B 拍「...」
```

**简报整体结构**：

```
美区热点日报 | 5月28日（周四）| 今日真热点 N 条

#1
🔥 **Erin Brockovich 公布全美 4,200 个数据中心地图，呼吁本地社区行动**
📊 r/technology · 24h top #1 · 7.3h ago
🔗 来源：[Reddit 原帖](url) | [The Verge 报道](url) | [TikTok #datacenterprotest](url)
🎭 人设：Mia 拍「湾区 SWE bro 查自家附近数据中心位置 vlog」；Ryan 拍「AI 时代环境账单这样算」

#2
🔥 **小学生（12 岁起）大规模和 AI 女友谈恋爱，专家警告**
📊 r/technology · 24h top #3 · 23h ago
🔗 来源：[Reddit 原帖](url) | [Guardian 报道](url) | [TikTok 仅 23 个 reaction，窗口开](url)
🎭 人设：Jade 拍「心理咨询师视角，男孩 AI 女友会带来什么」；Mia 拍「AI 公司怎么放任 12 岁注册的」

...

— 今日抓到 X raw / Y 过 2 层闸门 / Z 与过去 7 天重复 drop / 按 rank 取前 120 + GT 经定性筛选后，N 条满足 "26 角色能写具体仿拍 brief" 标准 —
```

**0 条达标时**：

```
美区热点日报 | 5月28日（周四）| 今日无符合标准的真热点

今日抓到 X 条候选，经定性判断（3 yes 进简报）无一条满足 "26 角色能写具体仿拍 brief"。
可能原因：(a) 美区今日确无新事件冒头，(b) 候选偏 Reddit 内部讨论 / 体育 / 政治党争（无角色能写专业 hot take），(c) 候选偏行业宏观讨论非具体事件。

明日再抓。
```

### Step 7 - 推飞书

```bash
WEBHOOK=$(grep '^feishu_webhook_trend:' ~/.config/ops-skills/tk-template-scout.yaml 2>/dev/null | sed 's/^feishu_webhook_trend: *"\(.*\)"$/\1/')

if [ -z "$WEBHOOK" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then
  echo "skip 飞书推送：webhook_trend 未配置"
else
  python3 <plugin-root>/skills/tk-template-scout/push_feishu_card.py \
    --briefing briefing.txt \
    --webhook "$WEBHOOK"
fi
```

返回非 `code:0` → 退出码 1，简报继续 dump 对话。

### Step 8 - 最终报告

简报 dump 后追加简短统计：

```
[stats]
  原始 RSS 条目: 307 (16 sub × ~20)
  过 2 层闸门: 266
  跨天去重 drop: 5
  按 rank 取前: 120
  定性筛过 (3 yes): N
  涌现真热点: N
  飞书推送: ok/skip
```

## /schedule 自动化

每天北京 9:00 自动跑（用户在终端跑，本 skill 不调）：

```
/schedule create "0 1 * * *" "run skill us-trend-scout"
```

UTC 01:00 = 北京 09:00（美东前一天晚上 8-9 点）。

## 文体约束

- 全中文。专有名词（TikTok / Gen Z / hashtag / sound / Reddit / sub）保留英文
- **不用 em dash（—）**，用逗号、句号、冒号
- markdown 富文本（飞书 card 渲染 `**加粗**` / 链接）
- 数字角色名首字母大写（Caden / Sophie），不写 handle
- 每条热点必须带：r/sub + 24h top 排名 + age + Reddit 原帖 + 至少 1 个跨平台来源（GT 条目用 traffic + 跨平台来源）
- **不允许编时间和排名** — `age_h` 和 `rank` 字段全部来自 scout_reddit.py（脚本算的），RSS 没有 ups/comments，不许编造点赞/评论数

## 失败处理

| 故障 | 处理 |
|---|---|
| scout_reddit.py 整体失败 | 退出码 1，给清晰错误信息（"Reddit 网络不通" / "Python 不在 PATH" / "RSS 限流 403"等），不退化到 WebSearch（v4.8.0 已验证那是死路） |
| 多数 sub 报 403 | RSS 被限流。脚本已并发 3 + 重试 2 次；若仍大面积 403，等几分钟重跑（Reddit 滑动窗口会恢复） |
| 部分 sub 失败 | 脚本会继续跑其他 sub，stats.subs_succeeded 反映 |
| Google Trends 拉不到 | trends_error 记录，cross-check 减分但不影响主流程 |
| WebSearch enrichment 失败 | 该条候选用纯 Reddit 数据判断；不强行重试 |
| 0 条达标 | **诚实留空**，简报照常发，标 "今日无符合标准的真热点" |

## 与 tk-template-scout 的分工

| skill | 信源 | 专攻 |
|---|---|---|
| **tk-template-scout** | TikTok hashtag 页（yt-dlp）| TikTok 平台内 viral 模板（按 sound/hashtag 索引），找仿拍参考视频 |
| **us-trend-scout**（本 skill）| Reddit + Google Trends + WebSearch | TikTok 外冒头的事件型热点（Reddit 帖发酵 / 跨平台新闻 / Twitter 现象） |

两者同一天跑，**互不重复**。本 skill v4.8.0 起把 viral 挑战已迁出避免重复。

## 版本演进

**v5.0 vs v4.8.0**：

| 维度 | v4.8.0（已弃） | v5.0 |
|---|---|---|
| 信源 | 5 路通用 WebSearch | scout_reddit.py + Google Trends + WebSearch enrichment |
| Query 形态 | "industry shift movement" 慢趋势词 | 不用 query，直接拉 Reddit hot 24h |
| 24h 过滤 | query 文本软提示（无效）| Reddit 原生 `t=day` + 时间戳硬过滤 |
| 实际拿到 | 全是 McKinsey/Vogue 年度报告 | 24h 内真发酵帖（如 "12 岁 AI 女友" / "Erin Brockovich 数据中心地图"）|
| 实测真热点 | 0 条（全是慢趋势）| 5-15 条（依当日舆论场涌现）|
| 去重 | 无 | 7 天跨天 + 同跑内 permalink |
| 输出 | 5 赛道凑 5 条 | 涌现式，达标几条出几条，0 条诚实留空 |

**v5.3（当前）变更**：Reddit 封了 `.json` 端点（无 OAuth 一律 403），scout_reddit.py 改走 **RSS**（`/top/.rss?t=day`）。

| 维度 | v5.0（.json，已失效） | v5.3（RSS，当前） |
|---|---|---|
| 端点 | `/r/<sub>/top.json?t=day` → **现在 403** | `/r/<sub>/top/.rss?t=day` → 任何 UA 可达 |
| 热度信号 | ups + comments 精确数 + 阈值闸门 | feed 内 `rank`（#1 = 该 sub 当日最热），无 ups/comments |
| 闸门 | 3 层（含 ups/comments 阈值 + flair）| 2 层（24h + 主题/形态/source-sub），删阈值和 flair |
| 候选池 | 阈值过滤后约 85 | 按 rank 取前 120（给"多推"留空间）|
| 并发 | 8 | 3 + 失败重试（RSS 限流更敏感）|
| 简报 📊 行 | `ups: X · comments: Y · age · r/sub` | `r/sub · 24h top #N · age` |
