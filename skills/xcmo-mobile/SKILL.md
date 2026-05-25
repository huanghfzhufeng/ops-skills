---
name: xcmo-mobile
description: 按邮箱+日期从 xcmo 平台拉该用户当天生成的所有视频，按人物分组下载到本地，生成 HTML 站 + 二维码，起本地服务器供手机扫码访问（看视频/复制文案/复制标签）。用于「电脑下载完→手机扫码→发到 TikTok」的工作流。触发：用户说「下载 <邮箱> <日期> 的内容」、「拉 <邮箱> <日期> 的素材」、「mobile share <邮箱> <日期>」、「<邮箱> <日期>」（直接给邮箱+日期）、「更新 xcmo token: <token>」。
---

# xcmo-mobile

把指定 xcmo 用户在指定日期生成的视频拉到本地，按人物分组，生成可手机扫码访问的本地站点。

**典型工作流**：电脑跑 skill → 自动起服务器 → 手机扫人物二维码 → 看视频 + 复制文案/标签 → 切到 TikTok App 粘贴发布。

## 首次使用

第一次跑前必须完成两步，否则会以退出码 2 或 3 失败。

### 1. 装 Python 依赖

```bash
pip3 install qrcode pillow
```

### 2. 设置 xcmo session token

1. 浏览器打开 https://xcmo.ai 登录
2. F12 → Application → Cookies → 找 `vee_session` → 复制 value
3. 跟 Claude 说："更新 xcmo token: <粘贴 token>"

Claude 会把 token 写到 `~/.claude/memory/xcmo-session.json`（权限 0600）。

### 3. Windows 用户额外注意（macOS / Linux 跳过）

**第一次跑会弹"Windows 安全警告"对话框**，问"允许 Python 通过防火墙"。务必同时勾选：

- ☑ **专用网络**（家庭/工作）
- ☑ **公用网络**（默认不勾，但家用 WiFi 经常被 Windows 识别成 Public）

只勾一项的话，手机扫码会看到 `Safari cannot open the page because the network connection was lost`。

如果防火墙框已经被点掉了，PowerShell 跑这个把当前 WiFi 改成 Private：

```powershell
Set-NetConnectionProfile -InterfaceAlias 'Wi-Fi' -NetworkCategory Private
```

跑完 `--background` 模式后**不需要保持终端窗口开着** —— mobile.py 已用 `DETACHED_PROCESS` 标志让子进程脱离 console，关掉 cmd / PowerShell 后 HTTP server 继续活。停服务用 `taskkill /F /PID <PID>`（box 里会印出来）。

准备好后，直接说 "下载 <你的邮箱> <日期> 的内容" 即可触发。

## 触发示例

```
下载 your-email@example.com 2026-05-22 的内容
```

```
拉 your-email@example.com 2026-05-21~2026-05-22 的素材
```

```
mobile share your-email@example.com 2026-05-22
```

```
your-email@example.com 2026-05-22
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

### Step 2 - 跑 mobile.py（**Claude 必须用 `--background`**）

执行本 skill 目录下的 `mobile.py`（与本 SKILL.md 同目录）。Claude 根据读到本 SKILL.md 的位置自动构造绝对路径。

**Claude 在 Bash 里跑时必须加 `--background`**——否则脚本会阻塞在 `httpd.serve_forever()`，Bash 命令卡死，Claude 没法回复用户。

```bash
python3 <skill-dir>/mobile.py \
  --email "your-email@example.com" \
  --date "2026-05-22" \
  --background
```

`--background` 行为：
1. 拉数据 + 下载视频 + 生成 HTML/QR（同正常模式）
2. 起 `python3 -m http.server` 子进程（脱离父进程会话，跑到后台）
3. **自动 `webbrowser.open(http://localhost:port)`** 在用户默认浏览器打开站点
4. mobile.py 主进程立刻退出（不阻塞 Bash / Claude）

输出最后会有 box 显示：电脑访问 URL / 手机扫码 URL / PID / 怎么停。

参数：
- `--background`（**推荐 Claude 默认用**）：后台起服务 + 自动开浏览器 + 立即退出
- `--share`：**给别人发链接时用**——起 cloudflared quick tunnel，二维码里写公网 `https://xxx.trycloudflare.com`，任何手机任何网络都能扫，不依赖同 WiFi / 不依赖防火墙 / 不依赖操作系统。需先装 `cloudflared`（macOS: `brew install cloudflared`，Windows: `winget install --id Cloudflare.cloudflared`）。详见下文「给别人发公网链接」章节。
- `--no-serve`：只生成文件不起服务（用户后续手动起）
- `--refresh-only`：**切换 WiFi 后用**——跳过 API 和视频下载，从本地缓存秒级重生二维码 + HTML。可以和 `--background` 组合（`--refresh-only --background`）
- `--port 9000`：指定 HTTP 端口（默认 8080，被占用自动找下一个，显式提示「请求 X 用了 Y」）
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

`--background` 模式下，mobile.py 跑完立刻退出，已经做了 3 件事：
- ✅ 子进程后台跑 http.server
- ✅ 浏览器自动打开了
- ✅ box 输出印了 URL + PID

Claude 应该把 box 内容**复述给用户**，并告诉：

1. **浏览器应该已自动打开** `http://localhost:<port>`（如果没自动开，让用户手动复制 URL）
2. **手机扫首页二维码**（前提是手机和电脑同 WiFi）
3. **停服务**：`kill <PID>` 或告诉 Claude「停服务」
4. **WiFi 换了？** 告诉用户跑同样命令带 `--refresh-only --background`，秒级重生不下载

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
~/Desktop/xcmo-mobile/your-email@example.com/20260522/
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

## 给别人发公网链接（`--share` 模式）

默认 LAN IP 模式只能"自己手机扫自己电脑"。任何"发给别人"的场景都会踩 LAN 隔离的坑：

- 别人手机和电脑不同 WiFi → 路由不通，Safari 报 `network connection was lost`
- 公共 WiFi / 公司 WiFi 开了 AP Isolation → 同 SSID 也互相看不到
- Windows 防火墙挡 Python → 弹框点错一次就全废
- 截图发别人扫 → 截图被压缩，二维码相机识别不到
- 别人电脑休眠 → HTTP server 被挂起，:8080 不响应

**`--share` 模式用 [cloudflared quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) 暴露公网 URL**，二维码里写 `https://random-1234.trycloudflare.com/<人物>.html`。任何手机任何网络扫都通，不依赖同 WiFi、不依赖防火墙、不依赖操作系统、不依赖能不能 ping LAN IP。

### 前置：装 cloudflared

```bash
# macOS
brew install cloudflared

# Windows
winget install --id Cloudflare.cloudflared

# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o /tmp/cloudflared.deb && sudo dpkg -i /tmp/cloudflared.deb
```

不需要 Cloudflare 账号，quick tunnel 是临时随机域名，两个进程一停 URL 立刻失效——跑完不留后门。

### 用法

```bash
python3 <skill-dir>/mobile.py \
  --email your-email@example.com \
  --date 2026-05-22 \
  --share
```

或对话里说："**下载 xxx@yyy.com 2026-05-22 的内容，用 --share 出公网链接发给别人**"。

### 行为（与默认模式的差异）

1. 拉数据 + 下载视频（同正常模式）
2. 起本地 `python -m http.server` 子进程（tunnel 转发的目标）+ 健康自检
3. 起 `cloudflared tunnel --url http://localhost:<port>` 子进程，tail 日志等 stdout 出现 `https://xxx.trycloudflare.com`（最多 60 秒）
4. **用公网 tunnel URL 生成 QR + HTML**（与 LAN 模式的区别就在这一步）
5. 浏览器自动打开公网链接
6. 输出 box 显示：公网 URL + server PID + tunnel PID + 两个日志路径 + 停止命令

### 停止

```bash
kill <server_pid> <tunnel_pid>             # macOS / Linux
taskkill /F /PID <server_pid> <tunnel_pid> # Windows
```

或者跟 Claude 说"停服务"，让 Claude 帮你 kill 两个 PID。

### 失败处理

| 情况 | 表现 | 处理 |
|---|---|---|
| 没装 cloudflared | `❌ 未找到 cloudflared 命令` | 按上方"前置：装 cloudflared"装 |
| cloudflared 启动 60s 内没拿到 URL | `cloudflared 在 60 秒内没拿到公网 URL` | 看 `_tunnel.log`，可能 Cloudflare 边缘节点抖动，重跑一次 |
| 本地 server 起不来 | `本地 HTTP server 起不来` | 看 `_server.log`，可能端口被占 / 权限问题 |

## 错误处理

| 情况 | 处理 |
|---|---|
| 邮箱在 scope 里找不到 | 退出码 5，stderr 列出可选邮箱 |
| token 失效（401/403）| 退出码 4，引导更新 token |
| session 文件缺失 | 退出码 3 |
| `qrcode` / `pillow` 没装 | 退出码 2 + 提示 `pip3 install qrcode pillow` |
| 某个 asset 拉取失败 | 跳过 + warning，不阻塞其他 |
| 某个视频下载失败 | 重试 1 次，仍失败 → 跳过（html 里仍写文案/标签）|
| 端口被占用 | 自动找 8080..8090 区间内的空闲端口，**显式打印「请求 X 用了 Y」**，避免用户搞混 |
| WiFi 切换 / IP 变化 | 旧二维码失效，告诉用户跑 `--refresh-only` 用本地缓存秒级重生 |
| HTML 写入失败（disk full / 权限）| 立刻 RuntimeError + 非 0 退出，不会静默成功 |

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
- 标准库：`urllib`, `http.server`, `socket`, `socketserver`, `webbrowser`, `html`, `shutil`, `time`
- **可选**：`cloudflared`（仅 `--share` 模式需要）

## 触发关键词

中文：下载 / 拉 / 导出 / mobile / 手机扫码 / 扫码看  
英文：mobile share / pull / fetch / download

**`--share` 模式专属触发**（需先装 cloudflared）：发给别人 / 公网链接 / 远程访问 / 不同 WiFi / 出公网 / 分享给朋友 / tunnel / share

通常用户会说邮箱 + 日期，Claude 应识别这种组合直接触发。
