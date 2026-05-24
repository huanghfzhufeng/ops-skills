#!/usr/bin/env python3
"""
TK Template Scout - 抓 TikTok 视频元数据

输入：tk_keywords.yaml（26 个 persona × 3 个关键词）
输出：JSON {persona_key: [top3 video records]} 到 stdout

技术路径：
  1. 对每个关键词跑 WebSearch (site:tiktok.com) 拿一批 video URL
     但 WebSearch 是 Claude 的工具，本脚本跑不了 — 由 SKILL.md orchestrator 负责
     脚本接受预先收集的 URL list（--urls-file 或 stdin）
  2. yt-dlp + --cookies-from-browser chrome 抓每条 URL 的完整元数据
  3. 按 timestamp 过滤 24h（不足 3 条放宽到 7 天）
  4. 按 like_count 排序取 Top 3

用法：
  # 模式 A：从 stdin 读 URL（每行一个，前缀 persona_key:URL）
  echo -e 'sophie:https://www.tiktok.com/@xxx/video/123\\nsophie:https://www.tiktok.com/@yyy/video/456' \\
    | python3 scout.py --max-age-hours 24

  # 模式 B：URL 文件
  python3 scout.py --urls-file urls.txt --max-age-hours 24

URL 文件格式（每行）：
  <persona_key>:<tiktok_video_url>
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict


def fetch_metadata(url: str, browser: str = "chrome", timeout: int = 30) -> dict | None:
    """跑 yt-dlp 抓单个 TikTok 视频的元数据。失败返回 None。"""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--cookies-from-browser", browser,
                "--dump-json",
                "--skip-download",
                "--no-warnings",
                "--socket-timeout", "15",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return {
            "id": data.get("id"),
            "title": (data.get("title") or "").strip(),
            "uploader": data.get("uploader"),
            "channel": data.get("channel"),
            "timestamp": data.get("timestamp"),
            "upload_date": data.get("upload_date"),
            "duration": data.get("duration"),
            "view_count": data.get("view_count") or 0,
            "like_count": data.get("like_count") or 0,
            "comment_count": data.get("comment_count") or 0,
            "repost_count": data.get("repost_count") or 0,
            "webpage_url": data.get("webpage_url") or url,
            "thumbnail": data.get("thumbnail"),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


def parse_input(lines: list[str]) -> dict[str, list[str]]:
    """解析 'persona_key:url' 格式，返回 {persona: [urls]}。"""
    result = defaultdict(list)
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        persona, url = line.split(":", 1)
        persona = persona.strip().lower()
        url = url.strip()
        if url.startswith("http"):
            result[persona].append(url)
    return dict(result)


def pick_top_n(records: list[dict], cutoff_ts: float, top_n: int = 3) -> tuple[list[dict], str]:
    """
    过滤时间 + 取 Top N。
    返回 (records, age_tag) 其中 age_tag 是 "24h" / "7d" / "all" 用于标注降级。
    """
    fresh = [r for r in records if r.get("timestamp") and r["timestamp"] >= cutoff_ts]
    if len(fresh) >= top_n:
        return sorted(fresh, key=lambda r: r["like_count"], reverse=True)[:top_n], "fresh"
    # 降级到 7 天
    week_cutoff = cutoff_ts - 6 * 86400
    week = [r for r in records if r.get("timestamp") and r["timestamp"] >= week_cutoff]
    if len(week) >= top_n:
        return sorted(week, key=lambda r: r["like_count"], reverse=True)[:top_n], "7d"
    # 全量
    return sorted(records, key=lambda r: r["like_count"], reverse=True)[:top_n], "all"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls-file", help="URL 文件路径，每行 persona_key:url")
    parser.add_argument("--max-age-hours", type=int, default=24, help="主时间窗（小时）")
    parser.add_argument("--top-n", type=int, default=3, help="每人取多少条")
    parser.add_argument("--parallel", type=int, default=6, help="并发抓取数")
    parser.add_argument("--browser", default="chrome", help="cookies 来自哪个浏览器")
    args = parser.parse_args()

    if args.urls_file:
        with open(args.urls_file, encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    persona_urls = parse_input(lines)
    if not persona_urls:
        print(json.dumps({"error": "no valid urls in input"}), file=sys.stdout)
        sys.exit(1)

    cutoff = time.time() - args.max_age_hours * 3600

    all_records: dict[str, list[dict]] = {}
    failures: dict[str, int] = defaultdict(int)

    flat_jobs = [(p, u) for p, urls in persona_urls.items() for u in urls]
    persona_buckets: dict[str, list[dict]] = defaultdict(list)

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        future_map = {pool.submit(fetch_metadata, url, args.browser): (p, url) for p, url in flat_jobs}
        for fut in as_completed(future_map):
            persona, url = future_map[fut]
            rec = fut.result()
            if rec is None:
                failures[persona] += 1
                continue
            persona_buckets[persona].append(rec)

    report = {}
    for persona in persona_urls:
        records = persona_buckets.get(persona, [])
        top, age_tag = pick_top_n(records, cutoff, args.top_n)
        report[persona] = {
            "videos": top,
            "fetched": len(records),
            "failed": failures[persona],
            "age_tag": age_tag,
        }

    out = {
        "generated_at": int(time.time()),
        "max_age_hours": args.max_age_hours,
        "top_n": args.top_n,
        "personas": report,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
