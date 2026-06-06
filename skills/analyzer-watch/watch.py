#!/usr/bin/env python3
"""watch.py - 监听 TikTok Analyzer，把破阈值的爆款视频推送到飞书群。

仅标准库（urllib + json + re），无需 pip install。

命令：
    run         登录 → 查当天 + 热门视频 → 筛(播放 > 阈值 或 ER > 阈值) → diff seen
                → 逐条推飞书卡片 → commit。首次跑(无 seen)= baseline：把现有达标
                视频全记 seen 但不推（避免首跑把上百条历史刷爆群）。
    run --dry-run   只 diff 不推，看会推哪些。
    log         查推送历史。

配置：~/.config/ops-skills/analyzer-watch.yaml
      base_url / email / password / feishu_webhook / view_threshold / er_threshold
state：~/.config/ops-skills/analyzer-watch-seen.json（跨 plugin 升级保留）
"""
from __future__ import annotations

import argparse
import datetime
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


def load_config() -> dict:
    """读 yaml 配置（简单正则，不依赖 PyYAML）。"""
    if not CONFIG_FILE.exists():
        print(json.dumps({"error": f"配置不存在: {CONFIG_FILE}（去建 analyzer-watch.yaml）"},
                         ensure_ascii=False))
        sys.exit(1)
    text = CONFIG_FILE.read_text(encoding="utf-8")

    def g(key: str, default: str | None = None) -> str | None:
        m = re.search(rf'^{key}:\s*"?([^"\n]+?)"?\s*$', text, re.M)
        return m.group(1).strip() if m else default

    return {
        "base_url": (g("base_url") or "").rstrip("/"),
        "email": g("email"),
        "password": g("password"),
        "webhook": g("feishu_webhook"),
        "view_th": float(g("view_threshold", "500")),
        "er_th": float(g("er_threshold", "5")),
    }


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
    return r["access_token"]


def fetch_candidates(cfg: dict, token: str) -> list[dict]:
    """查 daily(当天) + trending(热门)，按 video_id 合并去重。"""
    today = datetime.date.today().isoformat()
    by_id: dict[str, dict] = {}
    for url in (f"{cfg['base_url']}/api/metrics/daily?date={today}&limit=500",
                f"{cfg['base_url']}/api/metrics/trending?limit=100"):
        try:
            for item in http_json(url, token=token):
                v = item.get("video", item)
                vid = v.get("tiktok_video_id")
                if vid and vid not in by_id:
                    by_id[vid] = v
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
            continue
    return list(by_id.values())


def find_hits(videos: list[dict], cfg: dict) -> list[tuple]:
    """筛破阈值的视频。返回 [(video, views, er, reasons)]。"""
    out = []
    for v in videos:
        metrics = v.get("latest_metrics") or {}
        views = metrics.get("views") or 0
        er = v.get("engagement_rate") or 0
        reasons = []
        if views > cfg["view_th"]:
            reasons.append(f"播放破{int(cfg['view_th'])}")
        if er > cfg["er_th"]:
            reasons.append(f"ER破{cfg['er_th']:g}%")
        if reasons:
            out.append((v, views, er, reasons))
    return out


def load_seen() -> set[str] | None:
    """读 seen。不存在返回 None（= baseline 信号）。"""
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


def push_card(webhook: str, v: dict, views: int, er: float, reasons: list[str]) -> bool:
    m = v.get("latest_metrics") or {}
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "🔥 爆款预警：视频破阈值"},
                       "template": "red"},
            "elements": [
                {"tag": "div", "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**账号**\n@{handle_of(v)}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**命中**\n{' + '.join(reasons)}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**播放**\n{views:,}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**ER**\n{er}%"}},
                ]},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"💬 {(v.get('description') or '')[:80]}"}},
                {"tag": "div", "text": {"tag": "lark_md",
                 "content": f"👍 {m.get('likes', 0)} · 💬 {m.get('comments', 0)} · "
                            f"↗️ {m.get('shares', 0)} · 🔖 {m.get('collects', 0)}"}},
                {"tag": "action", "actions": [{"tag": "button",
                 "text": {"tag": "plain_text", "content": "看视频 ▶"}, "url": v["url"], "type": "primary"}]},
            ],
        },
    }
    try:
        r = http_json(webhook, "POST", payload=card)
        return r.get("code") == 0 or r.get("StatusCode") == 0
    except (urllib.error.URLError, TimeoutError):
        return False


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not cfg["webhook"] or "xxxxx" in (cfg["webhook"] or ""):
        print(json.dumps({"error": "feishu_webhook 未配置"}, ensure_ascii=False))
        return 1
    try:
        token = login(cfg)
    except (urllib.error.URLError, TimeoutError, KeyError) as exc:
        print(json.dumps({"error": f"登录失败: {exc}"}, ensure_ascii=False))
        return 1

    hit_list = find_hits(fetch_candidates(cfg, token), cfg)
    seen = load_seen()
    current_ids = {v["tiktok_video_id"] for v, *_ in hit_list}

    if seen is None:  # baseline：首次记 seen 不推
        save_seen(current_ids)
        print(json.dumps({"mode": "baseline", "total_hits": len(hit_list), "pushed": 0},
                         ensure_ascii=False))
        return 0

    new = [(v, vw, er, r) for v, vw, er, r in hit_list if v["tiktok_video_id"] not in seen]

    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "new": len(new), "videos": [
            {"handle": handle_of(v), "reasons": r, "views": vw, "er": er, "url": v["url"]}
            for v, vw, er, r in new]}, ensure_ascii=False, indent=2))
        return 0

    if not new:
        print(json.dumps({"mode": "incremental", "new": 0, "pushed": 0}, ensure_ascii=False))
        return 0

    pushed, logs = [], []
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    for v, vw, er, r in new:
        if push_card(cfg["webhook"], v, vw, er, r):
            pushed.append(v["tiktok_video_id"])
            logs.append({"pushed_at": now, "handle": handle_of(v), "views": vw,
                         "er": er, "reasons": r, "url": v["url"]})
    save_seen(seen | set(pushed))  # 只 commit 推成功的，失败的下轮重试
    append_pushlog(logs)
    print(json.dumps({"mode": "incremental", "new": len(new), "pushed": len(pushed)},
                     ensure_ascii=False))
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
    pr = sub.add_parser("run", help="查→筛→去重→推飞书（首次 baseline 不推）")
    pr.add_argument("--dry-run", action="store_true", help="只看会推哪些，不真推")
    pr.set_defaults(func=cmd_run)
    pl = sub.add_parser("log", help="查推送历史")
    pl.add_argument("--tail", type=int, default=20)
    pl.set_defaults(func=cmd_log)
    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
