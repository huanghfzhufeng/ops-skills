#!/usr/bin/env python3
"""watch.py - 监听 Social Growth Engineers 博客，diff 出新文章。

仅用标准库（urllib + re + json + html），无需 pip install。

命令：
    check   抓 sitemap，diff 出新博客，把每篇 meta + 正文输出 JSON 到 stdout。
            首次跑（无 state 文件）= baseline：把现有全部 URL 记为已见，不输出新博客
            （避免首跑把上千篇历史文章全推到群里）。
    commit  把 --urls-file 里的 URL（或 --url 多个）标记为已推送（加入 state）。
            推送成功后调用，实现「至少推一次」——推失败的不 commit，下轮自动重试。

state 文件：~/.config/ops-skills/sge-blog-watcher-seen.json（跨 plugin 升级保留）
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITEMAP_INDEX = "https://www.socialgrowthengineers.com/sitemap.xml"
UA = {"User-Agent": "Mozilla/5.0 (compatible; sge-blog-watcher/1.0)"}
STATE_DIR = Path.home() / ".config" / "ops-skills"
STATE_FILE = STATE_DIR / "sge-blog-watcher-seen.json"
PUSHLOG_FILE = STATE_DIR / "sge-blog-watcher-pushlog.jsonl"
BODY_MAX_CHARS = 6000

# 顶级单段 slug 里这些不是博客（app 收录、静态页、导航页）
EXCLUDE_EXACT = {
    "/apps", "/resources", "/reports", "/join", "/mysge", "/pro-view",
    "/case-studies", "/sign-in", "/about", "/contact", "/privacy", "/terms",
    "/search", "/all",
}


def fetch(url: str, timeout: int = 20) -> str:
    """GET 一个 URL，返回 utf-8 文本。抛 urllib.error 由调用方处理。"""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "ignore")


def normalize(url: str) -> str:
    """统一成 https://www.socialgrowthengineers.com/<slug>（去尾斜杠、补 www、统一 https）。"""
    m = re.search(r"https?://[^/]*socialgrowthengineers\.com(/[^?#]*)?", url)
    path = (m.group(1) if m and m.group(1) else "/")
    path = path.rstrip("/")
    return f"https://www.socialgrowthengineers.com{path}"


def is_blog_url(path: str) -> bool:
    """博客是顶级单段 slug（恰好一个 /），排除 app 二级路径和静态导航页。"""
    path = path.rstrip("/")
    if path.count("/") != 1:  # /apps/foo 有两个 /，自动排除
        return False
    if path in EXCLUDE_EXACT:
        return False
    return True


def get_all_blog_urls() -> tuple[list[str], dict]:
    """抓 sitemap index → 所有子 sitemap → 提取博客 URL（归一化、去重）。

    返回 (sorted_urls, stats)。某个子 sitemap 抓失败不致命，记入 stats。
    """
    index = fetch(SITEMAP_INDEX)
    sub_sitemaps = re.findall(r"<loc>([^<]+)</loc>", index)
    urls: set[str] = set()
    failed: list[str] = []
    for sm in sub_sitemaps:
        try:
            xml = fetch(sm)
        except (urllib.error.URLError, TimeoutError) as exc:
            failed.append(f"{sm}: {exc}")
            continue
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            path = re.sub(r"^https?://[^/]+", "", loc.split("?")[0])
            if is_blog_url(path):
                urls.add(normalize(loc))
    stats = {
        "sub_sitemaps": len(sub_sitemaps),
        "sub_sitemaps_failed": failed,
    }
    return sorted(urls), stats


def _meta_prop(text: str, prop: str) -> str | None:
    m = re.search(rf'<meta\s+property="{re.escape(prop)}"\s+content="([^"]*)"', text)
    return html.unescape(m.group(1)) if m else None


def _meta_name(text: str, name: str) -> str | None:
    m = re.search(rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"', text)
    return html.unescape(m.group(1)) if m else None


def _read_time(text: str) -> str | None:
    m = re.search(r"(<\s*1|\d+)\s*min read", text)
    return m.group(0) if m else None


def _extract_body(text: str) -> str:
    """从 <article> 抽正文纯文本。双重 unescape（SGE 描述有二次 HTML 转义）。"""
    m = re.search(r"<article[^>]*>(.*?)</article>", text, re.S | re.I)
    chunk = m.group(1) if m else text
    chunk = re.sub(r"<script[^>]*>.*?</script>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<style[^>]*>.*?</style>", " ", chunk, flags=re.S | re.I)
    plain = re.sub(r"<[^>]+>", " ", chunk)
    plain = html.unescape(html.unescape(plain))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:BODY_MAX_CHARS]


def fetch_post(url: str) -> dict:
    """抓单篇博客的 meta + 正文。"""
    text = fetch(url)
    desc = _meta_name(text, "description") or _meta_prop(text, "og:description")
    return {
        "url": url,
        "title": _meta_prop(text, "og:title"),
        "published": _meta_prop(text, "article:published_time"),
        "modified": _meta_prop(text, "article:modified_time"),
        "section": _meta_prop(text, "article:section"),
        "author": _meta_prop(text, "article:author"),
        "image": _meta_prop(text, "og:image"),
        "read_time_raw": _read_time(text),
        "description": desc,
        "body": _extract_body(text),
    }


def load_seen() -> set[str] | None:
    """读 state。不存在返回 None（首次 = baseline 信号）。损坏也返回 None。"""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    except (json.JSONDecodeError, OSError):
        return None


def save_seen(urls: set[str]) -> None:
    """原子写 state（先写 tmp 再 rename，避免半截文件）。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"seen": sorted(urls), "count": len(urls)}
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def append_pushlog(entries: list[dict]) -> None:
    """把推送记录 append 到 pushlog.jsonl（每行一个 JSON：时间/分类/标题/url）。"""
    if not entries:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    with PUSHLOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _log_committed(translated_path: str, committed: set[str]) -> int:
    """从 translated.json 取已推 URL 的标题等，写入推送日志。返回写入条数。"""
    try:
        data = json.loads(Path(translated_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    entries = [
        {
            "pushed_at": now,
            "published": post.get("published"),
            "section": post.get("section"),
            "title": post.get("title_cn") or post.get("title"),
            "url": normalize(post.get("url", "")),
        }
        for post in data.get("posts", [])
        if normalize(post.get("url", "")) in committed
    ]
    append_pushlog(entries)
    return len(entries)


def cmd_check(args: argparse.Namespace) -> int:
    try:
        current_list, sm_stats = get_all_blog_urls()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(json.dumps({"error": f"sitemap fetch failed: {exc}"}, ensure_ascii=False))
        return 1
    current = set(current_list)
    seen = load_seen()

    if seen is None:
        save_seen(current)
        print(json.dumps({
            "mode": "baseline",
            "total": len(current),
            "sitemap_stats": sm_stats,
            "new": [],
        }, ensure_ascii=False))
        return 0

    new_urls = sorted(current - seen)
    capped = new_urls[: args.max_new]
    posts: list[dict] = []
    for url in capped:
        try:
            posts.append(fetch_post(url))
        except (urllib.error.URLError, TimeoutError) as exc:
            posts.append({"url": url, "error": str(exc)})

    print(json.dumps({
        "mode": "incremental",
        "total": len(current),
        "new_count": len(new_urls),
        "fetched": len(posts),
        "truncated": len(new_urls) > len(capped),
        "sitemap_stats": sm_stats,
        "new": posts,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    seen = load_seen() or set()
    add: set[str] = set()
    if args.urls_file:
        raw = Path(args.urls_file).read_text(encoding="utf-8").splitlines()
        add = {normalize(line.strip()) for line in raw if line.strip()}
    if args.url:
        add |= {normalize(u) for u in args.url}
    new_seen = seen | add  # 不可变：构造新集合，不原地改
    save_seen(new_seen)

    logged = 0
    if args.log_from and add:
        logged = _log_committed(args.log_from, add)

    print(json.dumps({
        "committed": len(add),
        "total_seen": len(new_seen),
        "logged": logged,
    }, ensure_ascii=False))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    if not PUSHLOG_FILE.exists():
        print("（暂无推送记录）")
        return 0
    entries: list[dict] = []
    for line in PUSHLOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    tail = entries[-args.tail:] if args.tail > 0 else entries
    print(f"推送历史：累计 {len(entries)} 篇，显示最近 {len(tail)} 篇")
    for entry in tail:
        pushed = (entry.get("pushed_at") or "")[:16].replace("T", " ")
        published = (entry.get("published") or "")[:10]
        print(f"  {pushed}  [{published}] {entry.get('title', '?')}")
        print(f"      {entry.get('url', '')}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="监听 SGE 博客 diff 新文章")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="diff 出新博客并抓内容")
    p_check.add_argument("--max-new", type=int, default=20,
                         help="单次最多抓多少篇新博客（防 sitemap 异常爆量，默认 20）")
    p_check.set_defaults(func=cmd_check)

    p_commit = sub.add_parser("commit", help="把 URL 标记为已推送")
    p_commit.add_argument("--urls-file", help="每行一个 URL 的文件")
    p_commit.add_argument("--url", nargs="*", help="直接传 URL（可多个）")
    p_commit.add_argument("--log-from",
                          help="translated.json 路径；给了就从中取标题写推送日志")
    p_commit.set_defaults(func=cmd_commit)

    p_log = sub.add_parser("log", help="查看推送历史")
    p_log.add_argument("--tail", type=int, default=20,
                       help="显示最近 N 条（默认 20，传 0 = 全部）")
    p_log.set_defaults(func=cmd_log)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
