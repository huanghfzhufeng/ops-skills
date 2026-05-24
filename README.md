# ops-skills

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

美区 TikTok 矩阵号运营自动化工具集。[huanghfzhufeng](https://github.com/huanghfzhufeng) 出品。

## 包含的 Skill

| Skill | 干啥 | 触发 |
|---|---|---|
| **us-trend-scout** | 每天自动抓美区 TikTok 热点 → 配 26 数字角色出创意 → 简报到对话 | 「跑一次热点」 |
| **tk-template-scout** | 26 人 × 3 词搜 TikTok 真实视频 → yt-dlp 抓点赞 / 时间 / 文案 → 每人 Top 3 模板供运营仿拍 → 简报到对话（可选推飞书）。两种模式：MVP（WebSearch + yt-dlp，便宜）/ 严格 24h（Playwright + hashtag + ID 解码，真当天数据） | 「跑一次 TK 模板」 / 「跑一次 TK 模板 严格 24h」 |
| **xcmo-mobile** | 按邮箱+日期从 xcmo 拉视频 → 按人物分组 → 起本地服务 + 二维码 → 手机扫码看视频/复制文案 | 「下载 \<邮箱\> \<日期\>」|

---

## 安装

### 方式 1：Desktop App 用户（最简）

打开 **Mac 终端**（⌘+Space 搜「终端」回车），粘贴这一段：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git /tmp/ops-skills && \
mkdir -p ~/.claude/skills && \
cp -r /tmp/ops-skills/skills/* ~/.claude/skills/ && \
pip3 install --user --break-system-packages qrcode pillow 2>/dev/null; \
echo "✅ 装好，请完全退出 Claude Desktop App（⌘+Q）再打开"
```

跑完**完全退出 Claude Desktop App**（⌘+Q）再打开。

### 方式 2：Claude Code CLI 用户

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

享受标准 plugin 系统（版本管理 + `/plugin upgrade`）。

### Python 依赖

```bash
pip3 install qrcode pillow              # xcmo-mobile 用
brew install yt-dlp                     # tk-template-scout 用（也可 pip install yt-dlp）
```

us-trend-scout 全用 WebSearch + 标准库，无额外依赖。tk-template-scout 需要 yt-dlp + Chrome 已登录 tiktok.com（cookies 用于绕反风控）。

---

## 用户配置（跨升级保留）

所有用户级配置统一放在 `~/.config/ops-skills/` 或 `~/.claude/memory/`，**plugin 升级时这些目录不动**：

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/personas.yaml` | 自定义 26 数字角色（覆盖默认，us-trend-scout + tk-template-scout 共用）| 否 |
| `~/.config/ops-skills/tk-keywords.yaml` | 自定义每人的 TikTok 搜索关键词 | 否 |
| `~/.config/ops-skills/tk-template-scout.yaml` | 飞书 webhook（推 TK 模板日推到群） | 否 |
| `~/.claude/memory/xcmo-session.json` | xcmo 平台 vee_session token | **xcmo-mobile 必填** |

**首次配置 xcmo token**：
1. 浏览器登录 https://xcmo.ai
2. F12 → Application → Cookies → 复制 `vee_session` 值
3. 告诉 Claude：「更新 xcmo token: \<粘贴你的 token\>」

---

## us-trend-scout 用法

```
触发：跟 Claude 说「跑一次热点」/「美区热点」/「us trend」
```

6 路并行 WebSearch → 筛 5-8 条具体可证实的热点 → 每条配 1-2 个数字角色 → 简报直接 dump 到对话（飞书推送已下线）。

**定时执行**：

```
/schedule create "0 1 * * *" "run skill ops-skills:us-trend-scout"
```

UTC 01:00 = 北京 09:00。

---

## tk-template-scout 用法

两种模式按口令选：

### MVP 模式（默认，便宜快）

```
触发：跟 Claude 说「跑一次 TK 模板」/「TK 模板日推」/「tk-template-scout」
```

26 人 × 3 词并行 WebSearch 拿 TikTok 视频 URL → yt-dlp + Chrome cookies 抓官方网页元数据 → 按 timestamp 过滤 24h（不足 3 条降级到 7 天）→ 按点赞排序每人取 Top 3 → 简报。

**前置**：
1. `brew install yt-dlp`（或 `pip install yt-dlp`）
2. Chrome 登录过 `https://www.tiktok.com`（任意账号，cookies 用于绕反风控）

**数据时效**：因为 Google 索引 TikTok 滞后，"过去 24h" 硬约束往往无法满足，多数会降级到 7d 或全量高赞。对"运营找模板做选题"够用。要真当天数据用下面的严格 24h 模式。

### 严格 24h 模式（v4.3.0 新增，能拿到真当天数据）

```
触发：跟 Claude 说「跑一次 TK 模板 严格 24h」/「tk 严格 24h」/「tk-template 严格模式」
```

Playwright headless Chrome 抓 26 关键词对应的 TikTok hashtag 页 → 用 `video_id >> 32` snowflake 解码 timestamp 硬过滤 24h → yt-dlp 补点赞/标题 → cross-persona dedup → Top 3 + 低赞自动标注。

**前置**（在 MVP 模式基础上多两步）：

```bash
# 1) 装 Playwright + 拉 chromium（约 200MB，一次性）
pip3 install -r ~/.claude/skills/tk-template-scout/requirements.txt
playwright install chromium

# 2) Chrome 必须**真实登录** tiktok.com，然后手动导一次 cookies：
yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt \
  --skip-download --quiet 'https://www.tiktok.com/@tiktok'
# 检查 cookies 含 sessionid：
grep -E '^\.tiktok\.com.*sessionid\s' /tmp/tiktok-cookies.txt
```

**实测性能**：78 hashtag × 4 worker = Playwright 3 分钟 + yt-dlp 3 分钟 = **6 分钟**，26 人全部拿到 24h 内 Top 3。

**已知限制**：cross-persona dedup 启发式不完美；ID 解码假设虽有 sample 验证但不是 100% 保险；关键词 → hashtag 自动转换粗暴。详见 `skills/tk-template-scout/SKILL.md` "关键限制" 段。

### 定时执行（任一模式）

```
/schedule create "0 1 * * *" "run skill ops-skills:tk-template-scout"
```

---

## xcmo-mobile 用法

```
触发：跟 Claude 说
  下载 your-email@example.com 2026-05-22 的内容
  拉 your-email@example.com 2026-05-21~2026-05-22 的素材
  your-email@example.com 2026-05-22
  mobile share your-email@example.com 2026-05-22
```

Claude 会：
1. 调 xcmo API 拉该用户在指定日期生成的全部 task
2. 按 `character_id` 分组下载视频 + 缩略图
3. 生成 HTML 站点（总览页 + 每人物一个详情页）
4. 每个人物生成一张二维码
5. 起本地 HTTP 服务器（默认端口 8080）
6. 浏览器自动打开 `http://localhost:8080`
7. 提示你**手机和电脑在同一 WiFi 下扫人物二维码**

**手机扫码后能干啥**：
- 看该人物当天的所有视频
- 长按视频 → 存到相册（iOS）
- 点 📋 复制文案/标签 → 切到 TikTok App 粘贴 → 发布

**输出位置**：`~/Desktop/xcmo-mobile/<邮箱>/<日期>/site/`

**停服务**：终端 Ctrl+C。

---

## 仓库结构

```
ops-skills/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   ├── us-trend-scout/
│   │   ├── SKILL.md
│   │   └── personas.yaml          # 默认 26 数字角色（两 skill 共用）
│   ├── tk-template-scout/
│   │   ├── SKILL.md
│   │   ├── tk_keywords.yaml       # 26 人各 3 个 TikTok 搜索关键词
│   │   ├── scout.py               # MVP 模式：WebSearch + yt-dlp
│   │   ├── scout_strict.py        # 严格 24h 模式：Playwright + hashtag + ID 解码
│   │   └── requirements.txt       # PyYAML + playwright + playwright-stealth
│   └── xcmo-mobile/
│       ├── SKILL.md
│       ├── mobile.py              # 核心脚本
│       └── templates/             # HTML 模板
│           ├── index.html
│           ├── character.html
│           └── style.css
├── tests/                          # 31 个 pytest
├── .github/workflows/ci.yml
├── bump-version.sh
├── requirements.txt                # qrcode + pillow
├── requirements-dev.txt
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
./bump-version.sh 4.0.1
$EDITOR CHANGELOG.md
git add -A && git commit -m "chore: release v4.0.1"
git tag v4.0.1
git push && git push --tags
```

## 反馈

issue: [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
