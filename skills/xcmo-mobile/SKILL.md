---
name: xcmo-mobile
description: 按邮箱+日期从 xcmo 平台拉该用户当天生成的所有视频，按人物分组下载到本地，生成 HTML 站 + 二维码，起本地服务器供手机扫码访问（看视频/复制文案/复制标签）。用于「电脑下载完→手机扫码→发到抖音/TikTok」的工作流。触发：用户说「下载 <邮箱> <日期> 的内容」、「拉 <邮箱> <日期> 的素材」、「mobile share <邮箱> <日期>」、「<邮箱> <日期>」（直接给邮箱+日期）、「更新 xcmo token: <token>」。
---

# xcmo-mobile

把指定 xcmo 用户在指定日期生成的视频拉到本地，按人物分组，生成可手机扫码访问的本地站点。

**典型工作流**：电脑跑 skill → 自动起服务器 → 手机扫人物二维码 → 看视频 + 复制文案/标签 → 切到抖音 App 粘贴发布。

## 触发示例

```
下载 luyuyue@liao.com 2026-05-22 的内容
```

```
拉 luyuyue@liao.com 2026-05-21~2026-05-22 的素材
```

```
mobile share luyuyue@liao.com 2026-05-22
```

```
luyuyue@liao.com 2026-05-22
```

**更新 token**（当之前的失效时）：

```
更新 xcmo token: _aKtwdRSmJb8n...（粘贴新 token）
```

## 工作流（按顺序执行）

### Step 1 - 解析用户输入

从用户消息提取：

- `email`：必填，格式 `xxx@yyy.zzz`
- `date`：必填，支持 `2026-05-22` / `20260522` / `2026-05-21~2026-05-22`（区间）

**无法解析时回问用户**，不要瞎猜。

### Step 2 - 跑 mobile.py

执行本 skill 目录下的 `mobile.py`（与本 SKILL.md 同目录）。Claude 根据读到本 SKILL.md 的位置自动构造绝对路径。

```bash
python3 <skill-dir>/mobile.py \
  --email "luyuyue@liao.com" \
  --date "2026-05-22"
```

可选参数：
- `--port 9000`：指定 HTTP 端口（默认 8080，被占用自动找下一个）
- `--no-serve`：只生成文件不起服务（用户后续手动起）
- `--out-dir /tmp/test`：自定义输出根目录

脚本自动完成：

1. 读 `~/.claude/memory/xcmo-session.json` 拿 `vee_session` token
2. `GET /api/auth/me` 拿当前 scope_id
3. `GET /api/scopes/{scope_id}/members` 把邮箱 → user_id
4. `GET /api/tasks?date_from=X&date_to=Y&submitted_by_user_id=Z&limit=500` 拉 task
5. 筛 `completed` + 有 `result.asset_id` 的 task
6. 对每个 asset_id：`GET /api/assets?asset_id=X` 拿完整 asset 数据
7. 按 `character_id` 分组，下载视频（`file_url`）+ 缩略图（`thumb_url`）
8. 生成二维码（每个人物一张 PNG）
9. 渲染 HTML：`index.html` 总览 + 每人物一个 `<character_id>.html`
10. 检测电脑 LAN IP，二维码 URL = `http://<LAN-IP>:<port>/<character_id>.html`
11. 起 `python3 -m http.server <port>`，浏览器自动打开 `http://localhost:<port>`

### Step 3 - 报告

脚本结束（无 `--no-serve`）会阻塞在服务器上。Claude 应：

1. 告诉用户**站点已起**：电脑访问 `http://localhost:<port>`
2. 提示**手机扫码**：在首页有所有人物的二维码，扫哪个看哪个
3. 提醒**Ctrl+C 停服务**
4. **重要前提**：手机和电脑必须在同一 WiFi

### Step 4 - Token 失效处理（脚本退出码 4）

脚本探测到 HTTP 401/403 会退出码 4，stderr 输出明确指引。看到这个：

1. 告诉用户：「xcmo token 失效了，请按以下步骤拿新 token：
   - 浏览器打开 https://xcmo.ai 登录
   - F12 → Application → Cookies → 找 `vee_session` → 复制 value
   - 把新 token 发我（说「更新 xcmo token: xxx」）」
2. 用户提供新 token 后，用 Python 更新 `~/.claude/memory/xcmo-session.json` 的 `vee_session` 字段
3. 重跑下载脚本

更新 token 的 Python 片段：

```python
import json
from pathlib import Path

p = Path.home() / ".claude/memory/xcmo-session.json"
data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
data["vee_session"] = "<新 token>"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
p.chmod(0o600)
```

### Step 5 - 邮箱找不到（退出码 5）

如果脚本报「在 scope 里没找到邮箱」，说明该邮箱不是当前 scope 的成员。Claude 告诉用户：「这个邮箱不在你 xcmo 的 scope 里，确认一下拼写，或者用 `/api/scopes/<id>/members` 看可选邮箱」。

## 输出文件结构

```
~/Desktop/xcmo-mobile/luyuyue@liao.com/20260522/
└── site/
    ├── index.html             # 总览：所有人物 + 各自二维码
    ├── ava.html               # ava 的视频详情页
    ├── ro.html
    ├── eleanor.html
    ├── ... (每个人物一个 html)
    ├── style.css
    ├── qrcodes/
    │   ├── ava.png
    │   └── ...
    └── videos/
        ├── ava/
        │   ├── ootd fit check abc12345.mp4
        │   └── ootd fit check abc12345.jpg     # 缩略图（xcmo 提供）
        ├── ro/
        └── ...
```

视频文件命名：`{任务名} {asset 前 8 位}.mp4`，缩略图同名 `.jpg`。

## HTML 页面功能

### 总览页（`index.html`）

- 标题：邮箱 + 日期范围 + 总人物数 + 总视频数
- 人物卡片网格：每个卡片含
  - 该人物专属二维码（手机扫直接进该人物页）
  - 人物名（点击进入详情页）
  - 视频数

### 人物详情页（`<character_id>.html`）

每个视频一个卡片：
- `<video>` 控件（带 xcmo 缩略图 poster）
- 「📥 下载视频」按钮（`<a download>`）
- 「📝 文案」 + 「📋 复制」按钮
- 「🏷️ 标签」 + 「📋 复制」按钮

复制按钮支持：
- 现代浏览器：`navigator.clipboard.writeText()`
- HTTP 协议下的 fallback：`document.execCommand('copy')`

## 错误处理

| 情况 | 处理 |
|---|---|
| 邮箱在 scope 里找不到 | 退出码 5，stderr 列出可选邮箱 |
| token 失效（401/403）| 退出码 4，引导更新 token |
| session 文件缺失 | 退出码 3 |
| `qrcode` / `pillow` 没装 | 退出码 2 + 提示 `pip3 install qrcode pillow` |
| 某个 asset 拉取失败 | 跳过 + warning，不阻塞其他 |
| 某个视频下载失败 | 重试 1 次，仍失败 → 跳过（html 里仍写文案/标签）|
| 端口被占用 | 自动找 8080..8090 区间内的空闲端口 |

## 退出码

| Code | 含义 |
|---|---|
| 0 | 成功 |
| 2 | qrcode/pillow 缺失 |
| 3 | session 文件缺失 |
| 4 | TOKEN 失效（401/403）|
| 5 | 邮箱在 scope 里找不到 |

## 依赖

- Python 3.10+
- `qrcode` + `pillow`（生成二维码）
- 标准库：`urllib`, `http.server`, `socket`, `socketserver`, `webbrowser`, `html`

## 触发关键词

中文：下载 / 拉 / 导出 / mobile / 手机扫码 / 扫码看  
英文：mobile share / pull / fetch / download

通常用户会说邮箱 + 日期，Claude 应识别这种组合直接触发。
