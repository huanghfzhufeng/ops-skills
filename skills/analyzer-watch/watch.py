#!/usr/bin/env python3
"""watch.py - 监听 TikTok Analyzer，把破阈值的爆款视频推送到飞书群。

仅标准库（urllib + json + re + datetime + io），无需 pip install。

命令：
    run         登录 → 拉全量视频 → 筛(播放>阈值 或 (ER>阈值 且 播放>=最低播放))
                → diff seen → 逐条推飞书卡片 → commit。首次跑= baseline，只记不推。
    run --dry-run   只 diff 不推。
    log         查推送历史。

命中逻辑：播放 > view_threshold  或  ( ER > er_threshold% 且 播放 >= er_min_views )

卡片封面图（可选，配了 feishu_app_id/secret 才启用）：
    个人飞书自建应用加不了群，所以走「app 只上传图、发送仍用 webhook」——webhook 认 app
    上传的 image_key。封面 URL 用 TikTok oEmbed 实时取（analyzer 存的带签名、会过期）。
    访问 TikTok 要走 proxy。整条封面链路任一步失败 → 自动降级纯文字卡，推送绝不中断。

配置：~/.config/ops-skills/analyzer-watch.yaml
state：~/.config/ops-skills/analyzer-watch-seen.json（跨 plugin 升级保留）
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

STATE_DIR = Path.home() / ".config" / "ops-skills"
CONFIG_FILE = STATE_DIR / "analyzer-watch.yaml"
SEEN_FILE = STATE_DIR / "analyzer-watch-seen.json"
PUSHLOG_FILE = STATE_DIR / "analyzer-watch-pushlog.jsonl"
MAX_PUSH = 15        # 单次推送上限，防异常爆量刷屏 + 飞书限流
FETCH_LIMIT = 50000  # 拉全量视频的 limit；设远大于总视频数，逼近时告警
FEISHU = "https://open.feishu.cn/open-apis"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(json.dumps({"error": f"配置不存在: {CONFIG_FILE}"}, ensure_ascii=False))
        sys.exit(1)
    try:
        CONFIG_FILE.chmod(0o600)  # 含密码/app_secret，收紧权限防同机其他用户读取
    except OSError:
        pass
    text = CONFIG_FILE.read_text(encoding="utf-8")

    def g(key: str, default: str | None = None) -> str | None:
        m = re.search(rf'^{re.escape(key)}:\s*(.+?)\s*$', text, re.M)
        if not m:
            return default
        val = m.group(1).strip()
        if val and val[0] in "\"'":            # 带引号：取引号内，值里的 # 不算注释
            q = val[0]
            end = val.find(q, 1)
            return val[1:end] if end > 0 else val[1:]
        return re.split(r"\s+#", val, maxsplit=1)[0].strip()  # 无引号：剥掉行内 # 注释

    cfg = {
        "base_url": (g("base_url") or "").rstrip("/"),
        "email": g("email"),
        "password": g("password"),
        "webhook": g("feishu_webhook"),
        "view_th": float(g("view_threshold", "500")),
        "er_th": float(g("er_threshold", "5")),
        "er_min_views": float(g("er_min_views", "500")),       # ER 命中的最低播放
        "er_max_age_days": float(g("er_max_age_days", "7")),   # ER 命中要求发布 ≤ N 天（周会版）
        "app_id": g("feishu_app_id"),        # 可选：封面图用
        "app_secret": g("feishu_app_secret"),
        "proxy": g("proxy"),                  # 可选：访问 TikTok 用
    }
    missing = [k for k in ("base_url", "email", "password", "webhook") if not cfg[k]]
    if missing:
        print(json.dumps({"error": f"配置缺字段: {missing}"}, ensure_ascii=False))
        sys.exit(1)
    if "xxxxx" in (cfg["webhook"] or ""):
        print(json.dumps({"error": "feishu_webhook 还是占位符"}, ensure_ascii=False))
        sys.exit(1)
    return cfg


def http_json(url: str, method: str = "GET", token: str | None = None,
              payload: dict | None = None, timeout: int = 20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", "ignore"))


def login(cfg: dict) -> str:
    r = http_json(f"{cfg['base_url']}/api/auth/login", "POST",
                  payload={"email": cfg["email"], "password": cfg["password"]})
    tok = r.get("access_token")
    if not tok:
        raise ValueError("登录返回里没有 access_token")
    return tok


def fetch_candidates(cfg: dict, token: str) -> tuple[list[dict], int]:
    """拉【全量】追踪视频（trending?limit 大 = 所有视频按热度排）。全量才不漏慢热视频。
    返回 (videos, ok)；ok=0 表示拉取失败（→ 上层跳过本轮，不建空 baseline）。"""
    try:
        data = http_json(f"{cfg['base_url']}/api/metrics/trending?limit={FETCH_LIMIT}",
                         token=token, timeout=40)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, TypeError):
        return [], 0
    videos = []
    for item in data:
        v = item.get("video", item)
        vid = v.get("tiktok_video_id")
        if not vid:
            continue
        videos.append({
            "tiktok_video_id": vid,
            "url": v.get("url", ""),
            "description": v.get("description") or "",
            "created_at": v.get("created_at"),
            "latest_metrics": v.get("latest_metrics") or {},
            "engagement_rate": v.get("engagement_rate") or 0,
        })
    return videos, 1


def _age_days(created_str: str | None, now: datetime.datetime) -> float:
    """视频发布距今天数；created_at 缺失/异常 → 999（视为很老，不满足新视频约束）。"""
    if not created_str:
        return 999
    try:
        created = datetime.datetime.fromisoformat(created_str).replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return 999
    return (now - created).days


def find_hits(videos: list[dict], cfg: dict) -> list[tuple]:
    """命中逻辑（周会版）：
       播放 > view_th(1000)                                              → 纯流量爆款
       或 (ER > er_th% 且 播放 > er_min_views 且 发布 ≤ er_max_age_days 天) → 高互动新视频
    """
    out = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for v in videos:
        metrics = v.get("latest_metrics") or {}
        views = metrics.get("views") or 0
        er = v.get("engagement_rate") or 0
        reasons = []
        if views > cfg["view_th"]:                              # 纯流量爆款（不管 ER/时间）
            reasons.append(f"播放破{int(cfg['view_th'])}")
        if (er > cfg["er_th"] and views > cfg["er_min_views"]   # 高互动新视频
                and _age_days(v.get("created_at"), now) <= cfg["er_max_age_days"]):
            reasons.append(f"ER破{cfg['er_th']:g}%·{int(cfg['er_max_age_days'])}天新")
        if reasons:
            out.append((v, views, er, reasons))
    return out


def load_seen() -> set[str] | None:
    if not SEEN_FILE.exists():
        return None
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8"))["seen"])
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def save_seen(ids: set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"seen": sorted(ids), "count": len(ids)}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(SEEN_FILE)


def append_pushlog(entries: list[dict]) -> None:
    if not entries:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with PUSHLOG_FILE.open("a", encoding="utf-8") as f:
        f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))


def handle_of(v: dict) -> str:
    try:
        return v["url"].split("/@")[1].split("/")[0]
    except (IndexError, KeyError):
        return "?"


def rel_time(created_str: str | None) -> str:
    """发布时间(UTC ISO) → 相对时间，让运营一眼分新爆/慢热。"""
    if not created_str:
        return ""
    try:
        created = datetime.datetime.fromisoformat(created_str).replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return ""
    elapsed = datetime.datetime.now(datetime.timezone.utc) - created
    if elapsed.total_seconds() < 0:
        return "刚发布"
    if elapsed.days >= 1:
        return f"发布{elapsed.days}天前"
    hours = int(elapsed.total_seconds() // 3600)
    return f"发布{hours}小时前" if hours >= 1 else "刚发布"


# ---------- 封面图（可选；任一步失败 → 返回 None，push_card 自动降级纯文字卡）----------

def _open_proxy(req: urllib.request.Request, proxy: str | None, timeout: int):
    """用指定代理打开请求；proxy=None 显式直连（不读环境变量，定时任务环境更可控）。"""
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {})
    return urllib.request.build_opener(handler).open(req, timeout=timeout)


def get_tenant_token(cfg: dict) -> str | None:
    """app 凭证换 tenant_access_token。没配 app 凭证或失败 → None（降级纯文字卡）。"""
    if not cfg.get("app_id") or not cfg.get("app_secret"):
        return None
    try:
        r = http_json(f"{FEISHU}/auth/v3/tenant_access_token/internal", "POST",
                      payload={"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]})
        return r.get("tenant_access_token")
    except (urllib.error.URLError, TimeoutError):
        return None


def upload_feishu_image(app_token: str, img: bytes) -> str | None:
    """上传图片到飞书拿 image_key（飞书直连）。失败 → None。"""
    bd = "----wbBoundary7391x"
    body = b"".join([
        f"--{bd}\r\n".encode(),
        b'Content-Disposition: form-data; name="image_type"\r\n\r\nmessage\r\n',
        f"--{bd}\r\n".encode(),
        b'Content-Disposition: form-data; name="image"; filename="c.jpg"\r\n',
        b"Content-Type: image/jpeg\r\n\r\n", img, f"\r\n--{bd}--\r\n".encode(),
    ])
    req = urllib.request.Request(f"{FEISHU}/im/v1/images", data=body, method="POST",
        headers={"Authorization": f"Bearer {app_token}",
                 "Content-Type": f"multipart/form-data; boundary={bd}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()).get("data", {}).get("image_key")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def fetch_cover_image_key(cfg: dict, video_url: str, app_token: str | None) -> str | None:
    """oEmbed 实时取封面 → 下载 → 上传飞书 → image_key。任一步失败 → None（降级）。"""
    if not app_token or not video_url:
        return None
    proxy = cfg.get("proxy")
    try:
        oreq = urllib.request.Request(f"https://www.tiktok.com/oembed?url={video_url}",
                                      headers={"User-Agent": UA})
        thumb = json.loads(_open_proxy(oreq, proxy, 15).read().decode()).get("thumbnail_url")
        if not thumb:
            return None
        img = _open_proxy(urllib.request.Request(thumb, headers={"User-Agent": UA}), proxy, 20).read()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    return upload_feishu_image(app_token, img)


def push_card(cfg: dict, v: dict, views: int, er: float, app_token: str | None) -> bool:
    """有封面 → 左图右文小卡片；拿不到封面 → 降级纯文字卡。整卡点击跳转视频。"""
    m = v.get("latest_metrics") or {}
    rel = rel_time(v.get("created_at"))
    parts = [f"{label} {m.get(k, 0)}" for k, label in
             (("likes", "赞"), ("comments", "评"), ("shares", "转"), ("collects", "藏")) if m.get(k)]
    engage = " · ".join(parts) if parts else "暂无互动"
    url = v.get("url", "")

    image_key = fetch_cover_image_key(cfg, url, app_token)
    if image_key:
        txt = (f"**播放 {views:,}** ｜ **ER {er}%**\n{rel}\n"
               f"<font color='grey'>{engage}</font>　[看视频]({url})")
        elements = [{"tag": "column_set", "flex_mode": "none", "horizontal_spacing": "default", "columns": [
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "center",
             "elements": [{"tag": "img", "img_key": image_key,
                           "alt": {"tag": "plain_text", "content": ""}, "mode": "fit_horizontal"}]},
            {"tag": "column", "width": "weighted", "weight": 3, "vertical_align": "center",
             "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": txt}}]},
        ]}]
    else:
        line1 = f"**播放 {views:,}** ｜ **ER {er}%**" + (f" ｜ {rel}" if rel else "")
        elements = [{"tag": "div", "text": {"tag": "lark_md",
                     "content": f"{line1}\n<font color='grey'>{engage}　[看视频]({url})</font>"}}]

    card = {"msg_type": "interactive", "card": {
        "config": {"wide_screen_mode": True},
        "card_link": {"url": url},
        "header": {"title": {"tag": "plain_text", "content": f"爆款预警 · @{handle_of(v)}"}, "template": "red"},
        "elements": elements,
    }}
    try:
        r = http_json(cfg["webhook"], "POST", payload=card)
        return r.get("code") == 0 or r.get("StatusCode") == 0
    except (urllib.error.URLError, TimeoutError):
        return False


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    try:
        token = login(cfg)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        print(json.dumps({"error": f"登录失败: {exc}"}, ensure_ascii=False))
        return 1

    videos, ok_sources = fetch_candidates(cfg, token)
    if ok_sources == 0:
        print(json.dumps({"error": "数据源抓取失败，跳过本轮（不建 baseline、不推）"}, ensure_ascii=False))
        return 1
    truncated_fetch = len(videos) >= FETCH_LIMIT

    hit_list = find_hits(videos, cfg)
    seen = load_seen()
    current_ids = {v["tiktok_video_id"] for v, *_ in hit_list}

    def stamp(out: dict) -> dict:
        if truncated_fetch:
            out["warn"] = f"视频数触达上限 {FETCH_LIMIT}，可能被截断，请调大 FETCH_LIMIT"
        return out

    if seen is None:
        save_seen(current_ids)
        print(json.dumps(stamp({"mode": "baseline", "total_hits": len(hit_list), "pushed": 0}),
                         ensure_ascii=False))
        return 0

    new = [(v, vw, er, r) for v, vw, er, r in hit_list if v["tiktok_video_id"] not in seen]

    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "new": len(new), "videos": [
            {"handle": handle_of(v), "reasons": r, "views": vw, "er": er, "url": v["url"]}
            for v, vw, er, r in new]}, ensure_ascii=False, indent=2))
        return 0

    if not new:
        print(json.dumps(stamp({"mode": "incremental", "new": 0, "pushed": 0}), ensure_ascii=False))
        return 0

    truncated = len(new) > MAX_PUSH
    batch = sorted(new, key=lambda x: -x[1])[:MAX_PUSH]
    app_token = get_tenant_token(cfg)  # 封面用；None 则全部降级纯文字卡

    pushed, logs = [], []
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    for v, vw, er, r in batch:
        if push_card(cfg, v, vw, er, app_token):
            pushed.append(v["tiktok_video_id"])
            logs.append({"pushed_at": now, "handle": handle_of(v), "views": vw,
                         "er": er, "reasons": r, "url": v["url"]})
    save_seen(seen | set(pushed))
    append_pushlog(logs)

    out = stamp({"mode": "incremental", "new": len(new), "pushed": len(pushed),
                 "cover": "on" if app_token else "off"})
    if truncated:
        out["note"] = f"本轮 {len(new)} 条超上限，按播放推了前 {MAX_PUSH} 条，剩余下轮继续"
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    if not PUSHLOG_FILE.exists():
        print("(无推送历史)")
        return 0
    lines = PUSHLOG_FILE.read_text(encoding="utf-8").splitlines()
    for ln in (lines if args.tail == 0 else lines[-args.tail:]):
        try:
            e = json.loads(ln)
            print(f"{e['pushed_at']} | @{e['handle']} | {'+'.join(e['reasons'])} | "
                  f"views={e['views']} er={e['er']}% | {e['url']}")
        except (json.JSONDecodeError, KeyError):
            pass
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="TikTok Analyzer 破阈值视频 → 飞书推送")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run", help="拉→筛→去重→推飞书（首次 baseline 不推）")
    pr.add_argument("--dry-run", action="store_true", help="只看会推哪些，不真推")
    pr.set_defaults(func=cmd_run)
    pl = sub.add_parser("log", help="查推送历史")
    pl.add_argument("--tail", type=int, default=20)
    pl.set_defaults(func=cmd_log)
    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
