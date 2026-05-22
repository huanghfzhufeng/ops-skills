# ops-skills

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

美区 TikTok 矩阵号运营工具集，[huanghfzhufeng](https://github.com/huanghfzhufeng) 出品。

包含两个 skill：

- **us-trend-scout** — 每天自动抓美区 TikTok 热点，配 26 个数字角色出具体创意，推飞书群
- **xcmo-download** — 从 [xcmo.ai](https://xcmo.ai) 批量下载 batch 产物（视频 + 文案 + 标签），按「外部 / 内部」分组打包

---

## 安装

### 方式 1：Desktop App 用户（推荐，最简）

打开 **Mac 终端**（⌘+Space 搜「终端」回车），粘贴这一段：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git /tmp/ops-skills && \
mkdir -p ~/.claude/skills ~/.config/ops-skills && \
cp -r /tmp/ops-skills/skills/* ~/.claude/skills/ && \
cp /tmp/ops-skills/skills/us-trend-scout/config.example.yaml ~/.config/ops-skills/us-trend-scout.yaml && \
pip3 install --user python-docx 2>/dev/null; \
echo "✅ 装好，请完全退出 Claude Desktop App（⌘+Q）再打开"
```

跑完后**完全退出 Claude Desktop App**（⌘+Q），再打开。跟 Claude 说「跑一次热点」就触发。

### 方式 2：Claude Code CLI 用户

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

享受标准 plugin 系统（版本管理 + `/plugin upgrade`）。

---

## 用户配置（跨升级保留）

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/us-trend-scout.yaml` | 飞书 webhook URL | 否（不填则简报 dump 到对话不推送）|
| `~/.config/ops-skills/personas.yaml` | 自定义 26 数字角色（覆盖默认）| 否 |
| `~/.claude/memory/xcmo-session.json` | xcmo 平台 session token | xcmo-download 必填 |

---

## Skills

### us-trend-scout

每天北京 9:00 自动跑 6 路并行 WebSearch，筛 5-8 条**具体可证实**的热点，每条配 1-2 个数字角色出具体创意，推飞书群。

**触发词**：热点日报 / 美区热点 / us trend / 跑一次热点

**飞书 webhook 怎么拿**：飞书群 → 群设置 → 群机器人 → 添加 → 自定义机器人 → 复制 webhook URL。填到 `~/.config/ops-skills/us-trend-scout.yaml` 里。

### xcmo-download

把 xcmo 平台 batch 产物按「外部（南宁合作方）/ 内部（雨悦自运营）」分组下载：

- 外部 → `.docx`（文案+标签）+ `.zip`（视频包），方便整体发合作方
- 内部 → 只生成 `.docx`，视频文件留 `videos/内部/` 目录直接拿

**触发词**：下载 batch / 打包 batch / 下载这批

**用法**：

```
下载这批：
外部: batch-7762e81c-bb01-439d-9904-36d2399607bb, batch-aaa
内部: batch-xxx, batch-yyy
```

**首次配置 xcmo session token**：浏览器登录 xcmo.ai → F12 → Application → Cookies → 复制 `vee_session` 值 → 告诉 Claude：「更新 xcmo token: \<粘贴你的 token\>」。Claude 会写入 `~/.claude/memory/xcmo-session.json`。

**输出位置**：`~/Desktop/xcmo-batches/<YYYYMMDD>/`

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
│   │   ├── personas.yaml          # 默认 26 数字角色
│   │   └── config.example.yaml    # webhook 配置模板
│   └── xcmo-download/
│       ├── SKILL.md
│       └── download.py
├── tests/                          # 27 个 pytest 单测
├── .github/workflows/ci.yml        # 自动校验 + 测试
├── bump-version.sh                 # 版本同步工具
├── requirements.txt                # python-docx
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

# 发新版（同步 plugin.json + marketplace.json 的 version）
./bump-version.sh 3.0.1
# 编辑 CHANGELOG.md
git add -A && git commit -m "chore: release v3.0.1"
git tag v3.0.1
git push && git push --tags
```

## 反馈

issue: [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
