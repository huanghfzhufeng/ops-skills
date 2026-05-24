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

### 一键安装（推荐，**5 分钟**搞定全部依赖 + cookies）

打开 **Mac 终端**（⌘+Space 搜「终端」回车），粘贴：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git ~/ops-skills
cd ~/ops-skills
bash setup.sh
```

`setup.sh` 会自动：

1. 检测平台 / Python / Chrome 是否就绪
2. 装 `yt-dlp`（Homebrew or pip）
3. 装 Python 依赖：`qrcode pillow PyYAML playwright playwright-stealth`
4. 装 Playwright chromium（约 200MB 一次性下载）
5. 引导你从 Chrome 导出 TikTok cookies 到 `/tmp/tiktok-cookies.txt`（**严格 24h 模式必须**）

跑完会提示你"在 Claude 说『跑一次 TK 模板』即可"。

### 然后让 Claude 看到这些 skill

**Desktop App 用户**：

```bash
mkdir -p ~/.claude/skills && cp -r ~/ops-skills/skills/* ~/.claude/skills/
# 完全退出 Claude Desktop（⌘+Q）再打开
```

**Claude Code CLI 用户**：

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

享受标准 plugin 系统（版本管理 + `/plugin upgrade`）。

### 平台支持

| 平台 | 支持度 | 备注 |
|---|---|---|
| **macOS**（Apple Silicon / Intel） | ✅ 100% | 主开发平台 |
| **Linux** | ⚠️ 部分 | Chrome cookies 解密依赖 Chrome 装在标准位置 |
| **Windows** | ❌ 未测 | 建议用 WSL2 跑 Linux 模式 |

### 依赖明细（如果你不用 setup.sh 想自己装）

```bash
# 通用工具
brew install yt-dlp                                              # tk-template-scout 抓 TikTok 元数据
# 或 pip3 install --user --break-system-packages yt-dlp

# Python 包
pip3 install --user --break-system-packages \
  qrcode pillow PyYAML playwright playwright-stealth

# Playwright headless Chrome（200MB 一次性）
playwright install chromium

# 必须：Chrome 真登录 tiktok.com 后导出 cookies
yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt \
  --skip-download --quiet 'https://www.tiktok.com/@tiktok'

# 验证 cookies 含 sessionid（真登录的标志）
grep sessionid /tmp/tiktok-cookies.txt | grep tiktok.com
```

**为什么 cookies 这步必须**：TikTok 搜索 / hashtag 页对未登录用户弹登录墙。脚本必须用你 Chrome 真登录账号的 sessionid 才能访问数据。如果你 Chrome 只是浏览过 TikTok 没登录，cookies 里没 sessionid，脚本会报错退出 + 给清楚提示。

**Cookies 失效怎么办**（一般 7-30 天）：在 Chrome 重新登录 tiktok.com，然后：

```bash
rm /tmp/tiktok-cookies.txt && bash ~/ops-skills/setup.sh
```

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

```
触发：跟 Claude 说「跑一次 TK 模板」/「TK 模板日推」/「tk-template」
```

**v4.4.0 默认走 search 单源**（贴用户原 spec：「按关键词在 TikTok 搜索过去 24h」）。

### 数据流（5 步）

1. 读 `tk_keywords.yaml`（26 人 × 3 关键词 = 78 个查询）
2. Playwright headless Chrome 抓 `https://www.tiktok.com/search/video?q=<keyword>&publish_time=1&sort_type=2`（带你 Chrome cookies）
3. 从视频 URL 提取 `video_id`，用 `timestamp = video_id >> 32`（snowflake 解码）做 24h 硬过滤
4. yt-dlp 给筛剩的 URL 补 `like_count / title / uploader`
5. 每 persona 按 like_count 取 Top 3 → `render_briefing.py` 渲染成简报（格式代码固化）

### 输出格式（render_briefing.py 强制）

```
TK模板日推 | 5月24日（周日）

Sophie (@sophie.fits2)

The people who feel the most luxurious are rarely trying the hardest. | 9.6K赞 | https://www.tiktok.com/@iamshaniakhan/video/7643106369498909966
#OldMoneyStyle #menswatches #watches #Menswear #QuietLuxury | 232赞 | https://www.tiktok.com/@jamesashford.london/video/7643131720560069910
...

Ava (@ava.glow3)

(24h 内 0 命中)

...（26 人按固定顺序展开）
```

### 性能

- 78 search query × Playwright 4 worker = **3 分钟**
- 134 候选 × yt-dlp 6 并发 = **1-2 分钟**
- 总耗时：**约 4-5 分钟**
- 单次实测：26 人 23 人有数据 / 3 人 0 命中 / 最大爆款 23.6 万赞

### 备用数据源（高级用户）

如果默认 search 命中率不够，可以试 `hashtag` 单源或 `both` 双源（实测两源重叠仅 21%，是互补关系）：

```bash
# 显式跑 hashtag 单源
python3 skills/tk-template-scout/scout_strict.py --source hashtag --keywords ...

# 双源融合
python3 skills/tk-template-scout/scout_strict.py --source both --keywords ...
```

`scout_strict.py --help` 看完整参数。

### 定时执行

```
/schedule create "0 1 * * *" "run skill ops-skills:tk-template-scout"
```

UTC 01:00 = 北京 09:00。注意 cookies 7-30 天会失效，定时跑要监控失败邮件。

### 已知限制

- ID 解码假设虽有 sample 验证但不是 100% 保险（TikTok 改格式可能静默错）
- Cross-persona dedup 是启发式（"候选最少 persona 优先"），不是精确归属
- 关键词太长（5+ 词）命中率差，建议改简短关键词（如 `data science` 比 `data science life` 更地道）
- TikTok 反爬随时可能升级 → 心里要有 1-2 个月修一次脚本的预期

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
│   │   ├── scout.py               # 旧 MVP 模式：WebSearch + yt-dlp
│   │   ├── scout_strict.py        # 主路径：Playwright search 24h + ID 解码 + yt-dlp 补点赞
│   │   ├── render_briefing.py     # 简报格式固化渲染（代码级强制，防 Claude 即兴拼）
│   │   └── requirements.txt       # PyYAML + playwright + playwright-stealth
│   └── xcmo-mobile/
│       ├── SKILL.md
│       ├── mobile.py              # 核心脚本
│       └── templates/             # HTML 模板
│           ├── index.html
│           ├── character.html
│           └── style.css
├── tests/                          # 100 个 pytest（unit）
├── .github/workflows/ci.yml
├── bump-version.sh
├── setup.sh                        # 一键安装脚本（依赖 + cookies）
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
