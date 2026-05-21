# huanghfzhufeng marketplace

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[huanghfzhufeng](https://github.com/huanghfzhufeng) 的 Claude Code plugin marketplace。每个 plugin 独立装配、独立版本管理。

## 当前包含的 plugin

| Plugin | 版本 | 简介 | 安装 |
|---|---|---|---|
| [tiktok-matrix](plugins/tiktok-matrix/) | v1.0.0 | 美区 TikTok 矩阵号运营工具集（热点抓取 + xcmo 批次下载）| `/plugin install tiktok-matrix@huanghfzhufeng` |

未来计划加：`koubao`（口播自动化）、`xiaohongshu`（小红书运营），等等。

## 添加 marketplace（一次性）

在 Claude Code 里跑：

```
/plugin marketplace add huanghfzhufeng/ops-skills
```

这一步把 `huanghfzhufeng` 这个 marketplace 注册到本地。之后所有 plugin 装/卸/升都走这一个 marketplace。

## 装具体 plugin

```
/plugin install tiktok-matrix@huanghfzhufeng
```

装完去对应 plugin 的 README 看怎么用：[tiktok-matrix/README.md](plugins/tiktok-matrix/README.md)。

读法：「**从 huanghfzhufeng 这家店装 tiktok-matrix 这个 plugin**」。

## 升级

```
/plugin upgrade tiktok-matrix
```

社区 plugin **默认不自动升级**——必须主动跑。

## 仓库结构

```
ops-skills/                          ← 本仓库（marketplace 物理位置）
├── .claude-plugin/
│   └── marketplace.json             ← marketplace 元数据 + plugin 目录索引
├── plugins/
│   └── tiktok-matrix/                ← 每个 plugin 一个目录
│       ├── .claude-plugin/
│       │   └── plugin.json           ← plugin 自身元数据
│       ├── skills/
│       │   ├── us-trend-scout/
│       │   └── xcmo-download/
│       ├── tests/                    ← plugin 自己的测试
│       ├── README.md                 ← plugin 自己的文档
│       ├── CHANGELOG.md              ← plugin 自己的变更日志
│       └── requirements.txt
├── docs/PLUGIN_DESIGN_GUIDE.md       ← ⭐ 想做自己的 plugin？看这份
├── .github/workflows/ci.yml          ← 共享 CI（校验所有 plugin）
├── bump-version.sh                   ← 共享工具（指定 plugin 名 bump）
├── pytest.ini                        ← 共享 pytest 配置
├── requirements-dev.txt              ← 共享开发依赖
├── CHANGELOG.md                      ← marketplace 级变更（架构层）
├── LICENSE                           ← 共享 Apache 2.0
└── README.md                         ← 本文件
```

**关键区分**：
- 仓库根的 `CHANGELOG.md` / `README.md` 是 **marketplace 层**（架构变动、新增 plugin）
- 每个 `plugins/*/` 内的 `CHANGELOG.md` / `README.md` 是 **该 plugin 的**（具体功能变动）

## 设计指南

📖 **[docs/PLUGIN_DESIGN_GUIDE.md](docs/PLUGIN_DESIGN_GUIDE.md)** — 想做自己的 Claude Code plugin？这份指南包含心智模型 + 6 份直接抄的模板。本仓库就是按这份指南组织的参考实现。

## 开发

```bash
# clone + 跑测试
git clone https://github.com/huanghfzhufeng/ops-skills.git
cd ops-skills
pip install -r requirements-dev.txt
pytest

# 给某个 plugin 发新版
./bump-version.sh tiktok-matrix 1.0.1     # 同步改 plugin.json + marketplace.json
$EDITOR plugins/tiktok-matrix/CHANGELOG.md
git add -A && git commit -m "feat(tiktok-matrix): release v1.0.1 — <一句话>"
git tag tiktok-matrix-v1.0.1
git push && git push --tags
```

## 反馈

issue: [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
