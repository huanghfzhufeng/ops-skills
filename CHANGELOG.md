# Changelog

本项目所有重要变更都会记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [4.0.0] - 2026-05-22

### Changed (Breaking)

- **xcmo-download → xcmo-mobile 完全替换**。旧的「按 batch ID 下载 + 外部/内部分组打 docx+zip」流程废弃，替换为新流程：
  - **输入变了**：从「batch ID 列表 + 外部/内部分类」改成「邮箱 + 日期」
  - **输出变了**：从 `.docx + .zip` 改成「可手机扫码访问的本地 HTML 站」
  - **核心场景变了**：从「打包发给南宁合作方」改成「电脑下载 → 手机扫码 → 直接发抖音/TikTok」

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

老用户：以前用 `下载 batch xxx 外部` 的工作流不再支持。改用 `下载 luyuyue@liao.com 2026-05-22 的内容`。

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
