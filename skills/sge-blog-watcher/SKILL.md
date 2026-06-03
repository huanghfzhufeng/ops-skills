---
name: sge-blog-watcher
description: 监听 Social Growth Engineers (socialgrowthengineers.com) 博客，发现新文章立刻推送到飞书群（中文标题 + 摘要 + 正文 TL;DR + 原文链接，一篇一张卡）。纯公开站 curl 抓取，无需登录 / cookies / 反爬。靠 sitemap URL 集合 diff 做增量检测，永久 seen 去重防重推，首次跑建 baseline 不推历史。触发：用户说「SGE 推送」「sge blog」「sge-blog-watcher」「检查 SGE 新博客」「跑一次 SGE」，或被 /schedule 高频定时触发（默认每 10 分钟，有更新即推，不等到 9 点）。
---

# SGE Blog Watcher

监听 [socialgrowthengineers.com](https://www.socialgrowthengineers.com)（一个筛选好的
TikTok UGC 模版站），**发现新博客就立刻推到飞书群**。每条博客 = 一个新模版，全部都推，不过滤。

数据源：SGE 公开站（`curl` 抓 sitemap + 文章页，无需登录 / cookies / 反爬）。

核心机制：
- **增量检测**：抓 5 个 sitemap 的全部博客 URL，跟本地 `seen` 集合 diff，只有新增才推。
  （SGE 的 `lastmod` 不可靠，全是当天，所以用 URL 集合 diff 而非时间戳。）
- **永久去重**：推过的 URL 进 `seen`，绝不重推。
- **首次 baseline**：第一次跑把现有约 2400 篇历史文章全记为 `seen` 但**不推**，
  之后只推真·新增。
- **一篇一卡**：每篇博客单独一张飞书富文本卡片。
- **立刻推**：靠 `/schedule` 高频轮询（默认每 10 分钟），不是每天 9 点批量。

## 首次使用

1. **Python 3.8+**（脚本仅标准库，无需 pip install）
2. **配 webhook**：

```bash
mkdir -p ~/.config/ops-skills
cat > ~/.config/ops-skills/sge-blog-watcher.yaml <<'EOF'
feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
EOF
```

3. **建 baseline（首次必做，否则会把上千篇历史全推爆群）**：

```bash
python3 <skill-dir>/watch.py check   # 首跑输出 mode:baseline，已记录历史，不推任何东西
```

看到 `"mode": "baseline"` 即 baseline 建好。之后再跑就是增量模式。

## 工作流（按顺序执行）

### Step 1 — check：diff 出新博客

```bash
python3 <skill-dir>/watch.py check --max-new 20 > /tmp/sge-new.json
```

读 `/tmp/sge-new.json` 的 `mode` 字段判断：

- `"mode": "baseline"` → 首次，baseline 已建，**结束**（不推，不发消息）。
- `"mode": "incremental"` 且 `new_count == 0` → 无新博客，**静默结束**（不发任何消息，
  高频轮询时大部分时候走这条，不许刷屏）。
- `"mode": "incremental"` 且 `new[]` 非空 → 有新博客，进 Step 2。
- 有 `"error"` 字段 → sitemap 抓取失败，报错给用户，结束。

### Step 2 — Claude 生成中文字段（按 translate_prompt.md）

```bash
cat <skill-dir>/translate_prompt.md   # 读规则
cat /tmp/sge-new.json                 # 读新博客的 meta + 正文
```

Claude 按 `translate_prompt.md`，对 `new[]` 里**每篇**（跳过带 `error` 的）一次性
生成 `title_cn` / `summary_cn` / `tldr_lines` / `read_minutes`，写出：

```bash
# Claude 用 Write 工具写 /tmp/sge-translated.json，结构 {"posts": [ ... ]}
```

`tldr_lines` 必须带具体 handle / 播放量 / 可复用钩子原文（仿拍要照抄），不许编数字。

### Step 3 — render：渲染成卡片文件

```bash
python3 <skill-dir>/render_card.py \
  --json /tmp/sge-translated.json \
  --outdir /tmp/sge-cards > /tmp/sge-manifest.txt
```

`/tmp/sge-manifest.txt` 每行 `卡片文件路径<TAB>URL`。格式固化，**Claude 不要二次加工**。

### Step 4 — 推飞书（一篇一卡）

读 webhook：

```bash
WEBHOOK=$(grep '^feishu_webhook:' ~/.config/ops-skills/sge-blog-watcher.yaml | sed 's/^feishu_webhook: *"\(.*\)"$/\1/')
if [ -z "$WEBHOOK" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then echo "ERROR: webhook 未配置"; exit 1; fi
```

> ⚠️ **关键：逐张单独推，一张卡 = 一条独立的 Bash 命令。绝对不要用 while/for 循环把多次推送串在一起。**
> 原因（已实测）：在 Claude 执行环境里，含循环的多命令 Bash 会被沙箱自动后台化，后台进程 POST 飞书会 **hang 到超时**（GET 抓取不受影响，只有 POST 飞书会卡）。单条前台命令则秒成。

`/tmp/sge-manifest.txt` 每行是 `卡片路径<TAB>URL`。**对每一行单独跑一条命令**（把 `<卡片路径>` 换成实际路径），每条看到 `"code":0` 即成功，把该 URL 追加到 `/tmp/sge-pushed.txt`；某张失败就不记（下轮自动重试）：

```bash
python3 <plugin-root>/skills/tk-template-scout/push_feishu_card.py --briefing "<卡片路径>" --webhook "$WEBHOOK"
```

### Step 5 — commit：把推成功的标记为已推（并写推送日志）

```bash
if [ -s /tmp/sge-pushed.txt ]; then
  python3 <skill-dir>/watch.py commit \
    --urls-file /tmp/sge-pushed.txt \
    --log-from /tmp/sge-translated.json
fi
```

`--log-from` 会从 translated.json 取标题，把本批推送（时间 / 分类 / 标题 / URL）
追加到 `~/.config/ops-skills/sge-blog-watcher-pushlog.jsonl`，供日后审计。
推失败的 URL 没进 `seen`，下一轮 check 还会被当新博客重试（至少推一次）。

### Step 6 — 简短报告

推完报告：新博客 N 篇 / 推成功 M 篇 / 失败几篇 / 飞书状态。**无新博客时什么都不说**。

## 查询推送历史

每次成功推送都会追加一行到 `~/.config/ops-skills/sge-blog-watcher-pushlog.jsonl`
（JSONL，每行含 `pushed_at` / `published` / `section` / `title` / `url`）。

```bash
python3 <skill-dir>/watch.py log              # 最近 20 条（默认）
python3 <skill-dir>/watch.py log --tail 50    # 最近 50 条
python3 <skill-dir>/watch.py log --tail 0     # 全部
```

用户问「这阵子推了哪些 SGE 模版」时跑这个即可，一键拉出完整清单。

## /schedule 自动化（立刻推，不等 9 点）

**这是「有更新立刻推」的关键**——用高频轮询代替每天一次：

```
/schedule create "*/10 * * * *" "run skill sge-blog-watcher"
```

每 10 分钟轮一次，有新博客最多延迟 10 分钟就推。想更快可改 `*/5`（每 5 分钟）。
SGE 不是秒级更新的站（一天几篇），10 分钟足够「准实时」，也不浪费。

> 大部分轮询会落在「无新博客 → 静默结束」，几乎不耗 token；只有真有新博客那次
> 才会触发翻译 + 推送。

## 失败处理

| 故障 | 处理 |
|---|---|
| sitemap 整体抓不到 | check 输出 `error` 字段 + 退出码 1；报错给用户，不推 |
| 单个子 sitemap 失败 | 脚本跳过它继续（记入 `sitemap_stats.sub_sitemaps_failed`），少的那批下轮补上 |
| 单篇文章抓失败 | 该篇在 `new[]` 里带 `error` 字段；Claude 跳过它（不翻译不推），不进 `seen`，下轮重试 |
| 飞书单卡推送失败 | 该 URL 不 commit，下轮重试；其他卡照常推 |
| webhook 未配置 | Step 4 报错退出，提示去配 `~/.config/ops-skills/sge-blog-watcher.yaml` |
| 新博客异常爆量 | `--max-new`（默认 20）截断，`truncated:true`，剩余下轮继续 |

## 与另外两个 skill 的分工

| skill | 数据源 | 触发 | 专攻 |
|---|---|---|---|
| us-trend-scout | Reddit + Google Trends | 每天 9:00 | 美区跨平台事件型热点 |
| tk-template-scout | TikTok hashtag 页 | 每天 9:00 | 26 人 × 关键词的 TikTok 模板，给仿拍参考 |
| **sge-blog-watcher**（本 skill） | SGE 公开博客站 | **每 10 分钟，有更新即推** | SGE 精选 UGC 模版博客，新发即转推飞书群 |

前两个是「每天批量拉取」，本 skill 是「高频监听增量」，互不干扰（不同 webhook、不同群）。
