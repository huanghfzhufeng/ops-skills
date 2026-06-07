#!/usr/bin/env python3
"""watch.py - 监听 TikTok Analyzer，把破阈值的爆款视频推送到飞书群。

仅标准库（urllib + json + re + datetime），无需 pip install。

命令：
    run         登录 → 拉全量视频 → 筛(播放>阈值 或 (ER>阈值 且 播放>=最低播放))
                → diff seen → 逐条推飞书卡片 → commit。
                首次跑(无 seen)= baseline：把现有达标视频全记 seen 但不推。
    run --dry-run   只 diff 不推。
    log         查推送历史。

命中逻辑：播放 > view_threshold  或  ( ER > er_threshold% 且 播放 >= er_min_views )
    └ er_min_views(默认 300) 砍掉「低播放 ER 虚高」的噪音：播放几十、ER 却虚高到
      两位数的视频不是爆款，只是分母太小。真爆款分母大、ER 反而低，靠播放阈值抓。

健壮性（已考虑的边界）：
    - 拉取全失败 → 跳过本轮，不建空 baseline、不推（下轮重试）。
    - 数据源全量(trending?limit=FETCH_LIMIT)，慢热老视频也不漏；触达上限主动告警，绝不静默截断。
    - 单次推送上限 MAX_PUSH，超量按播放排序推前 N + 标注剩余。
    - config 必填校验；登录无 token 报错；字段 null 当 0。
    - 单条推送失败不 commit，下轮重试；seen 原子写。

配置：~/.config/ops-skills/analyzer-watch.yaml
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
MAX_PUSH = 15       # 单次推送上限，防异常爆量刷屏 + 飞书限流
FETCH_LIMIT = 50000  # 拉全量视频的 limit；设远大于总视频数（当前约 1300），逼近时会告警


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(json.dumps({"error": f"配置不存在: {CONFIG_FILE}"}, ensure_ascii=False))
        sys.exit(1)
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
        "er_min_views": float(g("er_min_views", "300")),  # ER 命中的最低播放门槛，砍噪音
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
    """拉【全量】追踪视频（trending?limit 设大 = 所有视频按热度排，不只 top）。

    全量才不漏「慢热」视频——10 多天前发、最近才慢慢爬过阈值的，既不在当天 daily、
    也挤不进热门 top。构造精简候选 dict（只留下游要的字段，含发布时间 created_at 和
    过去 24h 播放增长 growth_24h）。返回 (videos, ok)；ok=0 表示拉取失败。
    """
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
            "created_at": v.get("created_at"),                  # 发布时间(UTC ISO)
            "latest_metrics": v.get("latest_metrics") or {},
            "engagement_rate": v.get("engagement_rate") or 0,
            "growth_24h": item.get("views_growth_24h"),         # 过去 24h 播放增长(在外层 item)
        })
    return videos, 1


def find_hits(videos: list[dict], cfg: dict) -> list[tuple]:
    out = []
    for v in videos:
        metrics = v.get("latest_metrics") or {}
        views = metrics.get("views") or 0
        er = v.get("engagement_rate") or 0
        reasons = []
        if views > cfg["view_th"]:
            reasons.append(f"播放破{int(cfg['view_th'])}")
        if er > cfg["er_th"] and views >= cfg["er_min_views"]:  # ER 命中要求播放达门槛，砍噪音
            reasons.append(f"ER破{cfg['er_th']:g}%")
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
    """把发布时间(UTC ISO)算成相对时间，让运营一眼分「新视频起飞」还是「老视频慢热」。"""
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


def push_card(webhook: str, v: dict, views: int, er: float) -> bool:
    """精简卡片（观察期版）：标题=账号；第一行=播放(+24h增长) ｜ ER ｜ 发布多久前；
    第二行灰字=互动(只显非0) + 看视频链接。按需求去掉了命中原因和文案。"""
    m = v.get("latest_metrics") or {}
    views_part = f"**播放 {views:,}**"
    g24 = v.get("growth_24h")
    if g24 is not None:                       # 24h 增长：区分「正在爆」(涨很多) vs「已爆完」(0)
        views_part += f" · 24h{g24:+,}"
    line1 = f"{views_part} ｜ **ER {er}%**"
    rel = rel_time(v.get("created_at"))
    if rel:
        line1 += f" ｜ {rel}"
    parts = [f"{label} {m.get(k, 0)}" for k, label in
             (("likes", "赞"), ("comments", "评"), ("shares", "转"), ("collects", "藏")) if m.get(k)]
    engage = " · ".join(parts) if parts else "暂无互动"
    content = (
        f"{line1}\n"
        f"<font color='grey'>{engage}　[看视频]({v['url']})</font>"
    )
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"爆款预警 · @{handle_of(v)}"},
                       "template": "red"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
        },
    }
    try:
        r = http_json(webhook, "POST", payload=card)
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
    if ok_sources == 0:  # 数据源挂了 → 不建 baseline 不推，下轮重试
        print(json.dumps({"error": "数据源抓取失败，跳过本轮（不建 baseline、不推）"},
                         ensure_ascii=False))
        return 1
    truncated_fetch = len(videos) >= FETCH_LIMIT  # 触达上限 = 可能被截断，必须告警别静默漏

    hit_list = find_hits(videos, cfg)
    seen = load_seen()
    current_ids = {v["tiktok_video_id"] for v, *_ in hit_list}

    def stamp(out: dict) -> dict:
        if truncated_fetch:
            out["warn"] = f"视频数触达上限 {FETCH_LIMIT}，可能被截断，请调大 FETCH_LIMIT"
        return out

    if seen is None:  # baseline：首次记 seen 不推
        save_seen(current_ids)
        print(json.dumps(stamp({"mode": "baseline", "total_hits": len(hit_list), "pushed": 0}),
                         ensure_ascii=False))
        return 0

    new = [(v, vw, er, r) for v, vw, er, r in hit_list if v["tiktok_video_id"] not in seen]

    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "new": len(new), "videos": [
            {"handle": handle_of(v), "reasons": r, "views": vw, "er": er,
             "created_at": v.get("created_at"), "growth_24h": v.get("growth_24h"), "url": v["url"]}
            for v, vw, er, r in new]}, ensure_ascii=False, indent=2))
        return 0

    if not new:
        print(json.dumps(stamp({"mode": "incremental", "new": 0, "pushed": 0}), ensure_ascii=False))
        return 0

    # 单次上限：防异常爆量。超量按播放高的优先，剩余下轮继续。
    truncated = len(new) > MAX_PUSH
    batch = sorted(new, key=lambda x: -x[1])[:MAX_PUSH]

    pushed, logs = [], []
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    for v, vw, er, r in batch:
        if push_card(cfg["webhook"], v, vw, er):
            pushed.append(v["tiktok_video_id"])
            logs.append({"pushed_at": now, "handle": handle_of(v), "views": vw,
                         "er": er, "reasons": r, "url": v["url"]})
    save_seen(seen | set(pushed))  # 只 commit 推成功的，失败的下轮重试
    append_pushlog(logs)

    out = stamp({"mode": "incremental", "new": len(new), "pushed": len(pushed)})
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
