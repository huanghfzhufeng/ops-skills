# Changelog — marketplace 级别

本文件记录 **huanghfzhufeng marketplace 架构层**的变更（新增/删除 plugin、目录结构调整、共享工具）。

**单个 plugin 的功能变更**请看对应 plugin 自己的 CHANGELOG：

- [plugins/tiktok-matrix/CHANGELOG.md](plugins/tiktok-matrix/CHANGELOG.md)

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [2.0.0] - 2026-05-21

### Changed (Breaking)

- **架构重构成多 plugin 模式**。本仓库从「单 plugin `ops-skills`」转变为「marketplace `huanghfzhufeng` 装多个独立 plugin」
- 第一个 plugin 是 `tiktok-matrix`（继承原 ops-skills 的所有 skill 和功能）
- **Breaking**：原安装命令 `/plugin install ops-skills@ops-skills` 已废弃，新命令是 `/plugin install tiktok-matrix@huanghfzhufeng`
- **Breaking**：skill 命名空间从 `ops-skills:us-trend-scout` 变成 `tiktok-matrix:us-trend-scout`
- 老用户迁移：先 `/plugin uninstall ops-skills@ops-skills` 再按新流程装

### Added

- `plugins/` 子目录承载多个 plugin（当前 1 个，预留位置）
- 每个 plugin 自己的 plugin.json、README、CHANGELOG、requirements.txt
- 仓库根 README 改成 marketplace 总览
- `bump-version.sh` 升级支持指定 plugin：`./bump-version.sh tiktok-matrix 1.0.1`
- CI 适配多 plugin 校验

### Architecture Rationale

详见 [docs/PLUGIN_DESIGN_GUIDE.md](docs/PLUGIN_DESIGN_GUIDE.md) 的「多 plugin 架构」段。简单说：
- 各 plugin 独立版本管理，改一个不影响其他
- 用户按需安装，依赖最小化
- 加新 domain（如未来的 koubao）只需新增 plugin 目录，不影响已装用户

## [1.1.0] - 2026-05-21（已被 v2.0.0 重构吸收）

> 本版本的功能已全部迁移到 [plugins/tiktok-matrix/CHANGELOG.md](plugins/tiktok-matrix/CHANGELOG.md) 的 v1.0.0 段。详细 changelog 见那里。
>
> 简版：config 升级丢失 P0 修复 + 27 个 pytest + GitHub Actions CI + CHANGELOG + bump-version.sh + README Quick Start + 扩 keywords。

## [1.0.0] - 2026-05-21（已被 v2.0.0 重构吸收）

> 本版本的功能已全部迁移到 [plugins/tiktok-matrix/CHANGELOG.md](plugins/tiktok-matrix/CHANGELOG.md) 的 v1.0.0 段。
>
> 简版：初版发布两个 skill（us-trend-scout + xcmo-download），加 plugin.json + marketplace.json + LICENSE + README。

[2.0.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/huanghfzhufeng/ops-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/huanghfzhufeng/ops-skills/releases/tag/v1.0.0
