# Changelog

本项目所有重要变更都会记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [4.8.1] - 2026-05-26

### Changed - tier fallback 取代 track 分层（贴回原 spec）

- **`scout_strict.py` 时长过滤改 tier fallback**：原 v4.8.0 按 `track` 字段分（fashion/健身 → ≤30s，段子/科技 → ≤15s），但用户原 spec 是「优先 ≤15s，没有再扩 ≤30s」—— 是 fallback 关系不是分层关系
  - 删 `TRACK_MAX_DURATION_DEFAULTS` 常量 + `_resolve_max_duration` 函数
  - 加 `_filter_records()` 抽出单 tier 过滤逻辑（时长 + 竖版 + self-exclude）
  - `build_report` 改：先尝试 `tight_max=15s`，0 命中才扩 `relaxed_max=30s`
  - 每 persona 输出 `tier_used`: `tight` / `relaxed` / `none`
  - CLI 参数 `--max-duration` → `--tight-max` + `--relaxed-max`
- **`render_briefing.py` 加 tier 标签**：每条视频前缀 `[15s]` 或 `[30s 兜底]`，让运营一眼看出哪条是扩搜的
- **顶部全局说明改成**：`📏 时长规则：优先 ≤15s [15s]，0 命中时扩到 ≤30s 标 [30s 兜底] | 仅竖版 | 排除自家 26 号`

### Changed - 4 个 handle 修正（xcmo source of truth + TikTok 双重验证）

用 xcmo API（`GET /api/characters`）拿 27 真实 handle + yt-dlp 直接验证账号存在性，修正 4 处错的：

- `priya.handle`: `@priya.setup` ❌（不存在）→ **`@priya.apps`**
- `riley.handle`: `@riley.fitt` ❌（不存在）→ **`@riley.fits01`**
- `leila.handle`: `@evelyn.pilates` ❌（旧过期）→ **`@leila.pilates1`**
- `ro.handle`: `@eli.hacks` ❌（旧过期）→ **`@ro.hacks0`**

修正后 26 yaml handle ↔ xcmo 真实账号 100% 对齐。self-exclude 黑名单也对了，下次再有 `@priya.apps` 视频会被正确过滤掉。

### Changed - us-trend-scout 输出格式固化「带来源链接」

- 之前用户反馈「热点要带链接」没落地到 SKILL.md，下次定时跑可能忘
- 现在 `Step 6` + `输出格式` + 「文体约束」三处都写死要求：**每条细分趋势必须带 1-2 个权威来源链接（行业报告 / 主流媒体）**，数字 / YoY / 百分比可追溯
- 简报模板改 3 行结构：① 趋势描述（带 `**加粗**`）② 来源链接行 ③ 人设配对

### Verified - 端到端真跑（5/26）

- `scout_strict.py` 跑出 22/26 命中（v4.7.0 是 14/26）：20 人 `[15s]` + 2 人 `[30s 兜底]` + 4 人 0 命中
- `grab_viral_challenges.py` 跑出 6 verified + 1 rejected。Top 3 = CORTIS REDRED 96 万赞官方版 1 天前 + DWP2 8.9K 1.6 天前 + Be Her Ella Langley 3K 0.4 天前
- us-trend-scout 5 路 WebSearch 真跑，简报每类带 2-3 个权威源链接
- 两份简报推送双 webhook：trend `StatusCode:0` ✅、template card markdown 加粗 / 链接渲染正常
- 单测 126 全绿

## [4.8.0] - 2026-05-26

### Added

- **`skills/tk-template-scout/push_feishu_card.py`**（≈140 行）—— 飞书 **富文本卡片**（interactive markdown）推送脚本，两个 skill 共用。
  - 第一行 → 卡片 header title（自动选配色：「模板」→ 浅蓝、「热点/趋势」→ 蓝）
  - 其余 → markdown body，渲染 `**bold**` / `[link](url)` / emoji
  - **修 v4.6.0 痛点**：纯文本 webhook 不解析 markdown，简报里 `**xxx**` 直接显示成星号
  - 上限 ~30K 字符（飞书 markdown 元素），单份简报 5-8K 富余

### Changed - 分层时长过滤 + 竖版 + 自家黑名单（scout_strict.py）

- **`scout_strict.py` 时长硬过滤改分层**（v4.6.0 统一 ≤15s 砍掉太多 fashion/健身视频，12/26 人 0 命中）：
  - `fashion_beauty` + `health_fitness` → **≤30s**
  - `entertainment` + `tech_ai` → **≤15s**
  - 走 `personas.yaml` 已有 `track` 字段，零额外配置
  - `--max-duration N` 仍可覆盖分层（旧用法兼容）
- **新增竖版硬过滤**：抓 `width`/`height`，默认排除横版（`--no-vertical-filter` 关闭）。避免推荐运营复制不了的横版视频。
- **新增 self-exclude**：默认排除 `personas.yaml` 里 26 个 handle 的自家素材（`--no-self-exclude` 关闭）。修「Priya 推荐 @priya.apps 自家视频」类问题。

### Changed - 拆 viral 挑战块，去重两份简报

- **`us-trend-scout/SKILL.md`** 8 路 query → **5 路**（删 3 路 cross-niche viral content）；输出格式删「🔥 本周可蹭趋势」段，**简报开头直接进 5 大细分趋势**。理由：viral 挑战 Top 3 由 tk-template-scout 用 `grab_viral_challenges.py` 真实点赞 + 时间窗硬过滤自动选，权威来源在 TK 模板那边；两份简报顶部同步推送同 3 条挑战是冗余。

### Changed - render_briefing.py 标清楚硬过滤阈值

- 简报顶部新增一行 `📏 时长硬过滤：穿搭/彩妆/健身/健康 ≤30s，段子/泛娱乐/科技/AI ≤15s | 仅竖版 | 排除自家 26 号`。让运营一眼看清当前过滤口径。
- 0 命中提示从 `(24h 内 0 命中 ≤15s 模板)` 改为 `(24h 内 0 命中 ≤Xs 竖版模板)`，X 按 persona track 动态填入。

### Changed - personas.yaml handle 同步真实账号

- `priya.handle`: `@jake.setup` → `@priya.setup`
- `riley.handle`: `@finn.fits2` → `@riley.fitt`
- 其余 24 个 handle 等用户提供完整新列表后一次性更新。

### Fixed

- 飞书简报 `**xxx**` 显示成原始星号（plain text webhook 不解析 markdown）→ 改用 interactive card 解决
- 「前三个热点」两份简报重复（trend Top 3 = template Top 3）→ trend 简报只推 5 大细分趋势

## [4.7.4] - 2026-05-25

### Reverted - 撤回 v4.7.3 的 `--share` cloudflared tunnel 模式

经实际使用反馈：本地 LAN IP 模式已经够用，不需要给"发给别人"这个场景过度工程化。v4.7.3 加的整套 cloudflared 集成（新依赖、新 flag、新 onboarding 章节、新失败处理）属于 over-engineering，把"自己手机扫自己电脑"这个清晰用例搞复杂了。整体撤回。

- `--share` flag 删
- `spawn_cloudflared_tunnel()` / `CLOUDFLARED_INSTALL_HINT` / `CLOUDFLARED_URL_PATTERN` 删
- `_platform_detach_kwargs()` 删（inline 回 `spawn_background_server`）
- `render_site_files()` 签名回到 `lan_ip + port`
- non-share box 里 "💡 给别人发链接？跑 --share" 提示删
- `import shutil` / `import time`（顶部）删，`time` 回到 background 分支内部 import
- `SKILL.md` 删「给别人发公网链接（--share 模式）」整章 + 参数列表里 `--share` 行 + 触发关键词 share 部分 + 依赖段 cloudflared 行

保留的功能（v4.7.2 引入）：跨平台 server detach（Windows 关终端不死）+ HTTP 自检 + 跨平台 stop 命令 + Windows 防火墙提示。

## [4.7.2] - 2026-05-25

### Fixed - xcmo-mobile Windows 兼容性 + 后台 server 健康自检

- **关掉 cmd / PowerShell 窗口后 HTTP server 还能继续跑（Windows 兼容性 bug 修复）**：原 `spawn_background_server` 用 `start_new_session=True` —— 这是 POSIX 专属（调 `setsid`），**Windows 上 Python 会静默忽略**，子进程不会真正脱离父 console。后果：用户在 Windows 跑完 `python mobile.py --background` 后**一关终端窗口，HTTP server 立刻死**，手机扫码就看到 `Safari cannot open the page because the network connection was lost`。改成跨平台分支：Windows 上用 `creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`，POSIX 上保留 `start_new_session=True`。
- **加 `--background` 模式启动后 HTTP 自检**：spawn 子进程后 sleep 1.5s 立刻 GET `http://localhost:<port>/` 一次确认 server 真的在听。失败时打印明确的 "⚠ 子进程已起但本地 HTTP 自检失败" 框 + 日志路径 + 常见原因（端口占用 / 防火墙拦 / 子进程立刻退出），并以 exit 1 退出 —— 让 Claude 这一侧能立刻把错误转述给用户，不再让用户白扫一个根本没人监听的二维码。
- **跨平台 stop 命令**：输出 box 里"停止"行在 macOS/Linux 显示 `kill <PID>`，Windows 显示 `taskkill /F /PID <PID>`。
- **Windows 用户专属提示**：检测到 `sys.platform == "win32"` 时输出 box 自动追加防火墙必须勾【专用】+【公用】两项的提醒，附 PowerShell 一键修复 `Set-NetConnectionProfile ... NetworkCategory Private`。
- **`skills/xcmo-mobile/SKILL.md` 加 Windows 章节**：onboarding 段补 "3. Windows 用户额外注意"，写清楚防火墙弹框两项都要勾、否则手机扫码会看到 "connection was lost"。

### Files

- `skills/xcmo-mobile/mobile.py`：加 `check_server_alive()`；`spawn_background_server()` 平台分支 `creationflags` vs `start_new_session`；main `--background` 分支加自检 + 跨平台 stop + Windows 提示 + 失败时 exit 1
- `skills/xcmo-mobile/SKILL.md`：首次使用段加 "3. Windows 用户额外注意"

## [4.7.1] - 2026-05-25

### Fixed - xcmo-mobile 手机分享站 UX 三连修

- **人物名字按真实 display name 渲染**：之前用 `character_id` slug 当显示名，跟实际人物经常错位 —— `character_id=mia` 实际人物是 `Iris`，`character_id=jake` 实际是 `leo`，`character_id=carlos` 实际是 `ezra`，`character_id=kiki` 实际是 `riley`，等等。改成从 `asset.name` 的 `"<选题> × <人物名>"` 右半部分提取真 display name，HTML（首页卡片 h2、详情页 title/h1）全部用 display name；文件路径继续用 slug 保稳定（视频实际就落在 `videos/<slug>/` 下）。
- **首页人物卡片整张可点击 + 桌面 hover 提示**：原本只有 `<h2><a>` 一行可点击，且没有视觉提示用户不知道能点。改成整张卡片包 `<a class="character-card">`，桌面 `@media (hover: hover)` 加 `translateY(-2px)` + 蓝色边框 + 深阴影 + `cursor: pointer` 明示可点；移动端用 `@media (hover: hover)` 屏蔽 sticky hover，触屏不沾染。
- **清掉三处误导文案**：
  - 首页 footer 删 `"📱 手机扫人物二维码 → 直接看该人物的视频和文案"`（多余说明）和 `"⏹ 电脑终端 Ctrl+C 停服务"`（background 模式 Ctrl+C 根本停不掉，得 `kill <PID>`，文案纯误导）
  - 人物卡片删 `"📱 手机扫码看 · 💻 点击进入"`（卡片本身已有 hover 视觉提示 + cursor，文案冗余）
  - 只留真正有用的一行：`"⚠ 手机和电脑必须连同一 WiFi 才能扫码访问"`

### Files

- `skills/xcmo-mobile/mobile.py`：加 `extract_display_name()` + `display_name_for()` 工具函数，`render_character_card` / `render_index` / `render_character_page` 全部接 display_name
- `skills/xcmo-mobile/templates/index.html`：footer 简化
- `skills/xcmo-mobile/templates/character.html`：`{{CHARACTER_ID}}` → `{{CHARACTER_DISPLAY}}`（title + h1）
- `skills/xcmo-mobile/templates/style.css`：`.character-card` 改成 `<a>` 友好样式 + `@media (hover: hover)` 桌面 hover 抬起+边框

## [4.7.0] - 2026-05-25

### Changed - 中性 query（拔掉最后一层 hardcode 偏好）

- **`us-trend-scout/SKILL.md` Step 3 三路 viral query 去 "non-dance"**：
  - 旧（v4.6.0）：`TikTok viral non-dance content ...` / `TikTok non-dance viral ...` / `TikTok hottest non-dance trend ...`
  - 新（v4.7.0）：`TikTok viral content cross-niche ...` / `TikTok cross-niche participatory format ...` / `TikTok hottest cultural moment ... all genres participation`
  - **理由**：v4.6.0 用 `non-dance` 排除舞蹈，本质上是把"已知答案的反面"当作 query。当周真实数据自证 —— Apple Dance / Espresso Dance 用 grab_viral_challenges.py 跑出的最近样本分别是 51 天 / 475 天前，**它们是真过气，不是被"非舞蹈"过滤掉**。CORTIS Wiggle-Ears 是 K-pop 舞蹈，反而是当周最大 cross-niche moment（180 万赞 6.8 天前）。中性 query + 真实时间窗硬过滤，能让 viral 程度和跨圈层度自己说话。
- **`tk-template-scout/SKILL.md` Step 0 同步去 "non-dance"**，文案改成 cross-niche participatory 锚定。
- **新增禁止规则**：在 us-trend-scout 「绝对禁止」清单里加第 4 条 —— "**不要 hardcode '排除' 什么（如 non-dance）→ 这也是预设偏好，是 hardcode 的反向版本**"。

### Verified

- 用 grab_viral_challenges.py 跑 7 个中性候选（含 dance + skit + carousel + 美妆实测），数据自动选出真 viral：CORTIS Wiggle-Ears（K-pop 舞蹈 180 万赞 6.8 天前）、Little Birdie Duo（双人 skit 10.4K 赞 4.3 天前）、Wear Test Beauty（美妆实测 5.7K 赞 6.1 天前）。Apple Dance / Espresso Dance 因 >7 天硬过滤自动 reject。
- 两份简报（trend + template）端到端跑通并推送双 webhook 验证 `{"StatusCode":0}` success。

## [4.6.0] - 2026-05-25

### Added

- **`skills/tk-template-scout/grab_viral_challenges.py`**（260 行）—— 自动化全平台挑战样本抓取 + 时间窗验证脚本。
  - 输入：Claude WebSearch 后的候选 hashtag 数组（JSON via stdin / file）
  - 流程：Playwright 抓 hashtag 页 → yt-dlp 验证每个样本的点赞 / 时长 / 发布时间 → 硬过滤 ≤ N 天前 → 按点赞排序取 Top 1
  - 输出：`{"verified": [...], "rejected": [{"reason": "all samples > 7 days old (closest 219 days)"}, ...]}`
  - **防止重复犯"拿过期样本充数 viral 挑战"的错**（之前手工流程犯过：把 Group 7 / and Emily 的几个月前样本当 5 月新趋势）
- **`skills/tk-template-scout/validate_translated.py`**（180 行）—— 协议层验证 translated.json schema。
  - 检查 viral_challenges 必填字段、sample_url 必须 https、fanpai_brief 长度
  - 检查每条 video 的 title_cn / fanpai_brief 字段、长度、句首格式
  - 退出码区分 `0 完美` / `1 fatal` / `2 warnings 可降级`
  - 防 Claude 翻译漂移
- **`tests/test_validate_translated.py`**（17 个新单测）—— 覆盖协议验证

### Changed - SKILL.md（核心修正：抽象 query + 防回声室）

- **`us-trend-scout/SKILL.md` Step 3**：8 路 WebSearch 全部抽象化
  - **绝对禁止 hardcode**：公司名 / 例子名 / 产品类型 / 挑战形态
  - **只用**：类目 + 时间 + 地区 + 平台 + 抽象趋势词（shift / movement / phenomenon / surge / cultural / behavioral）
  - 新 query 实测有效：拿到 "65% Gen Z 自认创作者"、"comfort culture replaces hustle" 等具体趋势（不是泛言）
- **`tk-template-scout/SKILL.md` Step 0**：挑战 query 改抽象 + 加 7 天样本验证强制
  - 锚定一个核心："**病毒级非舞蹈内容**"（viral non-dance content）
  - 必须调 grab_viral_challenges.py 验证样本时间窗（≤ 7 天），不通过的候选自动丢弃
- **设计原则段（新增到两个 SKILL.md）**：广 → 严 → 具 三层漏斗
  ```
  Step 3 query 层（广）：抽象趋势词，不预设答案
       ↓
  Step 4 筛选层（严）：在搜索结果挑具体可证实
       ↓
  Step 5 配对层（具）：基于人设的具体仿拍 brief
  ```

### Why this matters (深层教训)

v4.5.x 出过 3 个典型偏离：

1. **hardcode 公司名**（query 写 `Anthropic Meta Microsoft`）→ 搜索引擎只能返回这几家，新趋势找不到
2. **hardcode 挑战类型**（query 写 `dance / format / meme`）→ dance 在搜索权重过高，结果全是编舞
3. **拿过期样本充数**（"and Emily" 52 天前 / "Group 7" 219 天前 当 5 月 viral 挑战）→ 没去抓样本验证

**根因**：我把"上次找到的具体东西"当作"下次 query 的锚定" = 回声室。

**修正**：
- query 抽象化（**渔网越广越好**）
- 筛选锋利化（**在搜索结果里挑具体证据**）
- 自动化验证（grab_viral_challenges.py 强制样本时间窗）
- 协议层守门（validate_translated.py 卡 schema）

### Implementation

- 新代码：grab_viral_challenges.py + validate_translated.py + test_validate_translated.py
- 工程化：之前手工流程（WebSearch → 抓样本 → 验证时间窗）现在自动化
- ci.yml：py_compile 加 grab_viral_challenges.py + validate_translated.py
- 测试覆盖：109 → **126 passed**（17 新测试）


## [4.5.0] - 2026-05-24

### Added

- **`skills/tk-template-scout/translate_prompt.md`**：固化翻译 + 仿拍 brief 生成规则。Claude 主线执行 SKILL.md 时按此 prompt 一次性翻译所有 video title + 生成仿拍建议，写到 `translated.json`。不调外部 API，0 成本。
  - 翻译规则：保留专有名词英文（TikTok / hashtag / 品牌名 / 配乐 / 地名）；金句用「」标；标视频形式（vlog / 段子 / 教程等）；20-40 中文字
  - 仿拍 brief：句首 `<Persona> 拍...`，30 字内，必须含场景 + 动作 + 钩子
  - 6 个 title 翻译例子 + 6 个 fanpai 例子（运营 1 秒可读 + 直接可执行）
- **`render_briefing.py` 加 `title_cn` / `fanpai_brief` 字段支持**：
  - 优先用 `title_cn`（Claude 翻译后），fallback `title`（raw 英文）
  - `fanpai_brief` 存在时在视频条目后加一行 `→ <brief>`
- **`tests/test_render_briefing.py` 加 4 个测试**：
  - `test_title_cn_takes_priority_over_title`
  - `test_fallback_to_raw_title_when_no_title_cn`
  - `test_fanpai_brief_shown_as_arrow_line`
  - `test_fanpai_brief_empty_no_arrow_line`

### Changed

- **6 个 persona 关键词优化**（基于 v4.4.1 实测数据）：
  - `ava`: `high fashion / couture / fashion week` → `vogue runway / met gala / red carpet`（解决 24h 0 命中）
  - `priya`: `tech wellness / data science life / health tech` → `women in tech / data scientist / tech career`（解决 24h 0 命中）
  - `eleanor`: `sorority life / college girl / campus aesthetic` → `college vlog / dorm decor / bama rush`（解决暑假 0 命中）
  - `clara`: `korean fashion / k beauty / seoul style` → `k drama makeup / glass skin / kbeauty haul`（low_heat 93 赞）
  - `silver`: `NYC it girl / Manhattan aesthetic / PR girl life` → `nyc aesthetic / it girl / manhattan`（low_heat 364 赞）
  - `jade`: `editorial fashion / luxury aesthetic / fashion editorial` → `street style / milan fashion week / paris fashion week`（low_heat 15 赞）
- **`~/.config/ops-skills/tk-template-scout.yaml` 改双 webhook 格式**：
  ```yaml
  feishu_webhook_trend: "..."     # us-trend-scout 推这里
  feishu_webhook_template: "..."  # tk-template-scout 推这里
  ```
- **tk-template-scout/SKILL.md 重写 Step 6/7**：
  - Step 6 加 "Claude 翻译 + 生成仿拍 brief" 子步骤（必做）
  - Step 6.5 渲染 `translated.json`（不是 `result.json`）
  - Step 7 改双 webhook 推送（`feishu_webhook_template`）
- **us-trend-scout/SKILL.md 复活推飞书**（Step 7.5）：推 `feishu_webhook_trend`
- **`.github/workflows/ci.yml`**：加 `bash -n setup.sh` 语法验证

### Why this matters

v4.4.x 简报输出英文 raw title + 不带仿拍建议，运营拿到要自己再翻译再脑补拍法。
v4.5.0 起：
1. **简报即开即用**：中文标题 + 仿拍 brief 一行就懂能不能仿
2. **飞书自动推**：跟 Claude 说"跑一次 TK 模板"→ 跑完 5 分钟内简报自动到飞书群，运营不用手工 curl
3. **关键词更对路**：6 个 low_heat persona 改地道 hashtag，预计 24h 命中率从 23/26 提升到 26/26

### Translation cost

0（Claude 主线翻译，不调外部 API）。每次跑约多耗 30 秒翻译 + 30 秒 brief 生成。

## [4.4.1] - 2026-05-24

### Added

- **`setup.sh`** 一键安装脚本。`bash setup.sh` 6 步搞定全部依赖：
  1. 平台检测（macOS 完整支持 / Linux 部分 / Windows 不支持）
  2. Python 3.10+ 检测
  3. Chrome 检测（macOS 检 `/Applications/Google Chrome.app`）
  4. 装 yt-dlp（Homebrew 优先，fallback pip）
  5. 装 Python 依赖：qrcode pillow PyYAML playwright playwright-stealth
  6. 装 Playwright chromium（~200MB）
  7. 引导用户手动登录 TikTok + 自动导出 cookies + 验证含 sessionid

### Changed

- **README 重写"安装"段**：
  - 头条改成"一键安装"（`bash setup.sh`）
  - 加完整依赖明细（之前漏 PyYAML / playwright / playwright-stealth / chromium）
  - 加"首次配置 TikTok cookies"教程（之前完全没提，新用户必踩坑）
  - 加平台支持矩阵（macOS ✅ / Linux ⚠️ / Windows ❌）
  - 加 cookies 失效处理（一句 `rm + bash setup.sh` 重跑）
- **README tk-template-scout 用法段**重写到 v4.4.0：
  - 删除已被 v4.4.0 移除的"两种模式"描述（MVP / 严格 24h 不再并列）
  - 改成"默认 search 单源 + 备用 hashtag/both（高级用户）"
  - 加 render_briefing.py 输出格式示例（贴用户原 spec）
  - 加性能数据（4-5 分钟 / 23/26 命中）
  - 加 4 条已知限制
- **README 仓库结构图**加 `setup.sh` 和 `render_briefing.py`

### Why this matters

打包给非技术运营 / 同事用之前，README 漏 5 个坑（依赖、cookies、登录态、用法过时、跨平台），首次跑会卡 1-2 小时。setup.sh 把所有自动化的步骤封装，对方只需要：

```
git clone ... && bash setup.sh
```

5 分钟搞定（其中 200MB chromium 下载占 2-3 分钟）。

## [4.4.0] - 2026-05-24

### Added

- **`skills/tk-template-scout/render_briefing.py`** — 简报格式固化脚本。把 `scout_strict.py` 的 JSON 输出渲染成严格按用户原 spec 格式的简报文本。
  - 用法：`python3 scout_strict.py ... | python3 render_briefing.py` 或 `render_briefing.py --json result.json`
  - 强制 26 人按 `DISPLAY_ORDER` 固定顺序展示
  - Persona 名格式 `Name (@handle)`、视频条目 `标题 | 点赞 | URL` 三段式
  - 点赞中文化 `1.2万赞 / 3.5K赞 / 234赞`
  - 0 命中 persona 仍显示 segment 标题 + 「(24h 内 0 命中)」
  - 不带 emoji 分组、不带统计行、不带 ⚠️ low_heat 标、不带"数据说明"段
- **`tests/test_render_briefing.py`** — 29 个单测覆盖：fmt_likes / clean_title / capitalize_persona / format_briefing / 日期映射 / 26 人顺序 / 装饰物排除

### Changed

- **数据源默认从 `both` 改回 `search`**（贴用户原 spec：「按关键词在 TikTok 搜索过去 24h」）
  - `scout_strict.py --source` 默认值 `both` → `search`
  - 想用 hashtag / both 须显式指定 `--source hashtag` 或 `--source both`
  - 实测 search 单源 24h 内 23/26 persona 命中、134 候选、4 分钟完成；hashtag/双源仍作为可选数据源保留
- **SKILL.md 重写"输出格式"段 + Step 6 拼简报**：删掉所有 Claude 即兴拼简报的格式描述，改成"调 render_briefing.py 拿成品输出，不要二次加工"。
  - 原因：实测靠 Claude 读 SKILL.md 拼简报会反复偏离用户原 spec（emoji 分组、统计行、⚠️ 标记、"模板""仿拍"行被自动加上）。代码固化后下游不管谁调用都拿到 100% 一致格式
- `.github/workflows/ci.yml`：`py_compile` 加 `render_briefing.py`

### Why this matters

3 次连续偏离用户原始需求：
1. v4.3.0 严格 24h 模式默认走 hashtag 页（不是用户要的搜索页）
2. v4.4.0 设计阶段我提议双源融合 → 用户拒绝，要求纯 search
3. v4.3.x 跑出的简报被 Claude 加上 emoji 分组、统计行、⚠️ 等装饰

修法：所有"格式 / 数据源"等可被 Claude 偏移的决策，**代码固化 + 单测覆盖**。
SKILL.md 只描述"调什么脚本"，不描述"输出长什么样"。

### Verified

- 100 pytest passed（43 旧 + 28 scout_strict + 29 render_briefing）
- 端到端跑 `scout_strict --source search` 78/78 抓取 0 errors，4 分钟完成
- `render_briefing.py --json result.json` 输出贴用户 spec 格式，0 装饰物

## [4.3.1] - 2026-05-24

### Changed

按用户最新人设分组优化 `tk_keywords.yaml` 的 26 人关键词。分组只在 yaml 注释里说明，scout 仍按 26 人扁平结构跑（用户明确不需要分组功能，避免过度设计）。

**上班账号（6 人，高质量内容输出 + 欧美时尚 / F1 / 科技事件方向）：**

- `avery`: `clean girl routine / LA lifestyle / healthy eating` → `womensfashion / europeanstreetstyle / f1fashion`
- `spencer`: `productivity tools / quiet life / optimizer` → `mensfashion / corporatestyle / f1paddock`
- `ava`: `beauty review / makeup tutorial / PR unboxing` → `highfashion / couture / fashionweek`
- `mia`: `tech review / app recommendation / growth tools` → `workingmom / worklifebalance / momlife`
- `ro`: `life hacks / unboxing tech / PM productivity` → `techworker / siliconvalley / technews`
- `ryan`: `meal prep / protein diet / engineer gym` → `softwareengineer / techindustry / developerlife`

**养号账号（20 人，按各自新标签调整）：**

- `caden / mason / eleanor` 近原配置，微调
- `jade` 心理 → editorial fashion 高级时尚
- `emma` 书单 → healthy cooking 健康饮食
- `nari` ABG → gen z fashion 年轻潮流
- `joey` 橄榄球 nutrition → high school sports 体育幽默
- `kai` 加 NYC college
- `jesse` cinematic → indie / vintage 文艺时尚
- `sophie` heiress → art gallery 艺术圈
- `ezra` men fashion → corporate humor 职场幽默
- `riley` 微调
- `clara` nurse → korean fashion 韩系
- `leila` pilates → trad wife 家居
- `max` walking → gym humor 健身幽默
- `charlotte` AI tools → tech girl + ai beauty 科技美妆
- `priya` data science → tech wellness 科技健康
- `iris` 删 work drama 加 career girl
- `leo` emotional → gym tok 健身
- `silver` 用户未提及，保留原 NYC PR girl 配置

### Verified

跑 `scout_strict.py` 端到端验证新关键词命中率：

- 78/78 hashtag 抓取 0 errors，5790 raw URL
- 315 候选 → 314 yt-dlp 元数据补全（99.7%）
- 26/26 persona 拿到 Top 3
- ID 解码 5/5 sample 全过
- cross-persona dedup 解决 6 个冲突
- 耗时 5.5 分钟

**新关键词命中爆款样本（24h 内）：**

- `emma` healthycooking 20.8 万赞
- `joey` footballhumor 5.7 万赞
- `max` gymhumor 4 万赞
- `avery` womensfashion 3.3 万赞

**3 个 persona 命中率偏低（已知）：**

- `leila` 301 赞（trad wife 赛道 24h 真没爆款，正常现象）
- `silver` 376 赞（用户未提，保留原配置）
- `priya` 118 赞 + 只 2 候选（`techwellness / datasciencelife` 太冷门）→ 下一版可试 `datascience / wellnesstech` 更地道

### Not done (explicit decision)

- **"上班 / 养号"分组功能**：用户明确说不需要，避免过度设计。yaml 注释里说明分组就够了。
- **"事件订阅"功能**（F1 / 文化时尚 / 科技 / 教育事件触发推送）：等用户立项再做（属于 us-trend-scout v2 方向）。

## [4.3.0] - 2026-05-24

### Added

- **tk-template-scout 严格 24h 模式**（解决 MVP 模式拿不到真当天数据的痛点）：
  - `skills/tk-template-scout/scout_strict.py`：Playwright 抓 TikTok hashtag 页 + `video_id >> 32` snowflake 解码 timestamp 硬过滤 24h + yt-dlp 补点赞 / 标题 / uploader
  - SKILL.md 加"选择模式"段 + 完整"严格 24h 模式"小节：触发词 / 命令 / 输出结构 / 简报特殊规则 / 关键限制诚实标注
  - `requirements.txt` 加 `playwright>=1.40` + `playwright-stealth>=2.0`
  - 用户首次跑前需 `pip install -r requirements.txt && playwright install chromium`（约 200MB）
- **触发词**：用户说"跑一次 TK 模板 严格 24h" / "tk 严格 24h" / "tk-template 严格模式" 启用
- `tests/test_scout_strict.py`：23 个 pytest unit 测试（纯函数无 I/O），覆盖 keyword_to_hashtag / check_cookies_have_session / cross_persona_dedup / build_report / load_netscape_cookies / ID 解码数学

### Technical decisions

- **走 TikTok hashtag 页（`/tag/<hashtag>`）而非 search 页**：实测 `/search?publish_time=1` filter 是 hint 不是硬约束，会混入旧高相关性视频；hashtag 页按时间倒序更可靠。78 hashtag 跑出来 26 人全部拿到 24h 内真实数据。
- **Video ID snowflake 解码**：`timestamp = video_id >> 32` 是 TikTok ID 高 32 位编码 unix 秒。比 yt-dlp 抓 timestamp 快 100 倍（无网络请求），秒级精度。同时加 sample 二次验证（`verify_id_decoding_sample`）：抽 5 个 sample 走 yt-dlp 拿真 timestamp，差异 > 1h 报警，超过半数 mismatch 强警告。
- **Cross-persona dedup**：同视频被多 persona 抓到时归给候选数最少的（让冷门赛道优先获得素材）。简报里不会出现"三个不同人设推荐同一个视频"的尴尬。
- **Browser context 复用**：4 worker × 1 context（不是 78 次新建 context），跑 78 hashtag 从 6 分钟降到 3 分钟。
- **Stealth 双层兜底**：playwright-stealth 可用就用，不可用也跑基础 init script（`navigator.webdriver` / `plugins` / `languages`）。
- **零自动导 cookies**：探针 URL 会过期导致首次跑挂，改成明确报错 + 提示用户手动跑 `yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt --skip-download 'https://www.tiktok.com/@tiktok'`。
- **检测 cookies 是否真登录**：load 后查 `sessionid` 是否在 `.tiktok.com` domain 下，不在就报错（用户的 Chrome 必须真登录 TikTok，不只是浏览过）。
- **检测 cookies 失效**：所有 78 hashtag raw URL 总和为 0 → 登录墙诊断 + 退出码 3。
- **保留"凑 Top 3"行为 + 自动标低赞**：`--min-likes-warn 500`（可配），Top1 < 阈值的 persona 在 JSON 里标 `low_heat_warning: true`，简报输出层要明示"24h 内无爆款"。

### Changed

- `plugin.json` + `marketplace.json` description 加严格 24h 模式描述
- `README.md`：tk-template-scout 用法段加严格模式触发 + 前置；仓库结构图加 `scout_strict.py` / `test_scout_strict.py`
- `.github/workflows/ci.yml`：`py_compile` 路径加 `skills/tk-template-scout/scout_strict.py`

### Known limitations (诚实标在 SKILL.md 里)

- ID 解码假设 `timestamp = video_id >> 32` 没真正二次验证生产环境长期稳定性，万一 TikTok 改 ID 格式可能静默错（已加 sample 验证 + warning 缓解，但不是 100% 保险）。
- Cross-persona dedup 是"候选数最少优先"的启发式，不是完美方案。
- 关键词 → hashtag 自动转换粗暴（空格删掉小写），5+ 词的关键词（如 `skincare routine heiress`）常 0 命中。

## [4.2.0] - 2026-05-22

### Added

- **新 skill `tk-template-scout`** — 26 人 × 3 词 TikTok 真实视频搜索 + 点赞排序 + Top 3 模板供运营仿拍：
  - `skills/tk-template-scout/SKILL.md`：触发词、8 步工作流、输出格式、文体约束、`/schedule` 集成
  - `skills/tk-template-scout/tk_keywords.yaml`：26 个 persona 各 3 个英文搜索关键词，按"赛道核心 + 人设场景 + 模板风格"配
  - `skills/tk-template-scout/scout.py`：核心抓取脚本，并行调 yt-dlp + `--cookies-from-browser chrome` 抓 TikTok 视频元数据，按 timestamp 过滤 24h（不足 3 条降级到 7 天再降级到全量），按 like_count 排序取 Top 3
  - `skills/tk-template-scout/requirements.txt`：PyYAML 依赖

### Technical decisions

- **数据源走 yt-dlp + Chrome cookies**（非第三方付费 API）：yt-dlp 抓的是 TikTok 官方网页 SSR 数据，等同浏览器访问。Mac 上 `--cookies-from-browser chrome` 自动读已登录 cookies 绕反风控，单视频抓取实测 100% 成功率。
- **WebSearch → URL 收集 → yt-dlp 抓详情** 的两阶段架构：因为 TikTok tag/搜索页直接 yt-dlp 抓需要 mobile API（`app_info`），但单视频 URL 抓没问题。WebSearch `site:tiktok.com <keyword>` 拿 URL 是稳定路径。
- **数据时效降级**：Google 索引 TikTok 视频比发布晚几天到几周，「过去 24h」硬约束往往无法满足。脚本自动降级到 7d → 全量高赞并在简报里标注 `age_tag`。对运营找模板做选题够用。
- **接口层抽象** `scout.py::fetch_metadata`：未来要严格实时 24h，加 Playwright fallback 跑 TikTok 搜索页（带 publish_time filter），代价是装 chromium ~200MB。
- **复用 us-trend-scout 的 personas.yaml**：单一数据源，新 skill 只新增 `tk_keywords.yaml` 关键词文件。
- **飞书 webhook 复用 `~/.config/ops-skills/tk-template-scout.yaml`**：与 us-trend-scout 解耦，未来 us-trend-scout 恢复推送时互不影响。

### Fixed

- `.github/workflows/ci.yml` 里 `py_compile skills/xcmo-download/download.py` 引用了 v4.0.0 已重命名的旧路径。改成 `skills/xcmo-mobile/mobile.py skills/tk-template-scout/scout.py`。

### Changed

- `plugin.json` + `marketplace.json` description 加 tk-template-scout 段
- `README.md`：Skill 表格加一行 / 用户配置表加三行 / 加 tk-template-scout 用法段 / 仓库结构图同步

## [4.1.0] - 2026-05-22

### Removed (Breaking — 但用户主动要求)

- **us-trend-scout 下线「推飞书」功能**。简报现在直接 dump 到对话给用户看。
  - 删 SKILL.md 的 Step 8（推飞书 curl 调用整段）
  - 删 `config.example.yaml`（飞书 webhook 配置模板）
  - 改 SKILL.md description：去掉「飞书推送」字眼
  - 改 SKILL.md「首次使用」段：从「配 webhook URL」改成「无需配置即可用」
  - 改 Step 1：只读 `personas.yaml`，不再读 `us-trend-scout.yaml`

### Changed

- plugin.json + marketplace.json description 同步：把「配 26 数字角色推飞书」改成「配 26 数字角色出创意，简报输出到对话」
- README.md：us-trend-scout 描述、用户配置表、安装命令同步更新
- `plugin.json::keywords` 里的 `feishu` / `lark` **保留**（marketplace SEO，未来如果恢复推送功能这两个 keyword 仍相关）

### Rationale

用户当前阶段不再需要推飞书。简报直接出现在 Claude 对话里更直接，省一道配置门槛。未来如果需要恢复推送（飞书 / 微信 / Telegram / 邮件），加回来即可。

### Migration

老用户：原 `~/.config/ops-skills/us-trend-scout.yaml` 文件可保留（脚本不再读它，无害），或手动删除：
```bash
rm ~/.config/ops-skills/us-trend-scout.yaml
```

## [4.0.3] - 2026-05-22

### Added

- **`--background` 参数** — Claude 在 Bash 里跑应该用这个：
  1. 拉数据 + 下载视频 + 生成 HTML/QR
  2. 起 `python3 -m http.server` 子进程（`start_new_session=True` 脱离会话）
  3. **自动 `webbrowser.open()` 在用户默认浏览器打开站点**
  4. mobile.py 主进程立刻退出（不阻塞 Bash / Claude）

  实测：跑完 1.4 秒返回，子进程在后台继续 serve，浏览器自动打开。

### Changed

- `serve_site` 函数拆成 `serve_site_foreground`（前台阻塞）+ `spawn_background_server`（后台 detach）
- **SKILL.md 明确告诉 Claude 必须用 `--background`** — 否则脚本会阻塞，Claude 无法继续

### Rationale

之前 Claude 在 Bash 里跑 `mobile.py` 不加 `--no-serve` 会卡在 `httpd.serve_forever()`，Bash 命令永远不返回。需要手动用 `--no-serve` + 手动起 server + 手动 open 浏览器（三步）。`--background` 一步搞定 + 自动开浏览器，符合用户期望「跑完自动给我打开网页」。

## [4.0.2] - 2026-05-22

### Fixed

- **文档表述统一为 TikTok**——之前文档/代码注释里几处写「抖音/TikTok」或「抖音」，但本项目用户做的是**美区 TikTok**（不是国内抖音）。统一改成 TikTok：
  - README.md（用法描述）
  - CHANGELOG.md（历史段也修了）
  - skills/xcmo-mobile/SKILL.md（description + 典型工作流）
  - skills/xcmo-mobile/mobile.py（注释）

注：`plugin.json` 的 `keywords` 里仍保留 `douyin`（marketplace SEO 用，不影响功能；可能引来国内做相似事的人）。

## [4.0.1] - 2026-05-22

### Added

- **`--refresh-only` 参数** — 切换 WiFi 后用：跳过 API 调用和视频下载，从本地缓存（`<site>/_cache.json`）秒级重生二维码 + HTML（实测 0.16 秒搞定）
- **box 框框输出** — `✅ 完成` 和「服务已启动」用 ASCII 框包住，URL/端口/路径一目了然
- **缓存机制** — 每次正常跑会写 `<site>/_cache.json` 保存 by_character 数据，给 `--refresh-only` 用

### Fixed

- **端口被占用时的混淆** — 之前 mobile.py 静默切换到下一个端口，用户不知道。现在 `find_free_port` 找到非请求端口时显式打印「请求 X 用了 Y」
- **HTML 写入静默失败** — 之前如果磁盘满 / 权限错，可能没写出文件但程序继续打印 "✅ 完成"。现在每写一个文件后 stat 检查大小 ≥100 字节，否则立刻 RuntimeError + 非 0 退出
- **xcmo-mobile 合并复制按钮** — 文案 + 标签合并成一个「📋 一键复制」按钮，复制出来是「文案 + 空行 + 标签」格式，粘到 TikTok 描述框直接发布

### Changed

- mobile.py 重构为更小函数：`fetch_by_character` / `download_all_videos` / `render_site_files` / `resolve_out_dir`，便于测试和理解
- SKILL.md 加 `--refresh-only` 用法说明 + WiFi 切换处理指引

## [4.0.0] - 2026-05-22

### Changed (Breaking)

- **xcmo-download → xcmo-mobile 完全替换**。旧的「按 batch ID 下载 + 外部/内部分组打 docx+zip」流程废弃，替换为新流程：
  - **输入变了**：从「batch ID 列表 + 外部/内部分类」改成「邮箱 + 日期」
  - **输出变了**：从 `.docx + .zip` 改成「可手机扫码访问的本地 HTML 站」
  - **核心场景变了**：从「打包发给南宁合作方」改成「电脑下载 → 手机扫码 → 直接发 TikTok」

### Added

- **新 skill `xcmo-mobile`**（`skills/xcmo-mobile/`）：
  - `mobile.py`：按邮箱+日期拉 xcmo 数据 → 按 `character_id` 分组下载视频 + 缩略图 → 生成 HTML 站 + 二维码 → 起本地 HTTP 服务
  - `templates/`：3 个文件（index.html / character.html / style.css）—— Apple 风格响应式设计
  - 二维码：每个人物一张 PNG，扫码直接到该人物详情页
  - 复制功能：文案/标签一键复制（含 HTTP 协议下的 fallback）
- **新依赖**：`qrcode` + `pillow`（生成二维码 PNG）
- **API 支持**（验证 OK）：
  - `/api/auth/me`（拿 scope_id）
  - `/api/scopes/{scope_id}/members`（邮箱 → user_id）
  - `/api/tasks?date_from=X&date_to=Y&submitted_by_user_id=Z`（拉用户当日 task）
  - `/api/assets?asset_id=X`（拿 asset 完整数据，含 `thumb_url` 用作缩略图）

### Removed

- `skills/xcmo-download/`（旧 skill，已被 xcmo-mobile 替代）
- `tests/test_download.py`（被 `tests/test_mobile.py` 替换，31 个测试覆盖）
- `python-docx` 依赖（不再生成 docx）

### Migration

老用户：以前用 `下载 batch xxx 外部` 的工作流不再支持。改用 `下载 your-email@example.com 2026-05-22 的内容`。

## [3.0.0] - 2026-05-22

### Changed (Breaking)

- **架构简化回单 plugin**。v2.0.0 试过的「marketplace + 多 plugin 子目录」模式 over-engineering——对当前只有 1 个 plugin 的项目不划算。回到 v1 风格：仓库根 = plugin 根。
- skills/、tests/、requirements.txt 从 `plugins/tiktok-matrix/` 移回仓库根
- marketplace name 改回 `ops-skills`（=plugin name），install 命令变回 `ops-skills@ops-skills`
- skill 命名空间从 `tiktok-matrix:us-trend-scout` 改回 `ops-skills:us-trend-scout`

### Removed

- `plugins/tiktok-matrix/` 子目录层级（移回根）
- `docs/PLUGIN_DESIGN_GUIDE.md`（502 行 meta 设计指南，仓库不需要写指南给别人）
- 双 CHANGELOG 结构（合并成根 CHANGELOG）
- bump-version.sh 的多 plugin 参数（简化回单参数 `./bump-version.sh <version>`）
- CI 的多 plugin 校验逻辑（简化）

### Retained from v2.0.0

保留了 v1.1.0 → v2.0.0 期间所有有价值的工程改进：
- ✅ user-level 配置目录 `~/.config/ops-skills/`（跨升级保留）
- ✅ 27 个 pytest 单测
- ✅ GitHub Actions CI（简化版）
- ✅ LICENSE / README / CHANGELOG / bump-version.sh
- ✅ 13 个 keywords

### Migration

老用户：
```
/plugin uninstall tiktok-matrix@huanghfzhufeng       # 卸掉 v2 装的
/plugin marketplace remove huanghfzhufeng            # 移除 v2 marketplace
/plugin marketplace add huanghfzhufeng/ops-skills    # 重加（同 GitHub 路径）
/plugin install ops-skills@ops-skills                # 装 v3
```

朋友新装（Desktop App 用户）：直接见 README 的安装方式。

## [2.0.0] - 2026-05-21（已被 v3.0.0 简化吸收）

> 试过的「marketplace + 多 plugin」架构。当时为了"未来加 koubao 等更多 plugin"而做，但实际只有 1 个 plugin，over-engineering。v3.0.0 回退到单 plugin。

主要尝试：
- 改 marketplace name 为 `huanghfzhufeng`，plugin 改名为 `tiktok-matrix`
- 加 `plugins/tiktok-matrix/` 子目录
- 加 `docs/PLUGIN_DESIGN_GUIDE.md`
- bump 脚本支持指定 plugin 名

## [1.1.0] - 2026-05-21

### Added

- **user-level 配置目录** `~/.config/ops-skills/`，跨升级保留：
  - `~/.config/ops-skills/us-trend-scout.yaml`（飞书 webhook URL）
  - `~/.config/ops-skills/personas.yaml`（自定义 26 数字角色）
- **pytest 单测套件** 27 个测试覆盖 `download.py` 的 `sanitize_filename` / `video_filename` / `parse_csv_list`
- **GitHub Actions CI** 自动校验 plugin schema + version 一致性 + 跑 pytest
- **`bump-version.sh`** 一行同步 plugin.json + marketplace.json 的 version
- **CHANGELOG.md**（本文件）
- **README Quick Start**（5 分钟首次上手）

### Fixed

- **[P0] config.yaml 升级丢失** — 配置文件原放 plugin 目录里，`/plugin upgrade` 后用户的 webhook URL 会丢。改成 user-level 路径后跨升级保留

### Changed

- 扩 `keywords` 从 5 个到 13 个：加 `douyin` / `tiktok-trends` / `content-creator` / `mcn` / `automation` / `lark` / `social-media` / `video-ops`

## [1.0.0] - 2026-05-21

### Added

- 初版发布，包装为 Claude Code plugin
- **us-trend-scout** skill — 6 路并行 WebSearch 抓美区 TikTok 热点，配 26 数字角色出创意，推飞书群
- **xcmo-download** skill — 从 xcmo.ai 批量下载 batch 产物，按外部/内部分组打 docx + zip
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` 让 `/plugin install` 一键安装
- Apache License 2.0
- README、requirements.txt

[3.0.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/huanghfzhufeng/ops-skills/releases/tag/v1.0.0
