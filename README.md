# ops-skills

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

美区 TikTok 矩阵号运营自动化工具集。[huanghfzhufeng](https://github.com/huanghfzhufeng) 出品。

## 包含的 Skill（4 个）

| Skill | 干啥 | 触发 |
|---|---|---|
| **us-trend-scout** | 每天抓美区 Reddit 24h **文化趋势**热点（RSS 拉 16 个精选 sub）→ 配 26 数字角色出创意 → 简报推飞书 | 「跑一次热点」/「美区热点」 |
| **tk-template-scout** | 26 人 × 3 词搜 TikTok 真实视频（Playwright + 24h 硬过滤）+ 全平台挑战 Top 3 → 每人 Top 模板供仿拍 → 简报推飞书 | 「跑一次 TK 模板」 |
| **sge-blog-watcher** | 监听 Social Growth Engineers 博客，发现新文章立刻推飞书群（中文标题 + 摘要 + TL;DR + 原文链接，一篇一卡片） | 定时 / 「跑一次 sge」 |
| **xcmo-mobile** | 按邮箱 + 日期从 xcmo 拉视频 → 按人物分组 → 起本地服务 + 二维码 → 手机扫码看视频 / 复制文案 | 「下载 \<邮箱\> \<日期\>」 |

> us-trend-scout 抓的是 **Reddit 文化趋势**（影视娱乐 / meme / 时尚美妆 / 生活方式情绪 / 名人文化），不是硬社会新闻；tk-template-scout 抓的是 **TikTok 平台内模板**。两者错位互补，同一天跑互不重复。

---

## 安装

### 一键安装（推荐，约 **5 分钟**搞定依赖 + cookies）

打开 **Mac 终端**（⌘+Space 搜「终端」回车），粘贴：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git ~/ops-skills
cd ~/ops-skills
bash setup.sh
```

`setup.sh` 会自动：

1. 检测平台 / Python / Chrome 是否就绪
2. 装 `yt-dlp`（Homebrew or pip）
3. 装 Python 依赖：`qrcode pillow PyYAML playwright playwright-stealth patchright`
4. 装 Playwright / patchright chromium（约 200MB 一次性下载）
5. 引导你从 Chrome 导出 TikTok cookies（**严格 24h 模式必须**）

### 让 Claude 看到这些 skill

**Claude Code CLI / Desktop（plugin，推荐）**：

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

享受标准 plugin 系统（版本管理 + `/plugin upgrade`）。

**Desktop App 手动方式**：

```bash
mkdir -p ~/.claude/skills && cp -r ~/ops-skills/skills/* ~/.claude/skills/
# 完全退出 Claude Desktop（⌘+Q）再打开
```

### 平台支持

| 平台 | 支持度 | 备注 |
|---|---|---|
| **macOS**（Apple Silicon / Intel） | ✅ 100% | 主开发平台 |
| **Linux** | ⚠️ 部分 | Chrome cookies 解密依赖 Chrome 装在标准位置 |
| **Windows** | ❌ 未测 | 建议用 WSL2 跑 Linux 模式 |

### TikTok cookies（tk-template-scout 必须）

TikTok 搜索 / hashtag 页对未登录用户弹登录墙，脚本必须用你 Chrome 真登录账号的 sessionid 才能拿数据。

**推荐导到持久目录**（跨天不被 `/tmp` 清，免去每天重导）：

```bash
# Chrome 先真登录 tiktok.com，然后：
mkdir -p ~/.config/ops-skills
yt-dlp --cookies-from-browser chrome --cookies ~/.config/ops-skills/tiktok-cookies.txt \
  --skip-download --playlist-items 0 'https://www.tiktok.com/@tiktok'

# 验证含 sessionid（真登录的标志）
grep sessionid ~/.config/ops-skills/tiktok-cookies.txt | grep tiktok.com
```

> 脚本（`scout_strict.py` / `grab_viral_challenges.py`）**默认优先读 `~/.config/ops-skills/tiktok-cookies.txt`**，找不到才回落 `/tmp/tiktok-cookies.txt`。导到持久目录后，定时任务每天自动跑不会再因 cookies 丢失而挂。
>
> macOS 导出会弹**钥匙串授权框**，点「始终允许」即可（藏在别的窗口后面就 ⌘+Tab 找一下）。

**Cookies 失效怎么办**（一般 7–30 天）：Chrome 重新登录 tiktok.com，重跑上面导出命令覆盖即可。

---

## 用户配置（跨升级保留）

所有用户级配置放在 `~/.config/ops-skills/`，**plugin 升级时不动**：

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/tiktok-cookies.txt` | TikTok 登录 cookies（持久，脚本优先读这里） | **tk-template 必填** |
| `~/.config/ops-skills/tk-template-scout.yaml` | 飞书 webhook：`feishu_webhook_trend`（us-trend）+ `feishu_webhook_template`（tk） | 否（配了才推飞书） |
| `~/.config/ops-skills/personas.yaml` | 自定义 26 数字角色（us-trend + tk 共用，覆盖默认） | 否 |
| `~/.config/ops-skills/us-trend-history.json` | us-trend 7 天跨天去重指纹库（脚本自建自管） | 自动 |
| `~/.claude/memory/xcmo-session.json` | xcmo 平台 vee_session token | **xcmo-mobile 必填** |

**飞书双 webhook**（两个日报推不同群）：

```yaml
# ~/.config/ops-skills/tk-template-scout.yaml
feishu_webhook_trend: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"     # us-trend 热点日报
feishu_webhook_template: "https://open.feishu.cn/open-apis/bot/v2/hook/yyyyy"  # tk 模板日推
```

**首次配置 xcmo token**：浏览器登录 https://xcmo.ai → F12 → Application → Cookies → 复制 `vee_session` → 告诉 Claude「更新 xcmo token: \<token\>」。

---

## us-trend-scout 用法

```
触发：跟 Claude 说「跑一次热点」/「美区热点」/「us trend」
```

抓**美区 Reddit 24h 真热点**（事件型，非慢趋势），筛**文化趋势**配 26 数字角色，简报 dump 对话 + 推飞书。

### 工作流

1. `scout_reddit.py` 拉 16 个精选 sub 的 24h top **RSS**（`/top/.rss?t=day`）+ Google Trends 侧路 → 2 层闸门（24h 硬过滤 + 主题/source-sub 黑名单）→ 7 天跨天去重 → 按 `rank` 取前 120 候选
2. Claude 端**文化趋势第一道筛**（v5.4，cici 需求）：优先影视娱乐 / meme / 时尚美妆 / 生活方式情绪 / 名人文化；硬社会新闻（政治 / 财经 / 监管）即使能 hot take 也默认 drop
3. 过筛的再走 3 yes 定性判断（24h 内 / 26 角色能写具体仿拍 brief / 能产 1-2 条视频选题）+ 可选 WebSearch 跨平台 enrichment
4. 涌现式输出（通常 8–15 条，质量第一不凑数）→ 每条配 1–3 角色具体 brief → 推飞书

> **为什么走 RSS**：Reddit 已封 `.json` 端点（无 OAuth 一律 403），RSS 是唯一零配置可达端点。代价是没有 ups/comments，热度用 feed 内 `rank` 表达；并发降到 3 + 失败重试防限流。

### 定时执行

```
/schedule create "0 9 * * *" "run skill ops-skills:us-trend-scout"
```

北京每天 9:00（= 美东前一天晚上）。本地 routine 需电脑唤醒才触发（睡眠错过会在唤醒后补跑）。

---

## tk-template-scout 用法

```
触发：跟 Claude 说「跑一次 TK 模板」/「TK 模板日推」/「跑一次 TK 模板 严格 24h」
```

### 严格 24h 模式（主路径）

1. **Step 0 全平台挑战 Top 3**（核心价值，作用 > 细分模板）：Claude WebSearch 找候选挑战 → `grab_viral_challenges.py` 用 Playwright 抓 `/tag/` 样本 + yt-dlp 验证 7 天内真样本
2. **26 人 × 3 关键词 = 78 个查询**：`scout_strict.py` 用 **patchright**（playwright 反检测 fork，过 TikTok 滑块 CAPTCHA）抓 `tiktok.com/search/video`
3. 从 URL 提取 `video_id`，`timestamp = video_id >> 32`（snowflake 解码）做 24h 硬过滤
4. yt-dlp 补 `like_count / title / uploader`，**抗限流重试**（失败率 ≥40% 判定 TikTok 限流 → sleep 后只重试失败的，最多 2 轮）
5. 每 persona 按点赞取 Top 1 → Claude 翻译 `title_cn` + `fanpai_brief` → `render_briefing.py` 渲染（0 命中的 persona 直接跳过不显示）

### 数据源

`--source search` 单源（默认）/ `hashtag` 单源 / `both` 双源融合。实测 search 源偶尔抽风（某些词返回 0 raw），**`both` 双源能把命中翻倍**（hashtag 补 search 漏抓），代价是抓取 ~17 分钟。

```bash
python3 skills/tk-template-scout/scout_strict.py --source both --scrolls 6 --keywords tk_keywords.yaml ...
# --help 看完整参数
```

### 定时执行

```
/schedule create "0 9 * * *" "run skill ops-skills:tk-template-scout"
```

注意 cookies 导到 `~/.config` 持久目录后，定时跑才不会因 `/tmp` 被清而挂。

### 已知限制

- ID 解码假设虽有 sample 验证但非 100% 保险（TikTok 改格式可能静默错）
- 严格 24h 命中率看当天舆论场，24/26 覆盖是常态（部分赛道当天真没 24h 新视频）
- 关键词太长（5+ 词）命中率差，建议简短地道关键词
- TikTok 反爬随时升级 → 预留 1–2 个月修一次脚本的心理预期

---

## sge-blog-watcher 用法

监听 [Social Growth Engineers](https://socialgrowthengineers.com) 博客，发现新文章立刻推飞书群。

```
触发：定时（每 10 分钟轮询）/ 跟 Claude 说「跑一次 sge」
```

- `watch.py` 抓博客列表，对比已推指纹库找增量
- Claude 翻译生成中文标题 + 摘要 + 正文 TL;DR
- `render_card.py` 渲染成飞书卡片（一篇一卡，带原文链接）

```
/schedule create "*/10 * * * *" "run skill ops-skills:sge-blog-watcher"
```

---

## xcmo-mobile 用法

```
触发：跟 Claude 说
  下载 your-email@example.com 2026-05-22 的内容
  拉 your-email@example.com 2026-05-21~2026-05-22 的素材
  mobile share your-email@example.com 2026-05-22
```

Claude 会：调 xcmo API 拉该用户指定日期生成的全部 task → 按 `character_id` 分组下载视频 + 缩略图 → 生成 HTML 站点（总览页 + 每人物详情页）→ 每人物一张二维码 → 起本地 HTTP 服务器（默认 8080）→ 浏览器自动打开。

**手机扫码后**（手机和电脑同 WiFi）：看该人物当天所有视频、长按存相册（iOS）、点 📋 复制文案/标签切到 TikTok 粘贴发布。

**输出位置**：`~/Desktop/xcmo-mobile/<邮箱>/<日期>/site/` ｜ **停服务**：终端 Ctrl+C。

---

## 仓库结构

```
ops-skills/
├── .claude-plugin/
│   ├── plugin.json                 # v5.3.0
│   └── marketplace.json
├── skills/
│   ├── us-trend-scout/
│   │   ├── SKILL.md
│   │   ├── scout_reddit.py         # RSS 拉 16 sub 24h + 2 层闸门 + 7 天去重
│   │   ├── personas.yaml           # 默认 26 数字角色（us-trend + tk 共用）
│   │   └── requirements.txt
│   ├── tk-template-scout/
│   │   ├── SKILL.md
│   │   ├── scout_strict.py         # 严格 24h 主路径：patchright + ID 解码 + yt-dlp 抗限流
│   │   ├── grab_viral_challenges.py# Step 0 全平台挑战抓取 + 7 天验证
│   │   ├── render_briefing.py      # 简报固化渲染（0 命中跳过）
│   │   ├── push_feishu_card.py     # 推飞书卡片
│   │   ├── translate_prompt.md     # title_cn + fanpai_brief 翻译规则
│   │   ├── tk_keywords.yaml         # 26 人各 3 个 TikTok 搜索关键词
│   │   ├── scout.py                # 旧 MVP 模式（WebSearch + yt-dlp，保留备用）
│   │   ├── validate_translated.py
│   │   └── requirements.txt
│   ├── sge-blog-watcher/
│   │   ├── SKILL.md
│   │   ├── watch.py                # 抓博客 + 增量检测
│   │   ├── render_card.py          # 飞书卡片渲染
│   │   ├── translate_prompt.md
│   │   └── requirements.txt
│   └── xcmo-mobile/
│       ├── SKILL.md
│       ├── mobile.py
│       └── templates/              # index.html / character.html / style.css
├── tests/                          # pytest（unit）
├── .github/workflows/ci.yml
├── setup.sh                        # 一键安装（依赖 + cookies）
├── bump-version.sh
├── CHANGELOG.md
├── LICENSE                         # Apache 2.0
└── README.md
```

---

## 开发

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git
cd ops-skills
pip install -r requirements-dev.txt
pytest

# 发新版
./bump-version.sh 5.3.1
$EDITOR CHANGELOG.md
git add -A && git commit -m "chore: release v5.3.1"
git tag v5.3.1
git push && git push --tags
```

## 反馈

issue: [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
