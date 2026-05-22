#!/usr/bin/env python3
"""xcmo-mobile: 按邮箱 + 日期拉 xcmo 平台上该用户当天生成的所有视频，
按人物分组下载到本地，生成 HTML 站点 + 每人物一个二维码，
起本地 HTTP 服务器供手机扫码访问（看视频/复制文案/复制标签）。

典型用法：
    python3 mobile.py --email luyuyue@liao.com --date 2026-05-22
    python3 mobile.py --email luyuyue@liao.com --date 2026-05-21~2026-05-22
    python3 mobile.py --email luyuyue@liao.com --date 2026-05-22 --no-serve
    python3 mobile.py --email luyuyue@liao.com --date 2026-05-22 --port 9000

读取 ~/.claude/memory/xcmo-session.json 拿 vee_session token 做认证。

退出码:
    0  成功
    2  qrcode/pillow 缺失
    3  session 文件缺失
    4  TOKEN 失效（401/403）
    5  邮箱在 scope 里找不到
"""

import argparse
import html
import http.server
import json
import os
import re
import socket
import socketserver
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import qrcode
except ImportError:
    print("❌ 缺少 qrcode 库, 请先装: pip3 install qrcode pillow", file=sys.stderr)
    sys.exit(2)


XCMO_BASE = "https://xcmo.ai"
SESSION_FILE = Path.home() / ".claude/memory/xcmo-session.json"

# Cloudflare 拒绝默认 Python-urllib UA，必须用浏览器 UA 绕开 Error 1010
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class AuthExpiredError(RuntimeError):
    """xcmo session token 失效或过期。"""


# ─── 工具函数（纯函数，好测）────────────────────────────────────────────

def normalize_date(s: str) -> str:
    """统一日期到 YYYY-MM-DD 格式。

    支持: '2026-05-22' / '20260522'.
    """
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    raise ValueError(f"无法解析日期 '{s}'（支持 YYYY-MM-DD 或 YYYYMMDD）")


def parse_date_range(date_arg: str) -> tuple[str, str]:
    """解析日期参数为 (date_from, date_to) 元组。

    支持单日 '2026-05-22' 或区间 '2026-05-21~2026-05-22'。
    """
    date_arg = date_arg.strip()
    for sep in ("~", "to", " - "):
        if sep in date_arg:
            parts = [p.strip() for p in date_arg.split(sep, 1)]
            return normalize_date(parts[0]), normalize_date(parts[1])
    d = normalize_date(date_arg)
    return d, d


def sanitize_filename(name: str, max_len: int = 50) -> str:
    """文件名安全化（去掉文件系统特殊字符）。"""
    bad = '<>:"/\\|?*\n\r\t'
    cleaned = "".join(c if c not in bad else "-" for c in (name or "")).strip()
    return cleaned[:max_len] if len(cleaned) > max_len else cleaned


def safe_character_id(cid: Optional[str]) -> str:
    """character_id 可能 None / 空，给一个安全默认（'_unknown'）。"""
    if not cid:
        return "_unknown"
    return sanitize_filename(cid, 40)


def video_filename(asset: dict) -> str:
    """生成本地视频文件名：'{任务名} {asset8}.mp4'。"""
    name = sanitize_filename(asset.get("name") or "video", 60)
    short_id = asset["id"][:8]
    return f"{name} {short_id}.mp4"


def thumb_filename(asset: dict) -> str:
    """生成缩略图文件名：'{任务名} {asset8}.jpg'。"""
    name = sanitize_filename(asset.get("name") or "video", 60)
    short_id = asset["id"][:8]
    return f"{name} {short_id}.jpg"


def get_lan_ip() -> str:
    """检测本机 LAN IP（让手机能访问到本机服务）。

    技巧：连一下外网（UDP 不真发包），让 OS 选 outgoing 网卡，
    那个网卡的 IP 就是 LAN IP。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_free_port(start: int, end: int) -> int:
    """从 start 找到第一个空闲端口（[start, end) 区间）。"""
    for port in range(start, end):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("", port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"端口 {start}-{end} 都被占用")


# ─── HTTP / API 函数 ──────────────────────────────────────────────────

def load_session() -> dict:
    """读 ~/.claude/memory/xcmo-session.json 拿 token。"""
    if not SESSION_FILE.exists():
        print(
            f"❌ 没找到 xcmo session 文件: {SESSION_FILE}\n"
            "请先告诉 Claude 你的 vee_session token，让它写入这个文件。",
            file=sys.stderr,
        )
        sys.exit(3)
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    if not data.get("vee_session"):
        print(
            f"❌ session 文件存在但 vee_session 字段为空: {SESSION_FILE}",
            file=sys.stderr,
        )
        sys.exit(3)
    return data


def http_get_json(url: str, session: dict) -> any:
    """GET with cookie auth + JSON 解析。401/403 抛 AuthExpiredError。"""
    req = urllib.request.Request(
        url,
        headers={
            "Cookie": f"vee_session={session['vee_session']}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code in (401, 403):
            raise AuthExpiredError(f"HTTP {e.code}: token 失效。body: {body}")
        raise RuntimeError(f"HTTP {e.code} {url}\n  body: {body}")
    return json.loads(resp.read().decode("utf-8"))


def download_file(url: str, dest: Path, session: dict) -> bool:
    """下载文件到 dest，返回是否成功。失败重试 1 次。"""
    full_url = url if url.startswith("http") else XCMO_BASE + url
    req = urllib.request.Request(
        full_url,
        headers={
            "Cookie": f"vee_session={session['vee_session']}",
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                dest.write_bytes(resp.read())
            return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthExpiredError(f"HTTP {e.code} 下载时 token 失效")
            if attempt == 1:
                print(f"    ❌ 下载失败 {full_url}: {e}", file=sys.stderr)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt == 1:
                print(f"    ❌ 下载失败 {full_url}: {e}", file=sys.stderr)
    return False


def resolve_email_to_user_id(email: str, scope_id: str, session: dict) -> str:
    """查 scope members 找邮箱对应的 user_id。"""
    members = http_get_json(f"{XCMO_BASE}/api/scopes/{scope_id}/members", session)
    for m in members:
        if m.get("user_email", "").lower() == email.lower():
            return m["user_id"]
    available = [m.get("user_email") for m in members]
    raise ValueError(
        f"在 scope {scope_id[:8]} 里没找到邮箱 '{email}'。\n"
        f"  当前 scope 内的邮箱: {available}"
    )


# ─── HTML 渲染 ────────────────────────────────────────────────────────

def render_item(asset: dict, character_id: str, index: int) -> str:
    """渲染单个视频卡片。"""
    video_name = video_filename(asset)
    thumb_name = thumb_filename(asset)

    # URL-encode 文件名（含中文、× 等非 ASCII 字符时 src 必须 encoded）
    video_src = f"videos/{urllib.parse.quote(character_id)}/{urllib.parse.quote(video_name)}"
    thumb_src = f"videos/{urllib.parse.quote(character_id)}/{urllib.parse.quote(thumb_name)}"

    has_thumb = bool(asset.get("thumb_url"))
    poster_attr = f' poster="{html.escape(thumb_src)}"' if has_thumb else ""

    caption = asset.get("caption") or ""
    tags = " ".join(asset.get("asset_hashtags") or [])

    # 合并文案 + 标签为一段：一次复制粘到抖音 / TikTok 描述框就完事
    if caption and tags:
        combined = f"{caption}\n\n{tags}"
    elif caption:
        combined = caption
    elif tags:
        combined = tags
    else:
        combined = ""

    # data-text 用于 JS 复制，要 escape 引号
    combined_attr = html.escape(combined, quote=True)
    combined_display = html.escape(combined) if combined else "—"

    return f"""<section class="video-item">
  <h2>视频 {index}</h2>
  <video controls preload="metadata"{poster_attr}>
    <source src="{html.escape(video_src)}" type="video/mp4">
  </video>
  <a class="btn-download" href="{html.escape(video_src)}" download>📥 下载视频</a>

  <div class="copy-section">
    <h3>📝 文案 + 标签 <button class="btn-copy" data-text="{combined_attr}">📋 一键复制</button></h3>
    <pre>{combined_display}</pre>
  </div>
</section>
"""


def render_character_card(character_id: str, count: int) -> str:
    """渲染首页的人物卡片。"""
    safe_cid = html.escape(character_id)
    return f"""<div class="character-card">
  <img class="qr" src="qrcodes/{safe_cid}.png" alt="{safe_cid} QR">
  <div class="info">
    <h2><a href="{safe_cid}.html">{safe_cid}</a></h2>
    <p class="count">{count} 个视频</p>
    <p class="hint">📱 手机扫码看 · 💻 点击进入</p>
  </div>
</div>
"""


def render_index(by_character: dict, email: str, date_range: str) -> str:
    """渲染总览页 HTML。"""
    template = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    cards = "".join(
        render_character_card(cid, len(assets))
        for cid, assets in sorted(by_character.items(), key=lambda x: -len(x[1]))
    )
    return (
        template
        .replace("{{EMAIL}}", html.escape(email))
        .replace("{{DATE_RANGE}}", html.escape(date_range))
        .replace("{{CHAR_COUNT}}", str(len(by_character)))
        .replace("{{VIDEO_COUNT}}", str(sum(len(a) for a in by_character.values())))
        .replace("{{CARDS}}", cards)
    )


def render_character_page(character_id: str, assets: list, email: str, date_range: str) -> str:
    """渲染单个人物详情页 HTML。"""
    template = (TEMPLATES_DIR / "character.html").read_text(encoding="utf-8")
    items = "".join(render_item(a, character_id, i) for i, a in enumerate(assets, 1))
    return (
        template
        .replace("{{CHARACTER_ID}}", html.escape(character_id))
        .replace("{{EMAIL}}", html.escape(email))
        .replace("{{DATE_RANGE}}", html.escape(date_range))
        .replace("{{COUNT}}", str(len(assets)))
        .replace("{{ITEMS}}", items)
    )


# ─── 主流程 ────────────────────────────────────────────────────────────

CACHE_FILE_NAME = "_cache.json"


def print_box(title: str, lines: list[str]) -> None:
    """打印一个 ASCII 框框包住的多行内容，让重要信息更显眼。"""
    width = max(len(title), max((len(line) for line in lines), default=0)) + 2
    bar = "─" * width
    print(f"\n┌{bar}┐")
    print(f"│ {title.ljust(width - 1)}│")
    print(f"├{bar}┤")
    for line in lines:
        print(f"│ {line.ljust(width - 1)}│")
    print(f"└{bar}┘")


def serve_site(site_dir: Path, port: int) -> None:
    """切换 cwd 到 site_dir，起 HTTP 服务，阻塞直到 Ctrl+C。"""
    os.chdir(site_dir)
    handler = http.server.SimpleHTTPRequestHandler

    try:
        webbrowser.open(f"http://localhost:{port}")
    except (webbrowser.Error, OSError):
        pass

    with socketserver.TCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 服务已停止")


def resolve_out_dir(
    cli_out_dir: str, email: str, date_from: str, date_to: str,
) -> Path:
    """决定输出根目录路径。"""
    if cli_out_dir:
        return Path(cli_out_dir)
    date_str = (
        date_from.replace("-", "")
        if date_from == date_to
        else f"{date_from.replace('-', '')}-{date_to.replace('-', '')}"
    )
    return Path.home() / "Desktop" / "xcmo-mobile" / email / date_str


def fetch_by_character(
    args_email: str, date_from: str, date_to: str, session: dict,
) -> dict:
    """跑 API 拉数据，返回 character_id → list[asset] 的 dict。"""
    # Step 1: /api/auth/me 拿 scope_id
    me = http_get_json(f"{XCMO_BASE}/api/auth/me", session)
    scope_id = me["scope_id"]
    print(f"🔑 当前认证: {me['email']} (scope={scope_id[:8]})")

    # Step 2: 邮箱 → user_id
    target_user_id = resolve_email_to_user_id(args_email, scope_id, session)
    print(f"🎯 目标用户: {args_email} → {target_user_id[:8]}")

    # Step 3: 拉 task 列表
    print(f"📅 日期范围: {date_from} ~ {date_to}")
    tasks_url = (
        f"{XCMO_BASE}/api/tasks"
        f"?date_from={date_from}&date_to={date_to}"
        f"&submitted_by_user_id={target_user_id}&limit=500"
    )
    tasks = http_get_json(tasks_url, session)
    completed = [
        t for t in tasks
        if t.get("status") == "completed" and (t.get("result") or {}).get("asset_id")
    ]
    print(f"📊 task: 共 {len(tasks)} 个，completed 且有 asset = {len(completed)}")

    if not completed:
        return {}

    # Step 4: 拉每个 asset 完整数据，按人物分组
    print(f"⬇ 拉取 {len(completed)} 个 asset 详细数据...")
    by_character: dict = defaultdict(list)
    for task in completed:
        asset_id = task["result"]["asset_id"]
        try:
            assets = http_get_json(
                f"{XCMO_BASE}/api/assets?asset_id={asset_id}", session,
            )
            if assets:
                a = assets[0]
                cid = safe_character_id(a.get("character_id"))
                by_character[cid].append(a)
        except AuthExpiredError:
            raise
        except (RuntimeError, json.JSONDecodeError) as e:
            print(f"  ⚠ asset {asset_id[:8]} 拉取失败: {e}", file=sys.stderr)

    return dict(by_character)


def download_all_videos(by_character: dict, videos_dir: Path, session: dict) -> None:
    """按人物分组下载视频 + 缩略图。"""
    print("⬇ 下载视频和缩略图...")
    for cid, assets in by_character.items():
        char_dir = videos_dir / cid
        char_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            video_name = video_filename(asset)
            thumb_name = thumb_filename(asset)
            video_dest = char_dir / video_name
            thumb_dest = char_dir / thumb_name

            file_url = asset.get("file_url")
            if file_url and not video_dest.exists():
                print(f"   ⬇ {cid}/{video_name}")
                download_file(file_url, video_dest, session)

            thumb_url = asset.get("thumb_url")
            if thumb_url and not thumb_dest.exists():
                download_file(thumb_url, thumb_dest, session)


def render_site_files(
    by_character: dict, site_dir: Path, qrcodes_dir: Path,
    email: str, date_range_str: str, lan_ip: str, port: int,
) -> None:
    """生成二维码 PNG + HTML 文件 + CSS。fail-fast：写完立刻校验。"""
    # 二维码
    print(f"🔲 生成 {len(by_character)} 个二维码 (URL: http://{lan_ip}:{port}/<人物>.html)...")
    for cid in by_character:
        url = f"http://{lan_ip}:{port}/{cid}.html"
        img = qrcode.make(url)
        img.save(qrcodes_dir / f"{cid}.png")

    # HTML 文件
    print("📝 生成 HTML 站...")
    index_path = site_dir / "index.html"
    index_path.write_text(
        render_index(by_character, email, date_range_str), encoding="utf-8",
    )
    if index_path.stat().st_size < 100:
        raise RuntimeError(f"index.html 写入失败或为空: {index_path}")

    for cid, assets in by_character.items():
        char_path = site_dir / f"{cid}.html"
        char_path.write_text(
            render_character_page(cid, assets, email, date_range_str),
            encoding="utf-8",
        )
        if char_path.stat().st_size < 100:
            raise RuntimeError(f"{cid}.html 写入失败或为空: {char_path}")

    # CSS
    css_path = site_dir / "style.css"
    css_path.write_text(
        (TEMPLATES_DIR / "style.css").read_text(encoding="utf-8"), encoding="utf-8",
    )
    if css_path.stat().st_size < 100:
        raise RuntimeError(f"style.css 写入失败: {css_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="xcmo-mobile: 按邮箱+日期拉素材生成本地手机分享站",
    )
    parser.add_argument("--email", required=True, help="目标用户邮箱（如 luyuyue@liao.com）")
    parser.add_argument(
        "--date", required=True,
        help="日期: '2026-05-22' 或区间 '2026-05-21~2026-05-22'",
    )
    parser.add_argument("--out-dir", default="", help="输出根目录（默认 ~/Desktop/xcmo-mobile/<email>/<date>/）")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 服务端口（默认 8080）")
    parser.add_argument("--no-serve", action="store_true", help="只生成文件，不起服务")
    parser.add_argument(
        "--refresh-only", action="store_true",
        help="跳过 API 调用 + 视频下载，只用本地缓存重生 HTML+二维码（切 WiFi 后用）",
    )
    args = parser.parse_args()

    date_from, date_to = parse_date_range(args.date)
    out_root = resolve_out_dir(args.out_dir, args.email, date_from, date_to)
    site_dir = out_root / "site"
    videos_dir = site_dir / "videos"
    qrcodes_dir = site_dir / "qrcodes"
    cache_path = site_dir / CACHE_FILE_NAME

    try:
        # 决定数据来源：refresh-only 走缓存，否则跑 API
        if args.refresh_only:
            if not cache_path.exists():
                print(
                    f"❌ --refresh-only 需要本地缓存，但 {cache_path} 不存在。\n"
                    f"   请先跑一次正常模式（不带 --refresh-only）。",
                    file=sys.stderr,
                )
                sys.exit(1)
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            by_character = cache["by_character"]
            print(f"♻ refresh-only 模式：从缓存读 {sum(len(a) for a in by_character.values())} 个 asset")
        else:
            session = load_session()
            by_character = fetch_by_character(args.email, date_from, date_to, session)
            if not by_character:
                print("（没有可下载的内容，退出）", file=sys.stderr)
                sys.exit(0)

        # 显示分组（refresh-only 和正常都显示）
        print(f"📁 按人物分组: {len(by_character)} 个人物")
        for cid, assets in sorted(by_character.items(), key=lambda x: -len(x[1])):
            print(f"   · {cid}: {len(assets)} 个")

        # 准备目录
        site_dir.mkdir(parents=True, exist_ok=True)
        qrcodes_dir.mkdir(parents=True, exist_ok=True)

        # 下载视频（refresh-only 跳过）
        if not args.refresh_only:
            videos_dir.mkdir(parents=True, exist_ok=True)
            download_all_videos(by_character, videos_dir, session)
            # 写缓存供下次 --refresh-only 用
            cache_path.write_text(
                json.dumps({
                    "email": args.email,
                    "date_from": date_from,
                    "date_to": date_to,
                    "by_character": by_character,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 检测 LAN IP + 找端口
        lan_ip = get_lan_ip()
        port = find_free_port(args.port, args.port + 10)
        if port != args.port:
            print(
                f"⚠️  请求端口 {args.port} 被占用，自动改用 {port}",
                file=sys.stderr,
            )

        # 生成 HTML + 二维码（fail-fast 内部已 stat 检查）
        date_range_str = (
            date_from if date_from == date_to else f"{date_from} ~ {date_to}"
        )
        render_site_files(
            by_character, site_dir, qrcodes_dir,
            args.email, date_range_str, lan_ip, port,
        )

        # 显眼的完成提示
        print_box("✅ 完成", [
            f"邮箱: {args.email}",
            f"日期: {date_range_str}",
            f"人物: {len(by_character)} 个 · 视频: {sum(len(a) for a in by_character.values())} 个",
            f"目录: {site_dir}",
        ])

        # 起服务
        if args.no_serve:
            print_box("💡 手动起服务", [
                f"cd {site_dir}",
                f"python3 -m http.server {port}",
            ])
            return

        print_box("🌐 服务已启动", [
            f"电脑访问:  http://localhost:{port}",
            f"手机扫码:  http://{lan_ip}:{port}（同 WiFi）",
            f"端口:     {port}（QR 已写入此端口）",
            "停止:     Ctrl+C",
            "",
            "WiFi 换了？跑：mobile.py ... --refresh-only",
        ])

        serve_site(site_dir, port)

    except AuthExpiredError as e:
        print("\n" + "=" * 60, file=sys.stderr)
        print("❌ xcmo session token 失效或过期", file=sys.stderr)
        print(f"   错误: {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("解决: 让 Claude 帮你更新 token:", file=sys.stderr)
        print("  1. 浏览器打开 https://xcmo.ai 登录", file=sys.stderr)
        print("  2. F12 → Application → Cookies → 复制 vee_session 值", file=sys.stderr)
        print("  3. 告诉 Claude: '更新 xcmo token: <你的 token>'", file=sys.stderr)
        sys.exit(4)
    except ValueError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        sys.exit(5)


if __name__ == "__main__":
    main()
