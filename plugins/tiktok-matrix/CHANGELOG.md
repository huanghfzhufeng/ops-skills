# Changelog — tiktok-matrix

本 plugin 的变更记录。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

> 历史：本 plugin 在 v1.0.0 之前以 `ops-skills` 名义存在于仓库根目录，发布过 v1.0.0 和 v1.1.0。在仓库 v2.0.0 重构（多 plugin 架构）后独立为 `tiktok-matrix` plugin，继承所有功能并从 v1.0.0 重新计数。完整仓库级变更见 [仓库根 CHANGELOG](../../CHANGELOG.md)。

## [1.0.0] - 2026-05-21

继承自原 `ops-skills` plugin v1.1.0 的所有功能：

### Skills 包含

- **us-trend-scout** — 6 路并行 WebSearch 抓美区 TikTok 热点，配 26 数字角色出创意，推飞书群
- **xcmo-download** — 从 xcmo.ai 批量下载 batch 产物，按外部/内部分组打 docx + zip

### 用户配置位置（跨升级保留）

- `~/.config/ops-skills/us-trend-scout.yaml`（飞书 webhook URL）
- `~/.config/ops-skills/personas.yaml`（自定义数字角色）
- `~/.claude/memory/xcmo-session.json`（xcmo session token）

### 工程化

- 27 个 pytest 单测覆盖 download.py 的纯函数
- GitHub Actions CI（plugin schema + version 一致性 + pytest）
- bump-version.sh 工具一键同步双 JSON 版本

[1.0.0]: https://github.com/huanghfzhufeng/ops-skills/releases/tag/tiktok-matrix-v1.0.0
