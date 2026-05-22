# ops-skills

[![CI](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/huanghfzhufeng/ops-skills/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

美区 TikTok 矩阵号运营自动化工具集。[huanghfzhufeng](https://github.com/huanghfzhufeng) 出品。

## 包含的 Skill

| Skill | 干啥 | 触发 |
|---|---|---|
| **us-trend-scout** | 每天自动抓美区 TikTok 热点 → 配 26 数字角色出创意 → 简报到对话 | 「跑一次热点」 |
| **xcmo-mobile** | 按邮箱+日期从 xcmo 拉视频 → 按人物分组 → 起本地服务 + 二维码 → 手机扫码看视频/复制文案 | 「下载 \<邮箱\> \<日期\>」|

---

## 安装

### 方式 1：Desktop App 用户（最简）

打开 **Mac 终端**（⌘+Space 搜「终端」回车），粘贴这一段：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git /tmp/ops-skills && \
mkdir -p ~/.claude/skills && \
cp -r /tmp/ops-skills/skills/* ~/.claude/skills/ && \
pip3 install --user --break-system-packages qrcode pillow 2>/dev/null; \
echo "✅ 装好，请完全退出 Claude Desktop App（⌘+Q）再打开"
```

跑完**完全退出 Claude Desktop App**（⌘+Q）再打开。

### 方式 2：Claude Code CLI 用户

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@ops-skills
```

享受标准 plugin 系统（版本管理 + `/plugin upgrade`）。

### Python 依赖

```bash
pip3 install qrcode pillow              # xcmo-mobile 用
```

us-trend-scout 全用 WebSearch + 标准库，无额外依赖。

---

## 用户配置（跨升级保留）

所有用户级配置统一放在 `~/.config/ops-skills/` 或 `~/.claude/memory/`，**plugin 升级时这些目录不动**：

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/personas.yaml` | 自定义 26 数字角色（覆盖默认）| 否 |
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
│   │   └── personas.yaml          # 默认 26 数字角色
│   └── xcmo-mobile/
│       ├── SKILL.md
│       ├── mobile.py              # 核心脚本
│       └── templates/             # HTML 模板
│           ├── index.html
│           ├── character.html
│           └── style.css
├── tests/                          # 31 个 pytest
├── .github/workflows/ci.yml
├── bump-version.sh
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
