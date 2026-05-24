#!/usr/bin/env python3
"""
TK Template Scout - 严格 24h 模式（Playwright + 双源融合 + ID 解码）

数据源（默认 both，可用 --source 切单源）：
  1. search:  https://www.tiktok.com/search/video?q=<keyword>&publish_time=1&sort_type=2
     TikTok 搜索页 Videos tab + Latest 排序。覆盖"算法判断相关"的视频。
  2. hashtag: https://www.tiktok.com/tag/<hashtag>
     TikTok hashtag 聚合页，按时间倒序。覆盖"主动打 hashtag"的视频。

实测两源重叠仅 21%，是互补关系不是替代关系。双源融合后单 persona 24h 命中
比 hashtag 单源还高 13%，比 search 单源高 130%。

流程：
1. 26 人 × 3 keyword = 78 个 job。每 job 抓 2 个 URL（search + hashtag）
2. 用 video_id >> 32 解码 timestamp 做 24h 硬过滤
3. Persona 内 dedup：同 video_id 在两源都出现 → 标 source=both
4. Cross-persona dedup：同 video_id 在多 persona 出现 → 归给候选最少的
5. yt-dlp 抓 like_count / title / uploader
6. 按 like_count 取 Top N

前置：
  - Chrome 已**真实登录** tiktok.com（cookies 必须含 sessionid）
  - playwright + chromium 已装
  - playwright-stealth 已装（可选但推荐）
  - yt-dlp 已装
  - cookies 文件先手动导出：
    yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt \\
      --skip-download --quiet 'https://www.tiktok.com/@tiktok'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Browser, BrowserContext, async_playwright

try:
    from playwright_stealth import Stealth
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


log = logging.getLogger("scout_strict")


# ---------- 数据结构 ----------


@dataclass(frozen=True)
class VideoCandidate:
    """从 hashtag/search 页解析出来的候选。"""

    persona: str
    keyword: str          # 原始关键词（含空格），用于 search query
    source: str           # 'search' | 'hashtag' | 'both'（dedup 后撞两源会变 both）
    url: str
    video_id: str
    timestamp: int        # unix seconds（ID 解码值）
    age_hours: float


@dataclass(frozen=True)
class VideoRecord:
    """yt-dlp 补全后的完整记录。"""

    url: str
    title: str
    uploader: str
    like_count: int
    view_count: int
    comment_count: int
    timestamp: int        # yt-dlp 拿到的真实值
    source: str           # 候选阶段确定的 source（'search' / 'hashtag' / 'both'）
    duration: int = 0     # v4.6.0：视频时长（秒），用于 ≤15s 硬过滤；0 = 未知


# ---------- 配置常量 ----------

DEFAULT_PARALLEL = 4  # Playwright worker 数（每个复用 1 context）
DEFAULT_SCROLLS = 3
DEFAULT_RETRY = 2
DEFAULT_YT_DLP_PARALLEL = 6
DEFAULT_ID_VERIFY_SAMPLE = 5
DEFAULT_MIN_LIKES_WARN = 500
PAGE_TIMEOUT_MS = 40_000
SELECTOR_TIMEOUT_MS = 15_000
SCROLL_PAUSE_MS = 1_500
ID_VERIFY_DIFF_THRESHOLD_HOURS = 1.0

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

VALID_SOURCES = {"search", "hashtag", "both"}


# ---------- Cookie 加载（Netscape → Playwright 格式） ----------


def load_netscape_cookies(path: Path) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, path_, secure, expiry, name, value = parts[:7]
            try:
                exp_i = int(expiry)
                if exp_i <= 0 or exp_i > 2_000_000_000:
                    exp_i = -1
            except ValueError:
                exp_i = -1
            cookies.append({
                "name": name, "value": value, "domain": domain, "path": path_,
                "secure": secure == "TRUE", "expires": exp_i,
                "httpOnly": False, "sameSite": "Lax",
            })
    return cookies


def check_cookies_have_session(cookies: list[dict[str, Any]]) -> bool:
    """检查 cookies 是否含真实登录 session（不只是 anonymous browsing cookies）。"""
    tiktok_cookie_names = {c["name"] for c in cookies if "tiktok.com" in c["domain"]}
    return "sessionid" in tiktok_cookie_names


# ---------- 关键词 → URL ----------


def keyword_to_hashtag(keyword: str) -> str:
    """'old money outfit' → 'oldmoneyoutfit'."""
    return re.sub(r"[^a-z0-9]", "", keyword.lower())


def build_urls(keyword: str, hashtag: str, source_mode: str) -> list[tuple[str, str]]:
    """
    根据 source_mode 返回 [(source_name, url), ...]。
    - source_mode='search'  → 只有 search URL
    - source_mode='hashtag' → 只有 hashtag URL
    - source_mode='both'    → 两个都
    """
    if source_mode not in VALID_SOURCES:
        raise ValueError(f"source_mode must be one of {VALID_SOURCES}")

    urls: list[tuple[str, str]] = []
    if source_mode in ("search", "both"):
        kw_enc = keyword.replace(" ", "%20")
        search_url = f"https://www.tiktok.com/search/video?q={kw_enc}&publish_time=1&sort_type=2"
        urls.append(("search", search_url))
    if source_mode in ("hashtag", "both"):
        urls.append(("hashtag", f"https://www.tiktok.com/tag/{hashtag}"))
    return urls


# ---------- Playwright 抓页面 ----------


async def make_context(browser: Browser, cookies: list[dict[str, Any]]) -> BrowserContext:
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        """
    )
    await context.add_cookies(cookies)
    return context


async def scrape_one_url(
    context: BrowserContext,
    persona: str,
    keyword: str,
    source: str,
    url: str,
    scrolls: int,
    cutoff_ts: float,
    now_ts: float,
) -> tuple[list[VideoCandidate], int]:
    """
    抓单个 URL（search 或 hashtag）。
    返回 (24h 内候选列表, 该页原始抓到的 URL 数)。
    """
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        try:
            await page.wait_for_selector('a[href*="/video/"]', timeout=SELECTOR_TIMEOUT_MS)
        except Exception:
            pass

        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await page.wait_for_timeout(SCROLL_PAUSE_MS)

        urls: list[str] = await page.evaluate(
            """
            () => {
                const set = new Set();
                document.querySelectorAll('a[href*="/video/"]').forEach(a => set.add(a.href));
                return Array.from(set);
            }
            """
        )
    finally:
        await page.close()

    candidates: list[VideoCandidate] = []
    seen_ids: set[str] = set()
    for u in urls:
        m = re.search(r"/video/(\d+)", u)
        if not m:
            continue
        vid_str = m.group(1)
        if vid_str in seen_ids:
            continue
        seen_ids.add(vid_str)
        vid = int(vid_str)
        ts = vid >> 32
        if ts < cutoff_ts:
            continue
        candidates.append(VideoCandidate(
            persona=persona, keyword=keyword, source=source, url=u,
            video_id=vid_str, timestamp=ts,
            age_hours=round((now_ts - ts) / 3600, 1),
        ))
    return candidates, len(urls)


async def scrape_one_with_retry(
    context: BrowserContext,
    persona: str,
    keyword: str,
    source: str,
    url: str,
    scrolls: int,
    cutoff_ts: float,
    now_ts: float,
    retry: int,
) -> tuple[list[VideoCandidate], int, str | None]:
    """retry 包装。返回 (candidates, raw_url_count, error_msg)。"""
    last_err: str | None = None
    for attempt in range(retry + 1):
        try:
            t0 = time.time()
            cands, raw = await scrape_one_url(
                context, persona, keyword, source, url, scrolls, cutoff_ts, now_ts,
            )
            elapsed = time.time() - t0
            log.info(
                "  %-9s %-10s %-22s %2d fresh / %3d raw in %4.1fs%s",
                source, persona, keyword[:22], len(cands), raw, elapsed,
                f" (attempt {attempt + 1})" if attempt > 0 else "",
            )
            return cands, raw, None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < retry:
                log.warning("  %-9s %-10s %s attempt %d failed, retrying: %s",
                            source, persona, keyword[:22], attempt + 1, last_err)
                await asyncio.sleep(2)
    log.error("  %-9s %-10s %s ALL %d attempts failed: %s",
              source, persona, keyword[:22], retry + 1, last_err)
    return [], 0, last_err


async def worker_loop(
    browser: Browser,
    cookies: list[dict[str, Any]],
    jobs: asyncio.Queue,
    results: list[VideoCandidate],
    raw_counts: dict[str, int],  # {source: total raw URL count}
    errors: list[tuple[str, str, str, str]],
    scrolls: int,
    cutoff_ts: float,
    now_ts: float,
    retry: int,
) -> None:
    """一个 worker 复用 1 个 context 处理多个 (persona, keyword, source, url) job。"""
    context = await make_context(browser, cookies)
    if _STEALTH_AVAILABLE:
        await Stealth().apply_stealth_async(context)
    try:
        while True:
            try:
                persona, keyword, source, url = jobs.get_nowait()
            except asyncio.QueueEmpty:
                return
            cands, raw, err = await scrape_one_with_retry(
                context, persona, keyword, source, url, scrolls, cutoff_ts, now_ts, retry,
            )
            results.extend(cands)
            raw_counts[source] = raw_counts.get(source, 0) + raw
            if err:
                errors.append((persona, keyword, source, err))
            jobs.task_done()
    finally:
        await context.close()


async def scrape_all(
    keyword_jobs: list[tuple[str, str]],  # [(persona, keyword), ...]
    cookies: list[dict[str, Any]],
    source_mode: str,
    parallel: int,
    scrolls: int,
    retry: int,
    max_age_hours: int,
) -> tuple[dict[str, list[VideoCandidate]], list[tuple[str, str, str, str]], dict[str, int]]:
    """
    抓所有 (persona, keyword) job 的 search 和/或 hashtag 页。
    返回 (by_persona_dedup, errors, raw_counts_by_source)。
    """
    log.info("Cookies loaded: %d entries", len(cookies))
    log.info("Source mode: %s", source_mode)

    now_ts = time.time()
    cutoff_ts = now_ts - max_age_hours * 3600

    # 展开 jobs: 每个 (persona, keyword) → 1 or 2 个 (persona, keyword, source, url)
    jobs_q: asyncio.Queue = asyncio.Queue()
    job_count = 0
    for persona, keyword in keyword_jobs:
        hashtag = keyword_to_hashtag(keyword)
        for source, url in build_urls(keyword, hashtag, source_mode):
            jobs_q.put_nowait((persona, keyword, source, url))
            job_count += 1
    log.info("Total URL fetch jobs: %d (=%d keywords × %s)",
             job_count, len(keyword_jobs), source_mode)

    results: list[VideoCandidate] = []
    raw_counts: dict[str, int] = {}
    errors: list[tuple[str, str, str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            workers = [
                asyncio.create_task(
                    worker_loop(browser, cookies, jobs_q, results, raw_counts, errors,
                                scrolls, cutoff_ts, now_ts, retry)
                )
                for _ in range(parallel)
            ]
            await asyncio.gather(*workers)
        finally:
            await browser.close()

    # persona 内 dedup：同 video_id 出现在 search + hashtag 两源 → 合并 source='both'
    by_persona: dict[str, list[VideoCandidate]] = defaultdict(list)
    for c in results:
        by_persona[c.persona].append(c)

    final: dict[str, list[VideoCandidate]] = {}
    for persona, cands in by_persona.items():
        # 同 video_id 合并：sources 取 union
        by_vid: dict[str, VideoCandidate] = {}
        for c in cands:
            if c.video_id in by_vid:
                existing = by_vid[c.video_id]
                if existing.source != c.source:
                    # 不同 source 撞到同一 video → 标 'both'
                    by_vid[c.video_id] = replace(existing, source="both")
            else:
                by_vid[c.video_id] = c
        # 按时间倒序
        final[persona] = sorted(by_vid.values(), key=lambda x: -x.timestamp)
    return final, errors, raw_counts


# ---------- Cross-persona dedup ----------


def cross_persona_dedup(
    by_persona: dict[str, list[VideoCandidate]],
) -> tuple[dict[str, list[VideoCandidate]], int]:
    """同视频被多 persona 抓到 → 归给候选数最少的（冷门优先）。"""
    vid_to_personas: dict[str, list[str]] = defaultdict(list)
    for persona, cands in by_persona.items():
        for c in cands:
            vid_to_personas[c.video_id].append(persona)

    persona_count = {p: len(cands) for p, cands in by_persona.items()}

    vid_owner: dict[str, str] = {}
    conflicts = 0
    for vid, personas in vid_to_personas.items():
        if len(personas) > 1:
            conflicts += 1
            owner = min(personas, key=lambda p: (persona_count[p], p))
            vid_owner[vid] = owner

    deduped: dict[str, list[VideoCandidate]] = {}
    for persona, cands in by_persona.items():
        deduped[persona] = [
            c for c in cands
            if c.video_id not in vid_owner or vid_owner[c.video_id] == persona
        ]
    return deduped, conflicts


# ---------- ID 解码二次验证 ----------


def verify_id_decoding_sample(
    by_persona: dict[str, list[VideoCandidate]],
    sample_size: int,
    diff_threshold_hours: float,
) -> tuple[int, int]:
    """抽 sample 走 yt-dlp 对比 ID 解码与真 timestamp。"""
    all_cands: list[VideoCandidate] = [c for cands in by_persona.values() for c in cands]
    if not all_cands:
        return 0, 0

    n = min(sample_size, len(all_cands))
    sample = random.sample(all_cands, n)
    log.info("Verifying ID decoding on %d random samples (threshold=%.1fh)...",
             n, diff_threshold_hours)

    verified = 0
    mismatch = 0
    for c in sample:
        rec = fetch_metadata(c.url, c.source)
        if rec is None or rec.timestamp == 0:
            continue
        verified += 1
        diff_h = abs(c.timestamp - rec.timestamp) / 3600
        if diff_h > diff_threshold_hours:
            mismatch += 1
            log.warning(
                "ID decode mismatch: video %s, decoded ts=%d real ts=%d diff=%.2fh",
                c.video_id, c.timestamp, rec.timestamp, diff_h,
            )

    if verified > 0 and mismatch > verified / 2:
        log.error(
            "⚠️ %d/%d samples mismatch > %.1fh! TikTok ID format may have changed. "
            "DO NOT TRUST 24h filtering until investigated.",
            mismatch, verified, diff_threshold_hours,
        )
    elif verified == 0:
        log.warning("ID decoding could not be verified (all samples failed yt-dlp fetch)")
    else:
        log.info("ID decoding OK: %d/%d samples within %.1fh",
                 verified - mismatch, verified, diff_threshold_hours)
    return verified, mismatch


# ---------- yt-dlp 抓元数据 ----------


def fetch_metadata(url: str, source: str = "hashtag", browser: str = "chrome",
                   timeout: int = 30) -> VideoRecord | None:
    """yt-dlp 抓单个 video 的 like_count / title / uploader。"""
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
        return VideoRecord(
            url=data.get("webpage_url") or url,
            title=(data.get("title") or "").strip()[:200],
            uploader=data.get("uploader") or "",
            like_count=int(data.get("like_count") or 0),
            view_count=int(data.get("view_count") or 0),
            comment_count=int(data.get("comment_count") or 0),
            timestamp=int(data.get("timestamp") or 0),
            source=source,
            duration=int(data.get("duration") or 0),
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    except Exception:  # noqa: BLE001 yt-dlp 偶发异常太杂
        return None


def fetch_metadata_for_all(
    candidates_by_persona: dict[str, list[VideoCandidate]],
    parallel: int,
) -> tuple[dict[str, list[VideoRecord]], int, int]:
    """并行跑 yt-dlp。"""
    flat: list[tuple[str, str, str]] = [
        (persona, c.url, c.source)
        for persona, cands in candidates_by_persona.items()
        for c in cands
    ]
    log.info("yt-dlp fetching %d URLs (parallel=%d)", len(flat), parallel)

    records_by_persona: dict[str, list[VideoRecord]] = defaultdict(list)
    ok = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        future_map = {pool.submit(fetch_metadata, url, src): (p, url, src)
                      for p, url, src in flat}
        done = 0
        for fut in as_completed(future_map):
            persona, _url, _src = future_map[fut]
            done += 1
            if done % 50 == 0:
                log.info("  yt-dlp progress: %d/%d", done, len(flat))
            rec = fut.result()
            if rec is None:
                fail += 1
                continue
            ok += 1
            records_by_persona[persona].append(rec)
    return dict(records_by_persona), ok, fail


# ---------- 主流程 ----------


def load_keywords(path: Path) -> list[tuple[str, str]]:
    """读 tk_keywords.yaml 展平成 [(persona, keyword), ...]"""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    jobs: list[tuple[str, str]] = []
    for persona, info in data.items():
        for kw in info.get("keywords", []):
            jobs.append((persona, kw))
    return jobs


def build_report(
    candidates_by_persona: dict[str, list[VideoCandidate]],
    records_by_persona: dict[str, list[VideoRecord]],
    top_n: int,
    min_likes_warn_threshold: int,
    max_duration_seconds: int = 0,
) -> dict[str, Any]:
    """
    组装最终输出。保留凑 Top N + 标 low_heat_warning。
    v4.6.0：max_duration_seconds > 0 时硬过滤掉 duration > max_duration_seconds 的视频。
    """
    per_persona: dict[str, Any] = {}
    for persona, records in records_by_persona.items():
        # v4.6.0 时长硬过滤（在排序之前）
        if max_duration_seconds > 0:
            records = [r for r in records if 0 < r.duration <= max_duration_seconds]
        sorted_recs = sorted(records, key=lambda r: -r.like_count)
        top = sorted_recs[:top_n]
        max_likes = top[0].like_count if top else 0
        low_heat = max_likes < min_likes_warn_threshold
        # 候选源分布（search-only / hashtag-only / both 各多少）
        cand_source_breakdown = defaultdict(int)
        for c in candidates_by_persona.get(persona, []):
            cand_source_breakdown[c.source] += 1
        per_persona[persona] = {
            "videos": [asdict(r) for r in top],
            "candidates_total": len(candidates_by_persona.get(persona, [])),
            "candidates_by_source": dict(cand_source_breakdown),
            "fetched_count": len(records),
            "max_likes": max_likes,
            "low_heat_warning": low_heat,
        }
    for persona in candidates_by_persona:
        if persona not in per_persona:
            cand_source_breakdown = defaultdict(int)
            for c in candidates_by_persona[persona]:
                cand_source_breakdown[c.source] += 1
            per_persona[persona] = {
                "videos": [],
                "candidates_total": len(candidates_by_persona[persona]),
                "candidates_by_source": dict(cand_source_breakdown),
                "fetched_count": 0,
                "max_likes": 0,
                "low_heat_warning": True,
            }
    return per_persona


def cookies_missing_error_message(cookies_path: Path) -> str:
    return (
        f"Cookies file not found: {cookies_path}\n"
        f"  Run this first to export from Chrome:\n"
        f"    yt-dlp --cookies-from-browser chrome --cookies {cookies_path} \\\n"
        f"      --skip-download --quiet 'https://www.tiktok.com/@tiktok'\n"
        f"  Chrome must be **really logged in** to tiktok.com (cookies must contain sessionid)."
    )


def cookies_invalid_error_message() -> str:
    return (
        "Cookies file exists but contains no `sessionid` for tiktok.com.\n"
        "  Your Chrome is not truly logged into TikTok (only anonymous cookies).\n"
        "  1. Open Chrome → https://www.tiktok.com → log in to an account\n"
        "  2. Re-export cookies (delete the old file first):\n"
        "       rm -f /tmp/tiktok-cookies.txt\n"
        "       yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt \\\n"
        "         --skip-download --quiet 'https://www.tiktok.com/@tiktok'"
    )


def all_pages_empty_error_message() -> str:
    return (
        "ALL pages returned 0 video URLs. Likely causes:\n"
        "  1. Chrome cookies expired - open tiktok.com in Chrome and log in again, re-export\n"
        "  2. TikTok rate-limited your IP - wait 30min or switch network\n"
        "  3. Your TikTok account region differs from US (data won't match US trends)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="TK Template Scout 严格 24h 模式（双源融合）")
    parser.add_argument("--keywords", required=True, type=Path)
    parser.add_argument("--cookies", type=Path, default=Path("/tmp/tiktok-cookies.txt"))
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--top-n", type=int, default=1,
                        help="每 persona 取 Top N（v4.6.0 默认 1）")
    parser.add_argument("--max-duration", type=int, default=15,
                        help="视频最大时长（秒）硬过滤，0 = 不限。v4.6.0 默认 15s")
    parser.add_argument("--source", choices=sorted(VALID_SOURCES), default="search",
                        help="数据源：search 单源（默认，贴 SKILL 原需求）/ hashtag 单源 / both 双源融合")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--scrolls", type=int, default=DEFAULT_SCROLLS)
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY)
    parser.add_argument("--yt-dlp-parallel", type=int, default=DEFAULT_YT_DLP_PARALLEL)
    parser.add_argument("--min-likes-warn", type=int, default=DEFAULT_MIN_LIKES_WARN)
    parser.add_argument("--no-cross-persona-dedup", action="store_true")
    parser.add_argument("--skip-id-verify", action="store_true")
    parser.add_argument("--id-verify-sample", type=int, default=DEFAULT_ID_VERIFY_SAMPLE)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    if not _STEALTH_AVAILABLE:
        log.warning("playwright-stealth not installed, basic anti-detection only")

    # 1. cookies
    if not args.cookies.exists():
        log.error("%s", cookies_missing_error_message(args.cookies))
        sys.exit(2)
    cookies = load_netscape_cookies(args.cookies)
    if not check_cookies_have_session(cookies):
        log.error("%s", cookies_invalid_error_message())
        sys.exit(2)
    log.info("Cookies OK: %s (contains tiktok.com sessionid)", args.cookies)

    # 2. keywords
    keyword_jobs = load_keywords(args.keywords)
    log.info("Loaded %d (persona, keyword) jobs", len(keyword_jobs))

    # 3. Playwright 抓所有
    t0 = time.time()
    candidates_by_persona, errors, raw_counts = asyncio.run(
        scrape_all(
            keyword_jobs, cookies, args.source,
            args.parallel, args.scrolls, args.retry, args.max_age_hours,
        )
    )
    log.info("Playwright phase done in %.1fs, %d errors", time.time() - t0, len(errors))
    log.info("Raw URL counts by source: %s", raw_counts)

    # 4. cookies 失效检测
    if sum(raw_counts.values()) == 0 and len(keyword_jobs) > 0:
        log.error("%s", all_pages_empty_error_message())
        sys.exit(3)

    # 5. cross-persona dedup
    if not args.no_cross_persona_dedup:
        candidates_by_persona, conflicts = cross_persona_dedup(candidates_by_persona)
        log.info("Cross-persona dedup: %d conflicts resolved", conflicts)
    else:
        conflicts = 0

    # 6. ID 解码二次验证
    id_verify_stats: dict[str, int] = {}
    if not args.skip_id_verify:
        verified, mismatch = verify_id_decoding_sample(
            candidates_by_persona, args.id_verify_sample, ID_VERIFY_DIFF_THRESHOLD_HOURS,
        )
        id_verify_stats = {"verified": verified, "mismatch": mismatch}

    # 7. yt-dlp
    t1 = time.time()
    records_by_persona, ok_count, fail_count = fetch_metadata_for_all(
        candidates_by_persona, args.yt_dlp_parallel,
    )
    log.info("yt-dlp phase done in %.1fs, ok=%d fail=%d",
             time.time() - t1, ok_count, fail_count)

    # 8. 组装输出（v4.6.0：含时长硬过滤）
    per_persona = build_report(
        candidates_by_persona, records_by_persona, args.top_n, args.min_likes_warn,
        max_duration_seconds=args.max_duration,
    )

    # 全局 source 分布
    global_source_breakdown: dict[str, int] = defaultdict(int)
    for cands in candidates_by_persona.values():
        for c in cands:
            global_source_breakdown[c.source] += 1

    output = {
        "mode": f"strict_24h_playwright_source={args.source}",
        "generated_at": int(time.time()),
        "max_age_hours": args.max_age_hours,
        "max_duration_seconds": args.max_duration,
        "top_n": args.top_n,
        "source_mode": args.source,
        "min_likes_warn_threshold": args.min_likes_warn,
        "stats": {
            "total_keyword_jobs": len(keyword_jobs),
            "total_url_fetches": sum(raw_counts.values()) > 0 and
                                 len(keyword_jobs) * (2 if args.source == "both" else 1) or 0,
            "scrape_errors": len(errors),
            "raw_url_counts_by_source": raw_counts,
            "candidates_total": sum(len(v) for v in candidates_by_persona.values()),
            "candidates_by_source": dict(global_source_breakdown),
            "cross_persona_conflicts_resolved": conflicts,
            "id_verify": id_verify_stats,
            "metadata_ok": ok_count,
            "metadata_fail": fail_count,
            "personas_with_data": sum(1 for v in per_persona.values() if v["videos"]),
            "personas_low_heat": sum(1 for v in per_persona.values() if v["low_heat_warning"]),
        },
        "errors": [
            {"persona": p, "keyword": kw, "source": s, "msg": m}
            for p, kw, s, m in errors
        ],
        "personas": per_persona,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
