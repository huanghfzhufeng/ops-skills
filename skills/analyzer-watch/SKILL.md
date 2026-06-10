---
name: analyzer-watch
description: 监听 TikTok Analyzer（自建账号数据后台）的爆款视频，「播放破 500」或「ER 破 5%」的视频立刻推送到飞书群（带视频封面的小卡片：账号 + 封面 + 播放 + ER + 发布多久 + 互动 + 看视频，整卡点击跳转，一条一卡；ER 可配最低播放门槛去噪；封面失败自动降级纯文字卡）。已预警视频播放再破 1万/10万 时各推一次「升级播报」橙卡（每档一次、跳档只报最高档、上线第一轮静默记档防刷屏）。JWT 登录拉 /api/metrics/trending 全量视频，video_id 集合 diff 做增量去重，首次跑建 baseline 不推历史。触发：用户说「爆款预警」「analyzer 推送」「analyzer-watch」「跑一次爆款监控」「破 500 推送」，或被 /schedule 高频定时触发（默认每 10 分钟，破阈值即推）。
---

# Analyzer Watch

监听 **TikTok Analyzer**（自建账号数据后台，追踪 28 个数字角色账号约 1300+ 条视频），
**视频播放破 500，或 ER 破 5%，就立刻推飞书群**（带视频封面的小卡片）。

数据源：Analyzer 的 JSON API（JWT 登录，**不爬 HTML**）。阈值都可在配置里调。

## 命中逻辑（当前：v1）

```
播放 > 1000   或   ( ER > 5%  且  播放 > 500  且  发布 ≤ 7 天 )
```

- **条件1 · 纯流量爆款**：播放破 1000 即推，不管 ER、不管发布多久。
- **条件2 · 高互动新视频**：ER > 5% 且 播放 > 500 且 7 天内发布。「7 天」砍掉「老视频慢热的虚高 ER」（实测 ER 候选里约 85% 是 7 天前老视频，被这条约束砍掉）。
- 四个阈值都可配：`view_threshold`(1000) / `er_threshold`(5) / `er_min_views`(500) / `er_max_age_days`(7)。

## 升级播报（里程碑两档）

**已经预警过**的视频继续爆，跨档再提醒：播放 **>1万** 推一次、**>10万** 再推一次
（**橙色卡**，标题「升级播报 · @handle · 播放破1万/10万」，区别于首次预警红卡）：

- 每条视频每档**只报一次**，全生命周期最多 3 张卡（首推红卡 + 1万橙卡 + 10万橙卡）。
- **跳档只报最高档**：两轮轮询间从几千直接蹿到 15 万 → 只发一张「破10万」，不连发两张。
- **首推即破档不补报**：首推时播放已 >1万 → 静默记档（首推卡已显示真实播放，补报是噪音）。
- **上线/状态文件升级的第一轮静默记档**：把 seen 里历史视频按当前播放记档、一张不发，
  防止把历史破万视频补发一遍刷爆群。
- 推送失败不记档，下轮自动重试；单轮升级播报上限 10 张，超出下轮续推。
- 档位可配 `milestone_thresholds`（默认 `"10000,100000"`），配空 = 关闭该功能。
- 状态存同一个 seen.json 的 `milestones` 字段（`{video_id: 已报最高档}`），向后兼容老格式。

> **版本命名约定**：命中条件每次调整按 `v1 / v2 / v3` 递增命名，**不要用「周会版」这种按来源的叫法**。改条件时同步三处：① 本节标题的版本号 ② `find_hits` docstring ③ CHANGELOG 记一笔。

## 核心机制（对称 sge-blog-watcher）

- **全量增量检测**：每轮拉 `trending?limit=50000`（= 全部视频按热度排，不只热门 top），筛达标的跟本地 `seen`（video_id 集合）diff，只推新破阈值的。**全量才不漏**「10 多天前发、最近才慢慢爬过阈值」的慢热视频。
- **永久去重**：推过的 video_id 进 `seen`，**一条只推一次**。
- **首次 baseline**：第一次跑把现有所有达标视频（无门槛实测约 575 条）记 `seen` 但**不推**，避免首跑刷爆群。
- **一条一卡**：每个破阈值视频单独一张飞书红卡。
- **立刻推**：靠 `/schedule` 每 10 分钟轮询，不等每天 9 点。

## 卡片样式

一条爆款一张红卡（`template:red` 背景，非 emoji），**整卡点击跳转视频**：

- **配了封面图**：左图右文小卡 —— 左侧视频封面小图，右侧「账号（标题）｜ 播放 + ER ｜ 发布多久前 ｜ 互动(只显非 0) + 看视频」。
- **没封面（降级）**：纯文字卡 —— 账号 + 播放/ER/发布 + 互动 + 看视频链接。

## 封面图（可选）

配了 `feishu_app_id` / `feishu_app_secret` / `proxy` 才启用，否则只发纯文字卡。

**机制（为什么绕）**：飞书 **webhook 自己传不了图**，必须先上传飞书拿 `image_key`，而上传要 app 凭证；个人飞书的自建应用又**加不了群**，所以走「**app 只上传图 + webhook 发消息**」——webhook 认同账号 app 上传的 `image_key`。封面 URL 用 TikTok **oEmbed 实时取**（analyzer 存的带签名、几小时就过期），访问 TikTok 要走 `proxy`。

**降级**：封面链路任一步失败（没配 app / 代理没开 / oEmbed 超时 / 上传失败）→ **自动发纯文字卡**，推送绝不中断（输出标 `cover: on/off`）。

**关键约束**：webhook 群必须和 app 在**同一个飞书账号**下，否则图引用不了（降级文字卡）。个人飞书走这套；企业飞书可改用 app 直接加群发消息（更简单，一个 app 包办图文）。

## 首次使用

1. **Python 3.8+**（仅标准库，无需 pip install）
2. **配置**：
```bash
mkdir -p ~/.config/ops-skills
cat > ~/.config/ops-skills/analyzer-watch.yaml <<'EOF'
base_url: "http://104.131.123.99:8001"
email: "你的 analyzer 账号"
password: "密码"
feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
view_threshold: 500
er_threshold: 5
er_min_views: 0
# 以下封面图可选，不配就发纯文字卡
feishu_app_id: "cli_xxxxx"
feishu_app_secret: "xxxxx"
proxy: "http://127.0.0.1:7892"
EOF
```
3. **建 baseline（首次必做，否则把现有约 575 条历史达标全推爆群）**：
```bash
python3 <skill-dir>/watch.py run   # 输出 mode:baseline,记录现有达标视频但不推
```
看到 `"mode": "baseline"` 即建好，之后再跑就是增量模式。

## 工作流

数据现成（账号/播放/ER/发布时间/链接都在 API 里），**不需要 Claude 中间翻译**，watch.py 一把梭：

```bash
python3 <plugin-root>/skills/analyzer-watch/watch.py run
```

输出 JSON，按 `mode` 判断：
- `"mode": "baseline"` → 首次，baseline 已建，**结束**（不推不发消息）。
- `"mode": "incremental", "new": 0` → 无新破阈值视频，**静默结束**（高频轮询大部分走这条，不刷屏）。
- `"mode": "incremental", "new": N, "pushed": M, "cover": "on/off"` → 推了 M 条，cover 标本轮有没有封面。
- 带 `"warn"` 字段 → 视频数逼近拉取上限，需调大 watch.py 里的 `FETCH_LIMIT`。
- 带 `"error"` 字段 → 数据源/登录失败，本轮**跳过**（不建 baseline、不推），下轮重试。

`run --dry-run` 只看会推哪些不真推（调试用）。

## 查推送历史

```bash
python3 <skill-dir>/watch.py log            # 最近 20 条
python3 <skill-dir>/watch.py log --tail 0   # 全部
```

每次成功推送追加一行到 `~/.config/ops-skills/analyzer-watch-pushlog.jsonl`（时间/账号/命中/播放/ER/链接）。

## /schedule 自动化（破阈值即推）

```bash
/schedule create "*/10 * * * *" "run skill analyzer-watch"
```

每 10 分钟轮一次。大部分轮询落在「无新 → 静默」，几乎不耗 token；只有真有新爆款那次才推。
封面图依赖代理：定时任务跑时代理开着 = 带封面；代理没开 = 自动降级纯文字卡。

## 失败处理

| 故障 | 处理 |
|---|---|
| 登录失败 | 输出 `error` + 退出 1；查 `analyzer-watch.yaml` 凭证 |
| webhook 未配 / 占位符 | 输出 `error` 退出；去配 yaml |
| 数据源抓取失败 | 输出 `error` **跳过本轮**（不建空 baseline、不推），下轮重试 |
| 单条推送失败 | 该 video_id 不 commit，下轮自动重试；其他卡照常推 |
| 封面拿不到（代理没开/超时/跨账号） | **自动降级纯文字卡**，推送不中断，输出标 `cover:off` |
| 异常爆量（>15 条/轮）| 按播放推前 15 条，输出 `note` 标注剩余下轮续推 |
| 视频数逼近拉取上限 | 输出 `warn` 提醒调大 `FETCH_LIMIT`，绝不静默截断漏视频 |

## 与其他 skill 的分工

| skill | 数据源 | 触发 | 专攻 |
|---|---|---|---|
| us-trend-scout | Reddit | 每天 9:00 | 美区文化趋势热点 |
| tk-template-scout | TikTok 搜索 | 每天 9:00 | 26 人模板供仿拍 |
| sge-blog-watcher | SGE 博客 | 每 10 分钟 | UGC 模板增量 |
| **analyzer-watch**（本 skill） | TikTok Analyzer API | **每 10 分钟** | 自家号爆款视频破阈值预警 |

本 skill 监控的是**自家号已发视频的实时表现**（哪条爆了），跟前几个「找选题 / 找模板」错位，互不重复。
