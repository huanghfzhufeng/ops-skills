---
name: xcmo-download
description: 从 xcmo 平台批量下载 batch 产物（视频 + 文案 + 标签），按"外部（南宁合作方）/内部（雨悦自己运营）"分组打包。外部输出 .docx + .zip 方便发合作方；内部只输出 .docx，视频文件留在本地目录方便自己拿。触发：用户说"下载 batch"、"打包 batch"、"下载这批"、"导出 batch"、"download batch"、"pull batch"，或直接给 batch ID 列表（如 `batch-xxxx-xxxx`）并标注"外部:"/"内部:"。也用于"更新 xcmo token: <token>"。
---

# xcmo Download Skill

把 xcmo 平台上批次任务（batch）的产物下载到本地，按"外部 / 内部"分组打包。

- **外部**（南宁合作方）：生成 `.docx`（文案+标签）+ `.zip`（视频包）—— 方便整体发给合作方
- **内部**（雨悦自己运营）：只生成 `.docx`，视频文件留在 `videos/内部/` 目录里 —— 自己运营自己拿，不用解压

## 触发示例

**标准格式**：
```
下载这批：
外部: batch-7762e81c-bb01-439d-9904-36d2399607bb, batch-aaa
内部: batch-xxx, batch-yyy
```

**简化格式**：
```
下载 batch
外部 batch-A, batch-B
内部 batch-X
```

**单批 + 类别**：
```
下载 batch-7762e81c-bb01-439d-9904-36d2399607bb 外部
```

只有外部 / 只有内部也可以。

**更新 token**（当之前的 token 失效时）：
```
更新 xcmo token: _aKtwdRSmJb8n...（粘贴新 token）
```

## 工作流

### Step 1 - 解析用户输入

提取：
- `external_batches`：外部 batch ID 列表（数组）
- `internal_batches`：内部 batch ID 列表（数组）

识别提示词：
- 外部 / outside / external / 南宁 / 合作方 / 南宁合作方
- 内部 / inside / internal / 雨悦 / 自运营

batch ID 格式：`batch-` 开头的 UUID（如 `batch-7762e81c-bb01-439d-9904-36d2399607bb`）。

**无法解析时回问用户**，不要瞎猜。

### Step 2 - 跑下载脚本

执行本 skill 目录下的 `download.py`（与本 SKILL.md 同目录）。Claude 根据读到本 SKILL.md 的位置自动构造绝对路径，**不要写死 `~/.claude/skills/...`**——plugin 安装后实际路径在 `~/.claude/plugins/cache/<owner>/ops-skills/skills/xcmo-download/download.py`。

```bash
python3 <skill-dir>/download.py \
  --external "batch-A,batch-B" \
  --internal "batch-X"
```

脚本自动：
1. 读 `~/.claude/memory/xcmo-session.json` 拿 `vee_session` token
2. 对每个 batch：`GET /api/tasks/batch/{batch_id}` → 拿 task 列表
3. 对每个 task 的 `result.asset_id`：`GET /api/assets/{id}` 拿完整 asset
4. 下载视频：`https://xcmo.ai{asset.file_url}` 带 cookie auth + Chrome UA（绕 Cloudflare 1010）
5. 生成 `{YYYYMMDD} 南宁合作方.docx` 和 `{YYYYMMDD} 内部.docx`
6. **外部**还会打包 `{YYYYMMDD} 南宁合作方.zip`；**内部不打 zip**

输出到 `~/Desktop/xcmo-batches/{YYYYMMDD}/`（直接放桌面，按日期分子目录）。

### Step 3 - 报告

脚本末尾输出 JSON summary。向用户汇报：
- 每类多少个 batch、多少个视频
- 文件夹路径
- 失败的 batch（如有）

### Step 4 - Token 失效处理（脚本退出码 4）

脚本探测到 HTTP 401 / 403 会退出码 4，stderr 输出明确指引。看到这个：

1. 告诉用户："xcmo token 失效了，请按以下步骤拿新 token：
   - 浏览器打开 https://xcmo.ai 登录
   - F12 → Application → Cookies → 找 `vee_session` → 复制 value
   - 把新 token 发我（直接粘贴或说"更新 xcmo token: xxx"）"
2. 用户提供新 token 后，用 Python 更新 `~/.claude/memory/xcmo-session.json` 的 `vee_session` 字段
3. 重跑下载脚本

更新 token 的 Python 片段：
```python
import json
from pathlib import Path
p = Path.home() / ".claude/memory/xcmo-session.json"
data = json.loads(p.read_text())
data["vee_session"] = "<新 token>"
p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
```

## 输出文件结构

```
~/Desktop/xcmo-batches/20260521/
├── 20260521 南宁合作方.docx     # 外部文档（文案+标签合并）
├── 20260521 南宁合作方.zip      # 外部视频打包（平铺，解压看到所有视频）
├── 20260521 内部.docx           # 内部文档（文案+标签合并）
└── videos/                      # 视频原文件（按类别分目录，不按 batch 分子目录）
    ├── 南宁合作方/              # 外部（zip 的源文件）
    │   ├── 20260520 asian-blond get ready × nari c7bc5f3b.mp4
    │   └── 20260521 kiki ootd × riley 29a638f9.mp4
    └── 内部/                    # 内部（不打 zip，直接从这里拿）
        ├── 20260520 curly-boy 男女友申请 × joey d4353926.mp4
        └── 20260520 carlos 职场幽默 × ezra 9515ad90.mp4
```

视频文件命名格式：`{YYYYMMDD} {character_id} {任务名} {asset8}.mp4`，每个字段含义：
- 日期：asset.created_at（视频生成时间）
- character_id：xcmo 系统角色 ID
- 任务名：asset.name
- asset8：asset id 前 8 位（防同名冲突 + 反查 xcmo asset）

### .docx 结构

```
xcmo 批次产物 — 南宁合作方                       ← 大标题
导出时间: 2026-05-21 06:00:00                    ← 元信息（斜体）
批次数: 3  |  视频数: 3

batch: batch-79d342bf-d4a0-46ed-...              ← 一级标题
task 总数: 1  |  成功导出: 1                      ← 斜体

  1. get ready without me × nari                 ← 二级标题
     视频文件: 20260520 asian-blond get ready ×  ← 粗体字段名，跟实际文件名一致
              nari c7bc5f3b.mp4
     角色: asian-blond
     Caption: omg kinda skipped the grwm...
     Hashtags: #grwm #techsales #corporatebaddie

  2. ...

batch: batch-b47e45c1-...                        ← 下一个 batch
...
```

## 错误处理

| 情况 | 处理 |
|---|---|
| batch_id 不存在（404） | 跳过该 batch + 记录在 summary `failed_batches` 里继续下一个 |
| task 未完成（`status != completed`） | 跳过 + 警告，不阻塞 |
| asset 没有 `file_url` | 跳过视频下载，但 doc 里仍保留 caption + hashtag |
| 视频下载失败 | 重试 1 次。仍失败 → doc 里标 "⚠ 视频下载失败" + zip 里没有 |
| **token 失效（401/403）** | 退出码 4 + stderr 引导。Claude 引导用户拿新 token 后自动写入 session 文件 |
| `~/.claude/memory/xcmo-session.json` 不存在 | 退出码 3 + 引导用户告诉 Claude token |

## 退出码

| Code | 含义 |
|---|---|
| 0 | 成功 |
| 2 | python-docx 缺失（需 `pip install python-docx`）|
| 3 | session 文件缺失 |
| 4 | token 失效 / 401-403 |

## 依赖

- Python 3.8+
- `python-docx`（已在 macOS Python 3.14 装好）
- 标准库：`urllib`, `json`, `zipfile`, `pathlib`, `argparse`

## 触发关键词

中文：下载 batch / 打包 batch / 下载这批 / 导出 batch / 拉视频 / 拉 batch / 下载产物 / 批次下载 / 更新 xcmo token
英文：download batch / pull batch / export batch / fetch batch / update xcmo token
