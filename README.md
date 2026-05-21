# ops-skills

运营自动化 Claude Code skill 集合，围绕「美区 TikTok 矩阵号」一条业务线：

- **us-trend-scout** — 每天自动抓美区 TikTok 热点，配 26 个数字角色出具体创意，推飞书群
- **xcmo-download** — 从 [xcmo.ai](https://xcmo.ai) 批量下载 batch 产物（视频 + 文案 + 标签），按「外部 / 内部」分组打包

## 安装

需要 [Claude Code](https://docs.claude.com/en/docs/agents/claude-code/overview)。

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install ops-skills@huanghfzhufeng/ops-skills
```

装完两个 skill 会以 `ops-skills:us-trend-scout` / `ops-skills:xcmo-download` 命名空间出现，触发关键词都已写在各自 `SKILL.md` 的 `description` 里。

### 依赖

xcmo-download 用到 `python-docx`：

```bash
pip install -r requirements.txt
# 或单装
pip install python-docx
```

us-trend-scout 全用 WebSearch + 标准库，无额外依赖。

## Skills

### us-trend-scout

每天北京 9:00（美东前一天晚上）自动跑 6 路并行 WebSearch，筛 5-8 条**具体可证实**的热点，每条配 1-2 个数字角色出具体创意，加平台格式趋势 + 文化情绪，输出中文纯文本简报推飞书群。

**触发词**：热点日报 / 美区热点 / us trend / trend scout / 跑一次热点

**首次使用**：

```bash
cd <plugin-install-path>/skills/us-trend-scout
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入飞书 webhook URL
```

webhook 获取方式：飞书群 → 群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 webhook URL。

webhook 没填时仍可跑（简报直接 dump 到对话），不会推飞书。

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

**首次配置**（拿 xcmo session token）：

1. 浏览器打开 https://xcmo.ai 登录
2. F12 → Application → Cookies → 找 `vee_session` → 复制 value
3. 告诉 Claude：「更新 xcmo token: \<粘贴你的 token\>」

Claude 会把 token 写入 `~/.claude/memory/xcmo-session.json`（user 级，不进 plugin 缓存，升级 plugin 不会丢）。token 过期后再说一次「更新 xcmo token: ...」即可。

**输出位置**：`~/Desktop/xcmo-batches/<YYYYMMDD>/`

## 仓库结构

```
ops-skills/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── us-trend-scout/
│   │   ├── SKILL.md
│   │   ├── personas.yaml          # 26 数字角色定位（公开）
│   │   └── config.example.yaml    # 配置模板（webhook 占位符）
│   └── xcmo-download/
│       ├── SKILL.md
│       └── download.py            # urllib + python-docx
├── requirements.txt
└── README.md
```

## 开发

本地调试 plugin（无需先发布到 marketplace）：

```bash
git clone https://github.com/huanghfzhufeng/ops-skills.git
cd ops-skills
claude --plugin-dir .
```

## 反馈

issue 提到 [github.com/huanghfzhufeng/ops-skills/issues](https://github.com/huanghfzhufeng/ops-skills/issues)。

## License

[Apache License 2.0](LICENSE) © 2026 huanghfzhufeng
