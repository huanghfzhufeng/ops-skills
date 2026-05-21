# Claude Code Plugin 设计指南

> 一份关于「如何做一个好 plugin」的完整心智模型。
>
> **适用读者**：想从零做一个 Claude Code plugin、或者想把现有的散装 skills 升级成正式 plugin 的开发者。
>
> **本指南由来**：[ops-skills](https://github.com/huanghfzhufeng/ops-skills) 从最初一堆 SKILL.md → v1.0.0「能装的 plugin」→ v1.1.0「完整 plugin」的演进过程中总结。

---

## 这份指南是什么

不是 API 文档（那是 [Anthropic 官方文档](https://code.claude.com/docs/en/plugins-reference) 的事），是**心智模型和工程实践**。

读完你会获得：

- 三个理念，帮你决定「为什么要做某些事」
- 五个生命周期层，帮你识别「我现在缺什么」
- 五条铁律，帮你避开「最容易忽视的坑」
- 成熟度自检表，帮你定位「我的 plugin 在哪一级」
- 6 份可直接抄的模板（plugin.json / marketplace.json / SKILL.md / CHANGELOG / CI / bump 脚本）

---

## 一、三个核心理念

### 理念 1：skill 是「协议」，不是「脚本」

SKILL.md 是给 AI（Claude）读的指令书，不是给 Python 解释器读的代码。这决定了你应该：

- 工作流要描述「**该做什么、按什么顺序、出错怎么办**」
- 不要描述「具体怎么实现」（实现细节放进辅助脚本，SKILL.md 自己保持可读）
- `description` 字段是 **"广告语 + 搜索关键词"**——写好了 AI 才能正确触发；写糟了 AI 看不见

### 理念 2：plugin 是「系统」，不是「压缩包」

很多人以为 plugin = 「把 skill 装到 zip 里」。错。

Plugin 是要把 **发现 → 安装 → 使用 → 升级 → 演进** 整条生命周期都设计好。**任何一环断掉，这个 plugin 在野外就会死**。

举例：你做了个能用的 plugin 但没加 `CHANGELOG.md`——用户升级时不知道改了啥，遇到 bug 不敢升、不敢回滚，慢慢就弃用了。这就是「使用层完美但演进层断裂」的死法。

### 理念 3：用户数据 ≠ plugin 代码

**铁律**：**plugin 是只读的（升级会覆盖），用户配置是可写的（永不被覆盖）**。

| 数据类型 | 该放哪 |
|---|---|
| plugin 自带默认（示例 yaml）| plugin 目录里（可被升级覆盖、用户可 override）|
| 用户自定义配置（webhook URL、API key）| `~/.config/<plugin-name>/` |
| 用户敏感数据（token、cookie）| `~/.claude/memory/` |
| 缓存 / 临时输出 | `~/Desktop/` 或 `/tmp/` |

一旦你把用户配置塞进 plugin 目录，升级路径就断了——用户每次 `/plugin upgrade` 都会丢配置。

---

## 二、五个生命周期层

把 plugin 想成一个产品，它要走 5 层。每一层缺东西就在那一层「死」。

```
①发现 →  ②安装 →  ③使用 →  ④演进 →  ⑤协作
```

### ① 发现层：让别人找到你

| 要素 | 文件 | 作用 |
|---|---|---|
| `description`（最关键）| SKILL.md frontmatter | 决定 Claude 何时触发 |
| `keywords` | plugin.json | 决定 marketplace 搜索能否搜到 |
| `category` | marketplace.json | 分类标签（content-creation / development / 等）|
| 项目标题 + 一段简介 | README 头部 | 别人打开仓库第一眼判断要不要看 |
| badges（CI/License/版本）| README 头部 | 让别人一眼判断质量 |

### ② 安装层：让别人能装上

| 要素 | 文件 | 作用 |
|---|---|---|
| plugin 身份证 | `.claude-plugin/plugin.json` | 名字、版本、作者、license |
| marketplace 目录 | `.claude-plugin/marketplace.json` | 让 `/plugin marketplace add` 认识仓库 |
| 法律基础 | `LICENSE` | 没 LICENSE 别人法律上不敢用 |
| 依赖明示 | `requirements.txt` / `package.json` | 不写依赖别人装不全 |
| 一行安装命令 | README Quick Start | 用户能复制粘贴跑通 |

### ③ 使用层：装上以后能跑通

| 要素 | 文件 | 作用 |
|---|---|---|
| 工作流定义 | SKILL.md 正文 | Step 1/2/3 让 AI 按顺序执行 |
| 失败兜底 | SKILL.md "失败处理"段 | API 挂了、配置缺失、token 过期怎么办 |
| 配置文件位置 | README + SKILL.md | 用户配置去 `~/.config/`，不进 plugin 目录 |
| 触发关键词 | description 句尾 | 中英文都列，用户原话作触发 |
| 输出格式明示 | SKILL.md "输出格式"段 | 让产出可预测 |
| 截图样本 | `docs/screenshots/` | 让用户看到产出长啥样 |

### ④ 演进层：发新版本（**最容易被忽视**）

这一层决定 plugin 能不能从「一次性脚本」变成「活的产品」。

| 要素 | 文件 | 作用 |
|---|---|---|
| 版本号同步工具 | `bump-version.sh` | 两份 JSON 一键改，不漏 |
| 变更日志 | `CHANGELOG.md` | 用户升级前能看到改了啥 |
| 自动化检查 | `.github/workflows/ci.yml` | 改代码 PR 自动验证不 break |
| 单元测试 | `tests/` | 改代码时知道改坏没 |
| 版本标签 | `git tag v1.1.0` | 历史可追溯、可回滚 |
| GitHub Release | github.com/.../releases | 用户看版本史的入口 |
| 用户配置分离 | `~/.config/<plugin>/` | 升级不丢用户数据 |

### ⑤ 协作层：让别人能贡献

| 要素 | 文件 | 作用 |
|---|---|---|
| 贡献指南 | `CONTRIBUTING.md` | 怎么提 PR、怎么跑测试 |
| issue 模板 | `.github/ISSUE_TEMPLATE/` | 收到的 issue 质量高 |
| PR 模板 | `.github/PULL_REQUEST_TEMPLATE.md` | PR 描述结构化 |
| 安全报告流程 | `SECURITY.md` | 漏洞怎么 responsible disclosure |
| 行为准则 | `CODE_OF_CONDUCT.md` | 社区氛围预期 |
| 英文翻译 | `README.en.md` | 让国际用户能进入 |

---

## 二·补：一个早期就要做的架构决策——单 plugin 还是多 plugin？

在你的仓库里塞 skill 之前必须想清楚的事，否则一旦有用户装上就难改了。

### 两种架构

**架构 A：1 个胖 plugin 装所有 skill**

```
marketplace my-stuff
└── plugin my-stuff
    ├── skills/skill-1
    ├── skills/skill-2
    └── skills/skill-3
```

**架构 B：1 个 marketplace 装多个瘦 plugin**

```
marketplace <owner-name>
├── plugin domain-A    (含 skill-1, skill-2)
├── plugin domain-B    (含 skill-3)
└── plugin domain-C    (含 skill-4, skill-5)
```

### 对比

| 维度 | 架构 A（胖）| 架构 B（瘦）|
|---|---|---|
| 装的命令数 | 1 条 | 每个 plugin 1 条 |
| 版本管理 | 改任何 skill 整 plugin 一起 bump，**联动升级** ❌ | 每个 plugin 独立 version ✅ |
| 依赖膨胀 | 用户装一个 plugin 必须装所有依赖 ❌ | 用户只装他要的 ✅ |
| 职责清晰 | 名字越来越泛 ❌ | 一个 plugin = 一个 domain ✅ |
| breaking change 难度 | 拆分时已装用户痛 ❌ | 天然解耦 ✅ |

### 选 A 的场景

- 所有 skill 都强相关、共享同一套依赖
- 你确定**永远只有 3-5 个 skill**
- 用户从不想"只用一部分"
- 个人玩具项目

### 选 B 的场景

- 你已经预见到要做 2+ 个 domain
- 不同 skill 依赖差异大（一个要 ffmpeg、一个 0 依赖）
- 你想让别人按需装
- 想长期演进的项目

### 业内主流案例

| 仓库 | 架构 | marketplace 名 |
|---|---|---|
| `claude-plugins-official` | B（几十个 plugin）| `claude-plugins-official` |
| `pua-skills` | B（当前 1 个但结构已分开）| `pua-skills` |
| `ykdojo` | B（当前 1 个但结构已分开）| `ykdojo` |
| `huanghfzhufeng/ops-skills`（本仓库）| B（v2.0.0 起重构）| `huanghfzhufeng` |

**业内 99% 走架构 B**。即使现在只有 1 个 plugin，也建议 **marketplace name 跟 plugin name 不同**，给未来加 plugin 留好结构位置。

### 命名惯例

```
marketplace name = <owner 名> 或 <repo 名>
plugin name      = <功能/domain 名>，比 marketplace 名短
```

例：
- marketplace `huanghfzhufeng` + plugin `tiktok-matrix` → `tiktok-matrix@huanghfzhufeng` ✓
- marketplace `pua-skills` + plugin `pua` → `pua@pua-skills` ✓
- marketplace `my-plugin` + plugin `my-plugin` → `my-plugin@my-plugin` ✗（视觉重复 + 未来锁死）

### 多 plugin 仓库的目录结构

```
your-repo/
├── .claude-plugin/
│   └── marketplace.json          ← 列所有 plugin
├── plugins/
│   ├── plugin-a/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── skills/...
│   │   ├── README.md
│   │   ├── CHANGELOG.md
│   │   └── requirements.txt
│   └── plugin-b/
│       └── ...                    （同结构）
├── LICENSE                        ← 共享
├── README.md                      ← marketplace 总览
├── CHANGELOG.md                   ← marketplace 级变更
├── docs/                          ← 共享文档
├── .github/workflows/ci.yml       ← 共享 CI
└── bump-version.sh                ← 共享工具（支持 ./bump-version.sh <plugin-name> <ver>）
```

**关键区分**：
- **仓库根** = marketplace 层（架构变化）
- **plugins/*/** = plugin 层（功能变化）

每个 plugin 有独立 CHANGELOG / README / version。仓库根的 CHANGELOG 只记录 marketplace 层的事（如新增 plugin、架构重构）。

---

## 三、五条最容易忽视的实践铁律

### 铁律 1：description 写「用户原话」，不是「技术词」

```yaml
# ❌ 触发率低（用户不会这么说）
description: 美区 TikTok 趋势分析与社交媒体格式洞察平台

# ✅ 触发率高（用户会这么说）
description: |
  美区 TikTok 热点抓取 + 飞书推送。
  触发：用户说"热点日报"、"美区热点"、"us trend"、"跑一次热点"
```

AI 触发是按字面匹配概率算的。**用户说啥你就写啥**。

### 铁律 2：双 JSON 的 version 必须同步

`plugin.json` 和 `marketplace.json` 的 version **永远要一致**，靠人记必出错。两道保险：

- **工具保险**：`bump-version.sh` 一键改两处
- **CI 保险**：push 时 CI 检查不一致直接 fail（见后面 CI 模板）

### 铁律 3：每个版本必须有「4 件套」

```
1. CHANGELOG.md 加一段 [1.x.x]
2. plugin.json + marketplace.json bump version
3. git tag v1.x.x
4. GitHub Release（在 github.com 网页上 Draft）
```

少任何一件，用户都难以理解这个版本。

### 铁律 4：用户配置位置三选一，永不放 plugin 目录

```
~/.config/<plugin-name>/<config>.yaml    # 通用配置
~/.claude/memory/<plugin>-session.json   # 敏感凭证
环境变量 <PLUGIN>_<KEY>                  # CI / 容器友好
```

放 plugin 目录里 = 升级丢配置 = 用户骂人 = 弃坑。

### 铁律 5：SKILL.md 不写绝对路径

```bash
# ❌ plugin 装到 cache 后路径就变了，会断
python3 ~/.claude/skills/foo/script.py

# ✅ 让 Claude 自己从 SKILL.md 位置解析
python3 <skill-dir>/script.py
```

plugin 装到 cache 后实际路径是 `~/.claude/plugins/cache/<market>/<plugin>/<version>/...`，**带版本号**，硬编码绝对路径必死。

---

## 四、成熟度自检阶梯

| 级别 | 标志 | 用户感受 |
|---|---|---|
| **Level 0：裸 skill** | 单个 SKILL.md 在 GitHub | "我得手抄到本地"|
| **Level 1：能装 plugin** | + plugin.json + marketplace.json | "能装但出 bug 没人管"|
| **Level 2：可维护 plugin** | + CHANGELOG + LICENSE + git tag | "能升级、可追溯改了啥"|
| **Level 3：工程化 plugin** | + CI + 测试 + bump 脚本 + user-level config | "改代码不怕 break、升级不丢配置"|
| **Level 4：产品级 plugin** | + 截图 + 英文 README + 进官方 marketplace | "搜索能搜到、看截图想装"|
| **Level 5：生态级 plugin** | + 多人贡献 + ISSUE_TEMPLATE + SECURITY.md | "活的开源社区"|

---

## 五、可直接抄的模板

### 模板 1：`.claude-plugin/plugin.json`

```json
{
  "name": "my-plugin",
  "description": "一句话讲清楚 plugin 干啥的（出现在 marketplace 搜索结果）。",
  "version": "1.0.0",
  "author": {
    "name": "your-github-username",
    "url": "https://github.com/your-github-username"
  },
  "homepage": "https://github.com/your-github-username/my-plugin",
  "repository": "https://github.com/your-github-username/my-plugin",
  "license": "Apache-2.0",
  "keywords": [
    "标签词-1",
    "标签词-2",
    "标签词-3"
  ]
}
```

### 模板 2：`.claude-plugin/marketplace.json`

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "my-plugin",
  "description": "marketplace 的一句话简介。",
  "owner": {
    "name": "your-github-username",
    "url": "https://github.com/your-github-username"
  },
  "plugins": [
    {
      "name": "my-plugin",
      "source": "./",
      "description": "和 plugin.json 里的 description 保持一致。",
      "version": "1.0.0",
      "category": "productivity",
      "homepage": "https://github.com/your-github-username/my-plugin"
    }
  ]
}
```

### 模板 3：`skills/<skill-name>/SKILL.md`

```markdown
---
name: my-skill
description: 一句话说 skill 干啥 + 触发词。触发：用户说"xxx"、"yyy"、"zzz"。
---

# My Skill

> 这一段写给读源码的人，说明 skill 的设计意图。

## 首次使用

配置文件放在 user-level 目录 `~/.config/my-plugin/`：

\`\`\`bash
mkdir -p ~/.config/my-plugin
cp <skill-dir>/config.example.yaml ~/.config/my-plugin/my-skill.yaml
$EDITOR ~/.config/my-plugin/my-skill.yaml
\`\`\`

## 工作流

### Step 1 - 读配置

按优先级加载：
1. `~/.config/my-plugin/my-skill.yaml`（用户配置，跨升级保留）
2. fallback 到 `<skill-dir>/config.example.yaml`

### Step 2 - 干活

具体步骤...

### Step 3 - 输出 / 报告

向用户报告：
- 处理了多少条
- 成功/失败计数
- 输出位置

## 输出格式

\`\`\`
<给用户的产出长啥样>
\`\`\`

## 失败处理

| 情况 | 处理 |
|---|---|
| API 401 | 提示用户更新 token |
| 网络超时 | retry 1 次 |
| 配置文件缺失 | 报错 + 引导首次使用 |
```

### 模板 4：`CHANGELOG.md`

Keep a Changelog 标准格式：

```markdown
# Changelog

本项目所有重要变更都会记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

—

## [1.1.0] - 2026-05-21

### Added
- 新加的功能

### Changed
- 修改的行为（可能 breaking）

### Fixed
- bug 修复

### Removed
- 删除的功能（major bump 用）

### Security
- 安全相关修复（如果有）

## [1.0.0] - 2026-04-01

### Added
- 初版发布

[Unreleased]: https://github.com/owner/repo/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/owner/repo/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/owner/repo/releases/tag/v1.0.0
```

### 模板 5：`.github/workflows/ci.yml`

最小可用 CI（校验 JSON + 跑测试 + 版本一致性检查）：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate JSON
        run: |
          python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"
          python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))"

      - name: Check version consistency
        run: |
          python3 -c "
          import json
          pj = json.load(open('.claude-plugin/plugin.json'))
          mj = json.load(open('.claude-plugin/marketplace.json'))
          plugin_v = pj['version']
          mp_v = next((p['version'] for p in mj['plugins'] if p['name'] == pj['name']), None)
          assert plugin_v == mp_v, f'version mismatch: plugin.json={plugin_v} marketplace.json={mp_v}'
          print(f'✓ version 同步: {plugin_v}')
          "

  test:
    runs-on: ubuntu-latest
    needs: validate
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements-dev.txt
      - run: pytest -v
```

### 模板 6：`bump-version.sh`

```bash
#!/usr/bin/env bash
# bump-version.sh — 同步更新 plugin.json 和 marketplace.json 的 version

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "用法: $0 <new-version>"
  exit 1
fi

NEW_VERSION="$1"
cd "$(dirname "$0")"

python3 - "$NEW_VERSION" <<'PYEOF'
import json, sys
from pathlib import Path

new_v = sys.argv[1]

pj = Path(".claude-plugin/plugin.json")
data = json.loads(pj.read_text(encoding="utf-8"))
data["version"] = new_v
pj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

mj = Path(".claude-plugin/marketplace.json")
mdata = json.loads(mj.read_text(encoding="utf-8"))
for p in mdata["plugins"]:
    if p["name"] == data["name"]:
        p["version"] = new_v
mj.write_text(json.dumps(mdata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"✓ version 已同步到 {new_v}")
PYEOF

echo ""
echo "下一步: 编辑 CHANGELOG.md → git commit → git tag v$NEW_VERSION → git push --tags"
```

记得 `chmod +x bump-version.sh`。

---

## 六、推荐发版流程

每次发新版严格走这 6 步：

```bash
# 1. 改代码 / 修 bug
git checkout -b fix/something
vim ...

# 2. 跑本地测试确认没破东西
pytest

# 3. 决定版本号（参考 semver）
#    1.0.0 → 1.0.1  patch（只修 bug）
#    1.0.0 → 1.1.0  minor（加新功能向后兼容）
#    1.0.0 → 2.0.0  major（breaking change）
./bump-version.sh 1.1.0

# 4. 写 CHANGELOG.md 新版段
$EDITOR CHANGELOG.md

# 5. commit + tag + push
git add -A
git commit -m "feat: release v1.1.0 — <一句话总结>"
git tag v1.1.0
git push && git push --tags

# 6. GitHub 上 Draft Release
#    github.com/owner/repo/releases/new
#    选 v1.1.0 tag，拷 CHANGELOG.md 该版段到 description
```

---

## 七、心法

> **好 skills 项目的判定标准**：你今天写完，半年后还能优雅发 v2.0、用户能丝滑升级、新贡献者能提 PR 通过 CI 自动验证。

**这不是「代码写得好」，是「系统设计得让它能在野外活下去」**。

写代码的人多，设计系统的人少。这份指南是给你设计「能活下去的系统」的工具。

---

## 八、参考资源

### 官方文档

- [Claude Code Plugins Reference](https://code.claude.com/docs/en/plugins-reference)
- [Discover and install prebuilt plugins](https://code.claude.com/docs/en/discover-plugins)
- [Extend Claude with skills](https://code.claude.com/docs/en/custom-skills)
- [Create a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces)

### 标准

- [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
- [Semantic Versioning](https://semver.org/lang/zh-CN/)
- [SPDX License List](https://spdx.org/licenses/)（给 plugin.json 的 license 字段选标识符）

### 参考实现

- [ops-skills](https://github.com/huanghfzhufeng/ops-skills) — 本指南就是从它的演进过程中总结的，仓库本身可作为 Level 3+ plugin 的完整样本
- [claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — Anthropic 官方 marketplace，看多 plugin 在一个 marketplace 里怎么组织
- [pua-skills](https://github.com/tanweai/pua) — 单 plugin 的 marketplace 写法参考

---

**Last updated**: 2026-05-21（对应 ops-skills v1.1.0）
