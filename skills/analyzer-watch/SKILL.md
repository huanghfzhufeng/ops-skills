---
name: analyzer-watch
description: 监听 TikTok Analyzer（自建账号数据后台）的爆款视频，播放破 500 或 ER 破 5% 的视频立刻推送到飞书群（账号 + 命中原因 + 播放/ER + 互动数 + 视频链接，一条一卡）。JWT 登录拉 /api/metrics（daily 当天 + trending 热门），video_id 集合 diff 做增量去重，首次跑建 baseline 不推历史。触发：用户说「爆款预警」「analyzer 推送」「analyzer-watch」「跑一次爆款监控」「破 500 推送」，或被 /schedule 高频定时触发（默认每 30 分钟，破阈值即推）。
---

# Analyzer Watch

监听 **TikTok Analyzer**（自建的账号数据后台，追踪 26 数字角色账号的视频指标），
**视频播放破 500 或 ER 破 5% 就立刻推飞书群**。

数据源：Analyzer 的 JSON API（JWT 登录，**不爬 HTML**）。阈值可在配置里调。

核心机制（**对称 sge-blog-watcher**，复用同一套增量 + 去重 + baseline 设计）：

- **增量检测**：查 `daily`(当天) + `trending`(热门) 的达标视频，跟本地 `seen`（video_id 集合）diff，只推新破阈值的。
- **永久去重**：推过的 video_id 进 `seen`，绝不重推。
- **首次 baseline**：第一次跑把现有所有达标视频记 `seen` 但**不推**，避免首跑刷爆群（实测首次有 80+ 条历史达标）。
- **一条一卡**：每个破阈值视频单独一张飞书卡片。
- **立刻推**：靠 `/schedule` 高频轮询（默认 30 分钟），不等每天 9 点。

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
EOF
```
3. **建 baseline（首次必做，否则把现有 80+ 条历史达标全推爆群）**：
```bash
python3 <skill-dir>/watch.py run   # 输出 mode:baseline,记录现有达标视频但不推
```
看到 `"mode": "baseline"` 即建好，之后再跑就是增量模式。

## 工作流

数据现成（账号/播放/ER/链接/文案都在 API 里），**不需要 Claude 中间翻译**，watch.py 一把梭：

```bash
python3 <plugin-root>/skills/analyzer-watch/watch.py run
```

输出 JSON，按 `mode` 判断：
- `"mode": "baseline"` → 首次，baseline 已建，**结束**（不推不发消息）。
- `"mode": "incremental", "new": 0` → 无新破阈值视频，**静默结束**（高频轮询大部分走这条，不刷屏）。
- `"mode": "incremental", "new": N, "pushed": M` → 推了 M 条破阈值视频，报告。

`run --dry-run` 只看会推哪些不真推（调试用）。

## 查推送历史

```bash
python3 <skill-dir>/watch.py log            # 最近 20 条
python3 <skill-dir>/watch.py log --tail 0   # 全部
```

每次成功推送追加一行到 `~/.config/ops-skills/analyzer-watch-pushlog.jsonl`（时间/账号/命中/播放/ER/链接）。

## /schedule 自动化（破阈值即推）

```bash
/schedule create "*/30 * * * *" "run skill analyzer-watch"
```

每 30 分钟轮一次，匹配 Analyzer 的 scrape 节奏（它自己约几分钟～小时 scrape 一次 TikTok）。大部分轮询落在「无新 → 静默」，几乎不耗 token；只有真有新爆款那次才推。

## 失败处理

| 故障 | 处理 |
|---|---|
| 登录失败 | 输出 `error` + 退出 1；查 `analyzer-watch.yaml` 凭证 |
| webhook 未配 / 占位符 | 输出 `error` 退出；去配 yaml |
| 单条推送失败 | 该 video_id 不 commit，下轮自动重试；其他卡照常推 |
| analyzer API 抓不到 | 该源跳过（daily/trending 互为备份），下轮再试 |

## 与其他 skill 的分工

| skill | 数据源 | 触发 | 专攻 |
|---|---|---|---|
| us-trend-scout | Reddit | 每天 9:00 | 美区文化趋势热点 |
| tk-template-scout | TikTok 搜索 | 每天 9:00 | 26 人模板供仿拍 |
| sge-blog-watcher | SGE 博客 | 每 10 分钟 | UGC 模板增量 |
| **analyzer-watch**（本 skill） | TikTok Analyzer API | **每 30 分钟** | 自家号爆款视频破阈值预警 |

本 skill 监控的是**自家 26 个号已发视频的实时表现**（哪条爆了），跟前几个「找选题 / 找模板」错位，互不重复。
