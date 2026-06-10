#!/usr/bin/env python3
"""watch.py - 监听 TikTok Analyzer，把破阈值的爆款视频推送到飞书群。

仅标准库（urllib + json + re + datetime + io），无需 pip install。

命令：
    run         登录 → 拉全量视频 → 筛(播放>阈值 或 (ER>阈值 且 播放>=最低播放))
                → diff seen → 逐条推飞书卡片 → commit。首次跑= baseline，只记不推。
    run --dry-run   只 diff 不推。
    log         查推送历史。

命中逻辑：播放 > view_threshold  或  ( ER > er_threshold% 且 播放 >= er_min_views )

爆款战报（里程碑）：已预警过的视频，播放再跨过 milestone_thresholds 档位（默认 1万/10万）
    时各再提醒一次（橙色卡），每档一次、跳档只报最高档。状态升级第一轮静默记档不补发历史。

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
MAX_MILESTONE_PUSH = 10  # 单次爆款战报上限；超出的不记档，下轮自动续推
FETCH_LIMIT = 50000  # 拉全量视频的 limit；设远大于总视频数，逼近时告警
FEISHU = "https://open.feishu.cn/open-apis"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def parse_milestones(raw: str | None) -> list[int]:
    """解析爆款战报档位（逗号分隔）。非法项忽略；空/全非法 → []（= 功能关闭）。"""
    out = set()
    for part in (raw or "").replace("，", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            out.add(int(part))
    return sorted(out)


def milestone_label(t: int) -> str:
    """档位 → 中文标签：10000 → 播放破1万，100000 → 播放破10万。"""
    return f"播放破{t // 10000}万" if t >= 10000 and t % 10000 == 0 else f"播放破{t}"


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
        "er_max_age_days": float(g("er_max_age_days", "7")),   # ER 命中要求发布 ≤ N 天（v1）
        "app_id": g("feishu_app_id"),        # 可选：封面图用
        "app_secret": g("feishu_app_secret"),
        "proxy": g("proxy"),                  # 可选：访问 TikTok 用
        # 爆款战报档位（已预警视频破档再提醒）；配空/非法 = 关闭
        "milestones": parse_milestones(g("milestone_thresholds", "10000,100000")),
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
    """命中逻辑（v1）：
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


def find_milestone_hits(videos: list[dict], seen: set[str],
                        milestones: dict[str, int], thresholds: list[int]) -> list[tuple]:
    """爆款战报命中：已预警过(in seen)的视频，播放跨过新档位 → (video, views, er, 档位)。
    跳档只报最高档（一轮之间从几千蹿到 15 万只发一张「破10万」，不连发两张）。"""
    out = []
    for v in videos:
        vid = v.get("tiktok_video_id")
        if vid not in seen:
            continue
        views = (v.get("latest_metrics") or {}).get("views") or 0
        lvl = max((t for t in thresholds if views > t), default=0)
        if lvl and lvl > milestones.get(vid, 0):
            out.append((v, views, v.get("engagement_rate") or 0, lvl))
    return out


def baseline_milestones(videos: list[dict], seen: set[str], thresholds: list[int]) -> dict[str, int]:
    """静默记档：seen 里的视频按当前播放记下已过的最高档位（不发卡）。
    状态升级后的第一轮用——否则会把历史上所有破万视频补发一遍刷爆群。"""
    ms: dict[str, int] = {}
    for v in videos:
        vid = v.get("tiktok_video_id")
        if vid not in seen:
            continue
        views = (v.get("latest_metrics") or {}).get("views") or 0
        lvl = max((t for t in thresholds if views > t), default=0)
        if lvl:
            ms[vid] = lvl
    return ms


def load_state() -> tuple[set[str] | None, dict[str, int] | None]:
    """读状态文件。返回 (seen, milestones)：
    - 文件不存在/损坏 → (None, None)，seen 走 baseline（只记不推）
    - 老格式（无 milestones 键）→ (seen, None)，里程碑走静默记档"""
    if not SEEN_FILE.exists():
        return None, None
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        seen = set(data["seen"])
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None, None
    try:
        ms = data.get("milestones")
        if not isinstance(ms, dict):
            return seen, None
        return seen, {str(k): int(v) for k, v in ms.items()}
    except (ValueError, TypeError):
        return seen, None


def save_state(ids: set[str], milestones: dict[str, int]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"seen": sorted(ids), "count": len(ids),
                               "milestones": milestones}, ensure_ascii=False),
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


def push_card(cfg: dict, v: dict, views: int, er: float, app_token: str | None,
              title: str | None = None, template: str = "red") -> bool:
    """有封面 → 左图右文小卡片；拿不到封面 → 降级纯文字卡。整卡点击跳转视频。
    title/template 可换标题与配色：首次预警红卡（默认），爆款战报橙卡。"""
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
        "header": {"title": {"tag": "plain_text",
                             "content": title or f"爆款预警 · @{handle_of(v)}"}, "template": template},
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
    seen, milestones = load_state()
    current_ids = {v["tiktok_video_id"] for v, *_ in hit_list}
    ths = cfg["milestones"]

    def stamp(out: dict) -> dict:
        if truncated_fetch:
            out["warn"] = f"视频数触达上限 {FETCH_LIMIT}，可能被截断，请调大 FETCH_LIMIT"
        return out

    if seen is None:
        # 首次跑：seen 与里程碑档位一起静默建 baseline，不推
        save_state(current_ids, baseline_milestones(videos, current_ids, ths))
        print(json.dumps(stamp({"mode": "baseline", "total_hits": len(hit_list), "pushed": 0}),
                         ensure_ascii=False))
        return 0

    new = [(v, vw, er, r) for v, vw, er, r in hit_list if v["tiktok_video_id"] not in seen]

    # 爆款战报：老状态文件没有 milestones → 本轮静默记档（防把历史破万视频补发刷屏），下轮起增量
    ms_baseline = milestones is None
    if ms_baseline:
        milestones = baseline_milestones(videos, seen, ths)
        m_hits: list[tuple] = []
    else:
        m_hits = find_milestone_hits(videos, seen, milestones, ths)

    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "new": len(new), "videos": [
            {"handle": handle_of(v), "reasons": r, "views": vw, "er": er, "url": v["url"]}
            for v, vw, er, r in new],
            "milestone_mode": "baseline" if ms_baseline else "incremental",
            "milestone_new": [
                {"handle": handle_of(v), "level": milestone_label(lv), "views": vw, "url": v["url"]}
                for v, vw, _er, lv in m_hits]}, ensure_ascii=False, indent=2))
        return 0

    if not new and not m_hits and not ms_baseline:
        print(json.dumps(stamp({"mode": "incremental", "new": 0, "pushed": 0}), ensure_ascii=False))
        return 0

    app_token = get_tenant_token(cfg) if (new or m_hits) else None  # 封面用；None 则降级纯文字卡
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    pushed, logs = [], []

    # —— 首次预警（红卡）——
    truncated = len(new) > MAX_PUSH
    batch = sorted(new, key=lambda x: -x[1])[:MAX_PUSH]
    for v, vw, er, r in batch:
        if push_card(cfg, v, vw, er, app_token):
            pushed.append(v["tiktok_video_id"])
            logs.append({"pushed_at": now, "handle": handle_of(v), "views": vw,
                         "er": er, "reasons": r, "url": v["url"]})
            # 首推时按当前播放静默记档：首推卡已显示真实播放，再补一张「破1万」是噪音
            lvl = max((t for t in ths if vw > t), default=0)
            if lvl:
                milestones[v["tiktok_video_id"]] = lvl

    # —— 爆款战报（橙卡，已预警视频跨档再提醒；每档一次，失败不记档下轮重试）——
    m_truncated = len(m_hits) > MAX_MILESTONE_PUSH
    m_batch = sorted(m_hits, key=lambda x: -x[1])[:MAX_MILESTONE_PUSH]
    m_pushed = 0
    for v, vw, er, lv in m_batch:
        label = milestone_label(lv)
        if push_card(cfg, v, vw, er, app_token,
                     title=f"爆款战报 · @{handle_of(v)} · {label}", template="orange"):
            milestones[v["tiktok_video_id"]] = lv
            m_pushed += 1
            logs.append({"pushed_at": now, "kind": "milestone", "handle": handle_of(v),
                         "views": vw, "er": er, "reasons": [label], "url": v["url"]})

    save_state(seen | set(pushed), milestones)
    append_pushlog(logs)

    out = stamp({"mode": "incremental", "new": len(new), "pushed": len(pushed),
                 "cover": "on" if app_token else "off"})
    if ms_baseline:
        out["milestone_mode"] = "baseline"
        out["milestone_recorded"] = len(milestones)
    else:
        out["milestone_new"] = len(m_hits)
        out["milestone_pushed"] = m_pushed
    if truncated:
        out["note"] = f"本轮 {len(new)} 条超上限，按播放推了前 {MAX_PUSH} 条，剩余下轮继续"
    if m_truncated:
        out["milestone_note"] = (f"爆款战报 {len(m_hits)} 条超上限，推了前 {MAX_MILESTONE_PUSH} 条，"
                                 f"剩余下轮继续")
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
