# ops-skills

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Plugin Version](https://img.shields.io/badge/plugin-v1.1.0-green)](CHANGELOG.md)

运营自动化 Claude Code skill 集合，围绕「美区 TikTok 矩阵号」一条业务线：

- **us-trend-scout** — 每天自动抓美区 TikTok 热点，配 26 个数字角色出具体创意，推飞书群
- **xcmo-download** — 从 [xcmo.ai](https://xcmo.ai) 批量下载 batch 产物（视频 + 文案 + 标签），按「外部 / 内部」分组打包

## Quick Start（5 分钟上手）

需要 [Claude Code](https://docs.claude.com/en/docs/agents/claude-code/overview)。

```bash
# 1) 装 plugin（在 Claude Code REPL 里跑）
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills

# 2) 装 Python 依赖
pip install python-docx

# 3) 配置 us-trend-scout 的飞书 webhook（一次性，跨升级保留）
mkdir -p ~/.config/ops-skills
curl -sL https://raw.githubusercontent.com/huanghfzhufeng/ops-skills/main/skills/us-trend-scout/config.example.yaml \
  > ~/.config/ops-skills/us-trend-scout.yaml
$EDITOR ~/.config/ops-skills/us-trend-scout.yaml   # 填飞书 webhook URL

# 4) 跑一次试试热点
# 在 Claude Code 里跟 Claude 说：
跑一次热点
# → 6 路并行抓热点 → 配 26 角色 → 推飞书（看群里）

# 5) （可选）配 xcmo session token，准备下载 batch
# 浏览器登录 xcmo.ai → F12 → Application → Cookies → 复制 vee_session 值
# 在 Claude Code 里说：
更新 xcmo token: <你的 token>
```

## 安装

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

第 1 行用 `<owner>/<repo>` 注册 marketplace；第 2 行 `<plugin-name>@<marketplace-name>` 装具体 plugin。

装完两个 skill 会以 `ops-skills:us-trend-scout` / `ops-skills:xcmo-download` 命名空间出现，触发关键词都已写在各自 `SKILL.md` 的 `description` 里。

### Python 依赖

xcmo-download 用到 `python-docx`：

```bash
pip install -r requirements.txt
# 或单装
pip install python-docx
```

us-trend-scout 全用 WebSearch + 标准库，无额外依赖。

### 升级

```
/plugin upgrade ops-skills
```

社区 plugin 默认**不自动升级**——必须用户主动跑。详见 [CHANGELOG.md](CHANGELOG.md) 看每版改了啥。

## 用户配置（跨升级保留）

所有用户级配置统一放在 `~/.config/ops-skills/`，**plugin 升级时这个目录不动**，配置不会丢：

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/us-trend-scout.yaml` | 飞书 webhook URL | 否（不填则简报 dump 到对话不推送）|
| `~/.config/ops-skills/personas.yaml` | 自定义数字角色，覆盖默认 26 个 | 否（不填用 plugin 自带）|
| `~/.claude/memory/xcmo-session.json` | xcmo 平台 session token | xcmo-download 必填 |

## Skills

### us-trend-scout

每天北京 9:00（美东前一天晚上）自动跑 6 路并行 WebSearch，筛 5-8 条**具体可证实**的热点，每条配 1-2 个数字角色出具体创意，加平台格式趋势 + 文化情绪，输出中文纯文本简报推飞书群。

**触发词**：热点日报 / 美区热点 / us trend / trend scout / 跑一次热点

<!-- TODO: 跑一次后截一张飞书群里收到的简报截图，存到 docs/screenshots/feishu-briefing.png -->

![飞书简报示例](docs/screenshots/feishu-briefing.png)

**定时**：

```
/schedule create "0 1 * * *" "run skill ops-skills:us-trend-scout"
```

UTC 01:00 = 北京 09:00。

### xcmo-download

把 xcmo 平台 batch 产物按「外部（南宁合作方）/ 内部（雨悦自运营）」分组下载：

- 外部 → `.docx`（文案+标签）+ `.zip`（视频包），方便整体发合作方
- 内部 → 只生成 `.docx`，视频文件留 `videos/内部/` 目录直接拿

**触发词**：下载 batch / 打包 batch / 下载这批 / 导出 batch / download batch

**用法**：

```
下载这批：
外部: batch-7762e81c-bb01-439d-9904-36d2399607bb, batch-aaa
内部: batch-xxx, batch-yyy
```

<!-- TODO: 跑一次后截一张 .docx 内容的截图，存到 docs/screenshots/xcmo-docx.png -->

![xcmo-download 产出示例](docs/screenshots/xcmo-docx.png)

**输出位置**：`~/Desktop/xcmo-batches/<YYYYMMDD>/`

**首次配置**（拿 xcmo session token）：

1. 浏览器打开 https://xcmo.ai 登录
2. F12 → Application → Cookies → 找 `vee_session` → 复制 value
3. 告诉 Claude：「更新 xcmo token: \<粘贴你的 token\>」

Claude 会把 token 写入 `~/.claude/memory/xcmo-session.json`（user 级，不进 plugin 缓存，升级 plugin 不会丢）。token 过期后再说一次「更新 xcmo token: ...」即可。

## 仓库结构

```
ops-skills/
├── .claude-plugin/
│   ├── plugin.json           # plugin 自身元数据
│   └── marketplace.json      # marketplace 目录索引
├── .github/workflows/ci.yml  # GitHub Actions: 校验 + pytest
├── skills/
│   ├── us-trend-scout/
│   │   ├── SKILL.md
│   │   ├── personas.yaml          # 默认 26 数字角色（user 可覆盖）
│   │   └── config.example.yaml    # webhook 配置模板
│   └── xcmo-download/
│       ├── SKILL.md
│       └── download.py            # urllib + python-docx
├── tests/test_download.py    # pytest 单测（27 case）
├── bump-version.sh           # 同步 plugin.json + marketplace.json 版本
├── CHANGELOG.md
├── LICENSE                   # Apache 2.0
├── README.md
├── requirements.txt          # python-docx
├── requirements-dev.txt      # + pytest
└── pytest.ini
```

## 开发

```bash
# clone + 本地跑测试
git clone https://github.com/huanghfzhufeng/ops-skills.git
cd ops-skills
pip install -r requirements-dev.txt
pytest

# 本地调试 plugin（无需先发布）
claude --plugin-dir .

# 发版（必须同步两份 JSON 的 version！）
./bump-version.sh 1.1.1
# 编辑 CHANGELOG.md 加新版段
git add -A && git commit -m "chore: release 1.1.1"
git tag v1.1.1
git push && git push --tags
```

## 反馈

issue 提到 [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)。

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
