#!/usr/bin/env python3
"""
grab_viral_challenges.py - 自动化全平台挑战样本抓取 + 时间窗验证

工作流（v4.6.0 防回声室关键）：

  Claude 主线 WebSearch 找候选挑战 hashtag
       ↓ 产出候选列表（5-8 个 hashtag）
  本脚本接 stdin / --hashtags 参数
       ↓
  对每个 hashtag：
    1. Playwright 抓 /tag/<hashtag> 页拿 video URL
    2. yt-dlp 抓每个 URL 的点赞 / 时长 / timestamp
    3. 硬过滤：timestamp >= now - max_age_days
    4. 按点赞排序，取 Top 1 作样本
       ↓
  输出验证后的 challenges JSON（含真实样本 + 时间戳证据）

用法：
  # 1. 用 stdin（推荐，Claude 直接管道传入候选）
  echo '[
    {"name": "CORTIS Wiggle-Ears", "hashtag": "cortischallenge", "desc": "..."},
    {"name": "Pet POV Chef", "hashtag": "petpov", "desc": "..."}
  ]' | python3 grab_viral_challenges.py --max-age-days 7

  # 2. 用文件
  python3 grab_viral_challenges.py --candidates candidates.json --max-age-days 7

输出（JSON to stdout）：
  {
    "verified": [
      {
        "name": "CORTIS Wiggle-Ears",
        "hashtag": "cortischallenge",
        "desc": "...",
        "sample_url": "https://...",
        "sample_likes": 1800000,
        "sample_duration": 28,
        "sample_age_hours": 153.6,
        "verified": true
      }
    ],
    "rejected": [
      {"name": "Group 7", "reason": "all samples > 7 days old (oldest 219 days)"}
    ]
  }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import scout_strict

try:
    from patchright.async_api import Browser, BrowserContext, async_playwright
    _USING_PATCHRIGHT = True
except ImportError:
    from playwright.async_api import Browser, BrowserContext, async_playwright
    _USING_PATCHRIGHT = False


log = logging.getLogger("grab_viral_challenges")

DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_TOP_URLS_PER_HASHTAG = 8
DEFAULT_PARALLEL = 4
PAGE_TIMEOUT_MS = 30_000
SELECTOR_TIMEOUT_MS = 10_000


# ---------- Playwright: 抓 hashtag 页 ----------


async def fetch_hashtag_urls(
    context: BrowserContext, hashtag: str, top_n: int
) -> list[str]:
    """从 /tag/<hashtag> 页拿 video URL 列表（不限时长）。"""
    page = await context.new_page()
    url = f"https://www.tiktok.com/tag/{hashtag}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        try:
            await page.wait_for_selector('a[href*="/video/"]', timeout=SELECTOR_TIMEOUT_MS)
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        urls: list[str] = await page.evaluate(
            """
            () => Array.from(new Set(
                Array.from(document.querySelectorAll('a[href*="/video/"]'))
                    .map(a => a.href)
            ))
            """
        )
        return urls[:top_n]
    finally:
        await page.close()


async def grab_hashtag_urls_all(
    candidates: list[dict[str, str]],
    cookies: list[dict[str, Any]],
    parallel: int,
    top_n: int,
) -> dict[str, list[str]]:
    """并行抓所有候选 hashtag 的 URL list。返回 {hashtag: [urls]}."""
    async with async_playwright() as p:
        launch_kwargs: dict = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        }
        if _USING_PATCHRIGHT:
            launch_kwargs["channel"] = "chromium"
        browser = await p.chromium.launch(**launch_kwargs)
        try:
            # 复用 scout_strict.make_context（带 stealth + cookies）
            context = await scout_strict.make_context(browser, cookies)
            try:
                results: dict[str, list[str]] = {}
                sem = asyncio.Semaphore(parallel)

                async def fetch_one(c: dict[str, str]) -> None:
                    hashtag = c["hashtag"]
                    async with sem:
                        try:
                            urls = await fetch_hashtag_urls(context, hashtag, top_n)
                            results[hashtag] = urls
                            log.info("  #%-25s %d URLs", hashtag, len(urls))
                        except Exception as e:
                            log.warning("  #%-25s ERROR: %s", hashtag, str(e)[:80])
                            results[hashtag] = []

                await asyncio.gather(*[fetch_one(c) for c in candidates])
                return results
            finally:
                await context.close()
        finally:
            await browser.close()


# ---------- yt-dlp 抓样本元数据 ----------


def fetch_video_metadata(url: str, browser: str = "chrome", timeout: int = 25) -> dict | None:
    """yt-dlp 抓 video 元数据：点赞 / 时长 / timestamp。"""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--cookies-from-browser", browser,
                "--dump-json",
                "--skip-download",
                "--no-warnings",
                "--socket-timeout", "12",
                url,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None
        d = json.loads(result.stdout)
        return {
            "url": d.get("webpage_url") or url,
            "title": (d.get("title") or "").strip()[:200],
            "uploader": d.get("uploader") or "",
            "like_count": int(d.get("like_count") or 0),
            "duration": int(d.get("duration") or 0),
            "timestamp": int(d.get("timestamp") or 0),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    except Exception:  # noqa: BLE001
        return None


def pick_top_sample_within_window(
    urls: list[str], max_age_days: int, yt_dlp_parallel: int,
) -> tuple[dict | None, str | None]:
    """
    对一批 URL 跑 yt-dlp，过滤 ≤max_age_days，按点赞排序取 Top 1。
    返回 (top_sample_dict 或 None, reject_reason 或 None)。
    """
    if not urls:
        return None, "no URLs from hashtag page"

    cutoff_ts = time.time() - max_age_days * 86400
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=yt_dlp_parallel) as pool:
        future_map = {pool.submit(fetch_video_metadata, u): u for u in urls}
        for fut in as_completed(future_map):
            rec = fut.result()
            if rec:
                records.append(rec)

    if not records:
        return None, "yt-dlp failed for all URLs"

    # 时间窗过滤
    fresh = [r for r in records if r["timestamp"] >= cutoff_ts]
    if not fresh:
        # 所有都过期：找最近的标 reject_reason
        oldest_days = round(
            min((time.time() - r["timestamp"]) / 86400 for r in records), 1
        )
        return None, f"all samples > {max_age_days} days old (closest {oldest_days} days)"

    # 按 like_count 取 Top 1
    fresh.sort(key=lambda r: -r["like_count"])
    return fresh[0], None


# ---------- 主流程 ----------


def verify_candidates(
    candidates: list[dict[str, Any]],
    cookies_path: Path,
    max_age_days: int,
    parallel: int,
    top_urls_per_hashtag: int,
    yt_dlp_parallel: int,
) -> dict[str, list[dict]]:
    """
    主流程：抓 hashtag → yt-dlp 验证 → 按时间窗筛 Top 1 样本。
    返回 {"verified": [...], "rejected": [...]}.
    """
    cookies = scout_strict.load_netscape_cookies(cookies_path)
    if not scout_strict.check_cookies_have_session(cookies):
        log.error("Cookies missing tiktok.com sessionid; run setup.sh to refresh.")
        sys.exit(2)

    log.info("Phase 1: Playwright 抓 %d hashtag 页（parallel=%d）", len(candidates), parallel)
    hashtag_urls = asyncio.run(
        grab_hashtag_urls_all(candidates, cookies, parallel, top_urls_per_hashtag)
    )

    log.info("Phase 2: yt-dlp 验证样本（max_age=%d 天）", max_age_days)
    verified: list[dict] = []
    rejected: list[dict] = []
    for cand in candidates:
        hashtag = cand["hashtag"]
        urls = hashtag_urls.get(hashtag, [])
        top, reject_reason = pick_top_sample_within_window(
            urls, max_age_days, yt_dlp_parallel
        )
        if top:
            age_hours = round((time.time() - top["timestamp"]) / 3600, 1)
            verified.append({
                **cand,
                "sample_url": top["url"],
                "sample_likes": top["like_count"],
                "sample_duration": top["duration"],
                "sample_uploader": top["uploader"],
                "sample_age_hours": age_hours,
                "sample_title": top["title"],
                "verified": True,
            })
            log.info("  ✓ %-30s %dlikes %ds, %.1fh ago", cand["name"], top["like_count"], top["duration"], age_hours)
        else:
            rejected.append({**cand, "reason": reject_reason})
            log.info("  ✗ %-30s %s", cand["name"], reject_reason)

    return {"verified": verified, "rejected": rejected}


def load_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    """读候选 hashtag list。优先 --candidates 文件，否则 stdin。"""
    if args.candidates:
        with args.candidates.open(encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    # 兼容两种格式：[{...}] 或 {"candidates": [...]}
    if isinstance(data, dict):
        data = data.get("candidates", [])
    # 验证 schema
    for c in data:
        if "hashtag" not in c or "name" not in c:
            raise ValueError(f"candidate 必须含 name 和 hashtag 字段，缺：{c}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="自动化全平台挑战样本抓取 + 时间窗验证")
    parser.add_argument("--candidates", type=Path,
                        help="候选 JSON 文件路径（默认从 stdin 读）")
    parser.add_argument("--cookies", type=Path, default=None,
                        help="cookies 文件路径。未指定时优先 ~/.config/ops-skills/tiktok-cookies.txt"
                             "（持久，跨天不被 /tmp 清），不存在则 fallback /tmp/tiktok-cookies.txt")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help="样本视频最大年龄（天）。超过即丢弃。默认 7。")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL,
                        help="Playwright 并发数")
    parser.add_argument("--top-urls-per-hashtag", type=int, default=DEFAULT_TOP_URLS_PER_HASHTAG,
                        help="每个 hashtag 页抓多少 URL 进 yt-dlp")
    parser.add_argument("--yt-dlp-parallel", type=int, default=6)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # cookies 路径解析（v5.4）：未显式指定时优先持久目录，避免 /tmp 跨天被清（与 scout_strict 一致）
    if args.cookies is None:
        persistent = Path.home() / ".config" / "ops-skills" / "tiktok-cookies.txt"
        args.cookies = persistent if persistent.exists() else Path("/tmp/tiktok-cookies.txt")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    if not args.cookies.exists():
        log.error("Cookies not found at %s. Run setup.sh first.", args.cookies)
        sys.exit(2)

    candidates = load_candidates(args)
    log.info("Loaded %d candidates", len(candidates))

    result = verify_candidates(
        candidates,
        cookies_path=args.cookies,
        max_age_days=args.max_age_days,
        parallel=args.parallel,
        top_urls_per_hashtag=args.top_urls_per_hashtag,
        yt_dlp_parallel=args.yt_dlp_parallel,
    )

    log.info(
        "Done: %d verified / %d rejected",
        len(result["verified"]), len(result["rejected"]),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
