# Changelog

本项目所有重要变更都会记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

—

## [1.1.0] - 2026-05-21

### Added

- **user-level 配置目录** `~/.config/ops-skills/`，存放跨升级保留的用户配置：
  - `~/.config/ops-skills/us-trend-scout.yaml`（飞书 webhook URL）
  - `~/.config/ops-skills/personas.yaml`（自定义 26 数字角色，覆盖 plugin 自带默认）
- **pytest 单测套件** `tests/test_download.py` — 27 个测试覆盖 `sanitize_filename` / `video_filename` / `parse_csv_list` 三个纯函数
- **GitHub Actions CI** `.github/workflows/ci.yml` — push/PR 自动校验 JSON schema + Python 语法 + pytest
- **`bump-version.sh`** — 一行命令同步 plugin.json + marketplace.json 的 version 字段
- **CHANGELOG.md**（本文件）
- **`requirements-dev.txt`** — 列 pytest 等开发依赖
- **`pytest.ini`** — pytest 配置 + marker 注册
- README 加 **Quick Start** 段（5 分钟首次上手）+ 截图占位

### Changed

- **us-trend-scout 配置加载逻辑改为 user-level 优先**：先读 `~/.config/ops-skills/us-trend-scout.yaml`，找不到再 fallback 到 plugin 自带的 `config.example.yaml`。**修复 1.0.0 的 P0 bug：用户 webhook URL 会在 plugin upgrade 时丢失**
- `personas.yaml` 同样支持 user override，方便自定义数字角色
- 扩 `plugin.json` + `marketplace.json` 的 `keywords`：加 `douyin` / `tiktok-trends` / `content-creator` / `mcn` / `automation` / `lark` / `social-media` / `video-ops`，提升 marketplace 搜索曝光

### Fixed

- **[P0] config.yaml 升级丢失** — 配置文件放 plugin 目录里，`/plugin upgrade` 后新版 cache 是干净目录，用户的 webhook URL 会丢。改成 user-level 路径后跨升级保留

## [1.0.0] - 2026-05-21

### Added

- 初版发布，包装为 Claude Code plugin
- **us-trend-scout** skill — 6 路并行 WebSearch 抓美区 TikTok 热点，配 26 个数字角色出创意，推飞书群
- **xcmo-download** skill — 从 xcmo.ai 批量下载 batch 产物，按外部/内部分组打 docx + zip
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` 让 `/plugin install` 一键安装
- Apache License 2.0
- README、requirements.txt

[Unreleased]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/huanghfzhufeng/ops-skills/releases/tag/v1.0.0
