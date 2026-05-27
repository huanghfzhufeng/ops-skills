---
name: us-trend-scout
description: 美区 24h 真热点抓取 + 26 数字角色创意配对。v5.0 重构：从"5 路通用 WebSearch + 慢趋势 query"换成"scout_reddit.py 脚本拉 16 个精选 Reddit sub（含 r/OutOfTheLoop 文化引爆点金矿 + r/technology + r/news + 美妆/健康/影视 sub）+ Google Trends 侧路 cross-check + Claude 端 WebSearch enrichment + TAEP 五维评分 + 7 天跨天去重 + 涌现式输出（不为完成而完成）"。卢雨悦每天必用。触发：用户说"热点日报"、"美区热点"、"us trend"、"trend scout"、"跑一次热点"，或被 /schedule 定时触发。
---

# US Trend Scout

抓美区 24h 真热点（事件型，非慢趋势）+ 26 数字角色创意配对，作为运营选题灵感。每天北京时间 9:00 自动跑（= 美东前一天晚上 8-9 点）。

简报**直接 dump 到对话**给运营看，同时推送飞书（如配置 webhook）。

## v5.0 设计原则（critical）

四条原则：

1. **24h 硬窗口** — 脚本层用 Reddit `t=day` 原生过滤 + `created_utc` 二次校验；超 24h 任何形式 drop。不靠 query 文本提示。
2. **质量第一 → 宁缺勿滥** — 不为完成而完成。今天涌现几条出几条，**禁止凑数**。不达标赛道留空。
3. **跨天去重** — 7 天指纹库，重复热点 drop（保持每天新鲜）。
4. **TikTok 外的跨平台热点** — 跟 tk-template-scout 错位。TikTok 平台内热点由那个 skill 接管，本 skill 专补 Reddit/Google Trends 等 TikTok 外冒头但即将蔓延的事件。

## 信源（v5.0 重构）

**第一层（scout_reddit.py 脚本）**：
- Reddit 16 个精选 sub（每 sub 100 条/24h）：
  - 核心：r/OutOfTheLoop（文化引爆点金矿，自带"为什么 X 爆了"解释）
  - 美妆：r/AsianBeauty / r/Sephora / r/30PlusSkinCare
  - 时尚：r/streetwear / r/femalefashionadvice
  - 健康：r/loseit / r/biohackers
  - 科技：r/artificial / r/technology / r/OpenAI
  - 大盘：r/popular / r/news（噪声大，靠 source-sub 黑名单清）
  - 影视：r/movies / r/television / r/popculture
- Google Trends Realtime US RSS（10 条，仅用于 cross-check 加分）

**第二层（Claude 用 WebSearch enrichment）**：
- 对每条进入 TAEP 评分的候选，做 1-2 次 WebSearch：
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
  "generated_at": "2026-05-27T01:00:00+00:00",
  "stats": {
    "subs_attempted": 16,
    "subs_succeeded": 15,
    "total_raw_posts": 643,
    "passed_filter": 90,
    "intra_dedup_dropped": 3,
    "history_deduped": 5,
    "final_candidates": 85,
    "trends_items": 10
  },
  "per_sub": {"OutOfTheLoop": {"raw": 3, "passed": 2}, ...},
  "candidates": [
    {
      "title": "...",
      "ups": 22787,
      "comments": 547,
      "age_h": 7.3,
      "permalink": "https://reddit.com/...",
      "url": "...",
      "fetched_from": "technology",
      "source_sub": "technology",
      "flair": "...",
      "selftext": "..."
    }
  ],
  "google_trends": [{"term": "...", "traffic": "1000+", "news_titles": [...]}]
}
```

脚本已经做完了 3 层闸门：(1) 24h 硬过滤 (2) 主题/形态/source-sub/flair 排除 (3) upvote+comments 阈值 + 同跑内 permalink 去重 + 7 天历史去重。Claude **不需要重做这些**。

### Step 4 - TAEP 评分 + WebSearch enrichment（Claude 端核心思考）

读 `/tmp/us-trend-candidates.json` 的 `candidates` 数组。**对每条**按 TAEP 五维评分（每维 1-5，T 由脚本保证恒等 5）：

| 维度 | 评分细则 |
|---|---|
| **T 时间锐度** | 脚本保证 24h 内 = 5（恒等） |
| **A 注意力** | ups > 10000 = 5；> 5000 = 4；> 2000 = 3；> 500 = 2；其他 = 1 |
| **E 引爆点清晰** | 能指到具体视频/事件/产品/帖子 = 5；只是讨论 = 3；定性 = 1 |
| **P 可参与度** | 26 角色 ≥ 2 个能蹭 = 5；1 个能蹭 = 3；0 个 = **drop**（不评分） |
| **C 商业属性** | 消费/生活方式/文化/科技产品 = 5；中性新闻 = 2；政治/体育/灾难 = 1（**< 3 drop**） |

**初筛门槛**：总分 ≥ 20/25 进入第二轮 WebSearch enrichment。**这不是死阈值**，是 Claude 的自审清单——核心判断是"它是不是真热点"。

**对每条过初筛的候选，做 1-2 次 WebSearch**：

1. **跨平台验证 query**：`"[热点关键词]" Twitter TikTok past 24 hours`
   - 加分项：主流媒体（Variety/Vox/BBC/CNBC）也报道 → A 加 1 分
   - 减分项：只有 Reddit 内部讨论 → A 减 1 分

2. **仿拍参考 query**：`"[热点关键词]" TikTok video viral creators`
   - 加分项：TikTok 已有 reaction 但 < 50 个 → P 加 1（红利窗口未关）
   - 减分项：TikTok 已有 500+ reaction → P 减 1（窗口已关闭）

跨平台 enrichment 完成后，**总分 ≥ 22/25 才进简报**（提高门槛，因为有了更多信息可判断）。

### Step 5 - 涌现式输出（不为完成而完成）

按调整后 TAEP 总分降序排列进入简报。**核心原则**：

- ❌ 不强求 5 条
- ❌ 不强求 5 赛道平均分配
- ❌ 不强求 26 角色平均覆盖
- ✅ 今天有几条真热点出几条（0-15 条都可能）
- ✅ 0 条就诚实说 0 条

**人设配对**：每条找**最贴合的 1-2 个**角色，给具体仿拍 brief（场景 + 动作 + 钩子）。**找不到合适的角色就不配**（P 评分应该已经过滤掉这种情况）。

### Step 6 - 拼简报（v5.0 涌现式格式）

**markdown 富文本**（飞书 card 渲染 `**加粗**` / `[文字](url)` 链接）。

每条结构 5 行：

```
#N [TAEP X/25]
🔥 **热点 title 简短描述**
📊 ups: X · comments: Y · Zh ago · r/sub
🔗 来源：[Reddit 原帖](url) | [跨平台报道](url) | [TikTok 参考](url)
🎭 人设：A 拍 "具体场景+动作+钩子"；B 拍 "..."
```

**简报整体结构**：

```
美区热点日报 | 5月27日（周二）| 今日真热点 N 条（候选 90 条经 TAEP 过滤）

#1 [TAEP 24/25]
🔥 **Erin Brockovich 公布全美 4,200 个数据中心地图，呼吁本地社区行动**
📊 ups: 22,787 · comments: 547 · 7.3h ago · r/technology
🔗 来源：[Reddit 原帖](url) | [The Verge 报道](url) | [TikTok #datacenterprotest](url)
🎭 人设：Mia 拍 "湾区 SWE bro 查自家附近数据中心位置 vlog"；Ryan 拍 "AI 时代环境账单这样算"

#2 [TAEP 23/25]
🔥 **小学生（12 岁起）大规模和 AI 女友谈恋爱，专家警告**
📊 ups: 17,769 · comments: 2,673 · 23h ago · r/technology
🔗 来源：[Reddit 原帖](url) | [Guardian 报道](url) | [TikTok 仅 23 个 reaction，窗口开](url)
🎭 人设：Jade 拍 "心理咨询师视角，男孩 AI 女友会带来什么"；Mia 拍 "AI 公司怎么放任 12 岁注册的"

...

— 今日另抓到 75 条 24h 内候选，但均未达到 TAEP 22/25 标准 —
— 已 drop 5 条与过去 7 天重复的热点 —
```

**0 条达标时**：

```
美区热点日报 | 5月27日（周二）| 今日无符合标准的真热点

今日抓到 90 条候选，经 TAEP 五维评分 + WebSearch cross-check，无一条满足 22/25 门槛。
可能原因：(a) 美区今日确无新事件冒头，(b) 重大事件被排除规则过滤（政治/体育/灾难类），
(c) 候选偏 Reddit 内部讨论未跨平台。

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
  原始候选: 643 (16 sub × ~40)
  过 3 层闸门: 90
  跨天去重 drop: 5
  TAEP 初筛 (≥20): 18
  WebSearch enrich + 二筛 (≥22): N
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
- 每条热点必须带：TAEP 分 + ups + comments + age + Reddit 原帖 + 至少 1 个跨平台来源
- **不允许编时间** — 时间字段全部来自 scout_reddit.py 的 `age_h` 字段（脚本算的）

## 失败处理

| 故障 | 处理 |
|---|---|
| scout_reddit.py 整体失败 | 退出码 1，给清晰错误信息（"Reddit 网络不通" / "Python 不在 PATH" 等），不退化到 WebSearch（v4.8.0 已验证那是死路） |
| 部分 sub 失败 | 脚本会继续跑其他 sub，stats.subs_succeeded 反映 |
| Google Trends 拉不到 | trends_error 记录，cross-check 减分但不影响主流程 |
| WebSearch enrichment 失败 | 该条候选用纯 Reddit 数据评分；不强行重试 |
| 0 条达标 | **诚实留空**，简报照常发，标 "今日无符合标准的真热点" |

## 与 tk-template-scout 的分工

| skill | 信源 | 专攻 |
|---|---|---|
| **tk-template-scout** | TikTok hashtag 页（yt-dlp）| TikTok 平台内 viral 模板（按 sound/hashtag 索引），找仿拍参考视频 |
| **us-trend-scout**（本 skill）| Reddit + Google Trends + WebSearch | TikTok 外冒头的事件型热点（Reddit 帖发酵 / 跨平台新闻 / Twitter 现象） |

两者同一天跑，**互不重复**。本 skill v4.8.0 起把 viral 挑战已迁出避免重复。

## v5.0 vs v4.8.0 对比

| 维度 | v4.8.0（已弃） | v5.0（当前） |
|---|---|---|
| 信源 | 5 路通用 WebSearch | scout_reddit.py + Google Trends + WebSearch enrichment |
| Query 形态 | "industry shift movement" 慢趋势词 | 不用 query，直接拉 Reddit hot 24h |
| 24h 过滤 | query 文本软提示（无效）| Reddit API 原生 `t=day` + `created_utc` 硬过滤 |
| 实际拿到 | 全是 McKinsey/Vogue 年度报告 | 24h 内真发酵帖（如 "12 岁 AI 女友" / "Erin Brockovich 数据中心地图"）|
| 实测真热点 | 0 条（全是慢趋势）| 5-15 条（依当日舆论场涌现）|
| 去重 | 无 | 7 天跨天 + 同跑内 permalink |
| 输出 | 5 赛道凑 5 条 | 涌现式，达标几条出几条，0 条诚实留空 |
