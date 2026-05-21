# tiktok-matrix

美区 TikTok 矩阵号运营工具集。隶属于 [huanghfzhufeng marketplace](../../README.md)。

包含两个 skill：

- **us-trend-scout** — 每天自动抓美区 TikTok 热点，配 26 个数字角色出具体创意，推飞书群
- **xcmo-download** — 从 [xcmo.ai](https://xcmo.ai) 批量下载 batch 产物（视频 + 文案 + 标签），按「外部 / 内部」分组打包

## 安装

```
/plugin marketplace add huanghfzhufeng/ops-skills
/plugin install tiktok-matrix@huanghfzhufeng
```

装完两个 skill 会以 `tiktok-matrix:us-trend-scout` / `tiktok-matrix:xcmo-download` 命名空间出现。

### Python 依赖

xcmo-download 用到 `python-docx`：

```bash
pip install -r requirements.txt
```

## 用户配置（跨升级保留）

所有用户级配置统一放在 `~/.config/ops-skills/`，**plugin 升级时这个目录不动**：

| 文件 | 作用 | 必填 |
|---|---|---|
| `~/.config/ops-skills/us-trend-scout.yaml` | 飞书 webhook URL | 否 |
| `~/.config/ops-skills/personas.yaml` | 自定义数字角色 | 否 |
| `~/.claude/memory/xcmo-session.json` | xcmo 平台 session token | xcmo-download 必填 |

## Skills

### us-trend-scout

每天北京 9:00 自动跑 6 路并行 WebSearch，筛 5-8 条**具体可证实**的热点，每条配 1-2 个数字角色出具体创意，加平台格式趋势 + 文化情绪，输出中文纯文本简报推飞书群。

**触发词**：热点日报 / 美区热点 / us trend / trend scout / 跑一次热点

**定时**：

```
/schedule create "0 1 * * *" "run skill tiktok-matrix:us-trend-scout"
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

**输出位置**：`~/Desktop/xcmo-batches/<YYYYMMDD>/`

**首次配置**（拿 xcmo session token）：

1. 浏览器打开 https://xcmo.ai 登录
2. F12 → Application → Cookies → 找 `vee_session` → 复制 value
3. 告诉 Claude：「更新 xcmo token: \<粘贴你的 token\>」

Claude 会把 token 写入 `~/.claude/memory/xcmo-session.json`。token 过期后再说一次「更新 xcmo token: ...」即可。

## 变更日志

见 [CHANGELOG.md](CHANGELOG.md)。
