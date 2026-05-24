# Changelog

本项目所有重要变更都会记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
