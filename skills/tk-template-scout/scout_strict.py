#!/usr/bin/env python3
"""
TK Template Scout - 严格 24h 模式（Playwright + hashtag + ID 解码）

和 scout.py（WebSearch + yt-dlp，受 Google 索引延迟限制）相比，本脚本：
1. 直接抓 TikTok hashtag 页（/tag/<hashtag>），按时间倒序拿真实 24h 内视频
2. 用 video_id >> 32 解码 timestamp 做硬过滤（无网络请求，秒级精度）
3. 抽 sample 走 yt-dlp 验证 ID 解码假设没失效（防 TikTok 改 ID 格式静默错）
4. cross-persona dedup：同视频被多 persona 抓到 → 归给候选最少的（冷门优先）
5. 用 yt-dlp 给候选 URL 补 like_count / title / uploader
6. 按 like_count 取 Top N

前置：
  - Chrome 已**真实登录** tiktok.com（cookies 必须含 sessionid 不只是 ttwid）
  - playwright + chromium 已装：pip install playwright && playwright install chromium
  - playwright-stealth 已装（反检测，可选但推荐）
  - yt-dlp 已装

cookies 文件必须先手动导出（脚本不再自动导，避免 probe URL 过期）：
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
from dataclasses import asdict, dataclass
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
    """从 hashtag 页解析出来的候选（只有 URL 和 timestamp，没点赞）。"""

    persona: str
    hashtag: str
    url: str
    video_id: str
    timestamp: int  # unix seconds（ID 解码值）
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
    timestamp: int  # yt-dlp 拿到的真实值


# ---------- 配置常量 ----------

DEFAULT_PARALLEL = 4  # Playwright 并发 worker 数（每个复用 1 个 context）
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


# ---------- Cookie 加载（Netscape → Playwright 格式） ----------


def load_netscape_cookies(path: Path) -> list[dict[str, Any]]:
    """yt-dlp 导出的 Netscape cookies 文件 → Playwright add_cookies 格式。"""
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
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path_,
                    "secure": secure == "TRUE",
                    "expires": exp_i,
                    "httpOnly": False,
                    "sameSite": "Lax",
                }
            )
    return cookies


def check_cookies_have_session(cookies: list[dict[str, Any]]) -> bool:
    """检查 cookies 是否含真实登录 session（不只是 anonymous browsing cookies）。"""
    tiktok_cookie_names = {
        c["name"] for c in cookies if "tiktok.com" in c["domain"]
    }
    # sessionid 是登录后才有的核心 cookie
    return "sessionid" in tiktok_cookie_names


# ---------- 关键词 → hashtag ----------


def keyword_to_hashtag(keyword: str) -> str:
    """'old money outfit' → 'oldmoneyoutfit'."""
    return re.sub(r"[^a-z0-9]", "", keyword.lower())


# ---------- Playwright 抓 hashtag ----------


async def make_context(browser: Browser, cookies: list[dict[str, Any]]) -> BrowserContext:
    """建一个新 context 并注入 cookies + 反检测脚本。"""
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    # 基础反检测（即使 stealth 没装也跑这个）
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        """
    )
    await context.add_cookies(cookies)
    return context


async def scrape_one_hashtag(
    context: BrowserContext,
    persona: str,
    hashtag: str,
    scrolls: int,
    cutoff_ts: float,
    now_ts: float,
) -> tuple[list[VideoCandidate], int]:
    """
    单个 hashtag 页：抓所有 video URL，ID 解码筛 24h 内。
    返回 (24h 内候选列表, 原始抓到的 URL 数)。
    raw URL count 用于 cookies 失效检测（全 0 → 拿到登录墙）。
    """
    url = f"https://www.tiktok.com/tag/{hashtag}"
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        try:
            await page.wait_for_selector('a[href*="/video/"]', timeout=SELECTOR_TIMEOUT_MS)
        except Exception:
            pass  # 也许真没视频，继续提取看看

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
        ts = vid >> 32  # snowflake: high 32 bits = unix seconds
        if ts < cutoff_ts:
            continue
        candidates.append(
            VideoCandidate(
                persona=persona,
                hashtag=hashtag,
                url=u,
                video_id=vid_str,
                timestamp=ts,
                age_hours=round((now_ts - ts) / 3600, 1),
            )
        )
    return candidates, len(urls)


async def scrape_one_with_retry(
    context: BrowserContext,
    persona: str,
    hashtag: str,
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
            cands, raw = await scrape_one_hashtag(
                context, persona, hashtag, scrolls, cutoff_ts, now_ts
            )
            elapsed = time.time() - t0
            log.info(
                "  %-10s #%-30s %2d fresh / %3d raw in %4.1fs%s",
                persona, hashtag, len(cands), raw, elapsed,
                f" (attempt {attempt + 1})" if attempt > 0 else "",
            )
            return cands, raw, None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < retry:
                log.warning("  %-10s #%-30s attempt %d failed, retrying: %s",
                            persona, hashtag, attempt + 1, last_err)
                await asyncio.sleep(2)
    log.error("  %-10s #%-30s ALL %d attempts failed: %s",
              persona, hashtag, retry + 1, last_err)
    return [], 0, last_err


async def worker_loop(
    browser: Browser,
    cookies: list[dict[str, Any]],
    jobs: asyncio.Queue,
    results: list[VideoCandidate],
    raw_url_counts: list[int],
    errors: list[tuple[str, str, str]],
    scrolls: int,
    cutoff_ts: float,
    now_ts: float,
    retry: int,
) -> None:
    """一个 worker 复用 1 个 context 处理多个 hashtag job。"""
    context = await make_context(browser, cookies)
    if _STEALTH_AVAILABLE:
        await Stealth().apply_stealth_async(context)
    try:
        while True:
            try:
                persona, hashtag = jobs.get_nowait()
            except asyncio.QueueEmpty:
                return
            cands, raw, err = await scrape_one_with_retry(
                context, persona, hashtag, scrolls, cutoff_ts, now_ts, retry,
            )
            results.extend(cands)
            raw_url_counts.append(raw)
            if err:
                errors.append((persona, hashtag, err))
            jobs.task_done()
    finally:
        await context.close()


async def scrape_all_hashtags(
    keyword_jobs: list[tuple[str, str]],
    cookies: list[dict[str, Any]],
    parallel: int,
    scrolls: int,
    retry: int,
    max_age_hours: int,
) -> tuple[dict[str, list[VideoCandidate]], list[tuple[str, str, str]], int]:
    """
    并行抓所有 (persona, hashtag) job。每个 worker 复用 1 个 context。
    返回 (by_persona_dedup_internal, errors, raw_url_total)。
    """
    log.info("Loaded %d cookies", len(cookies))

    now_ts = time.time()
    cutoff_ts = now_ts - max_age_hours * 3600

    jobs: asyncio.Queue = asyncio.Queue()
    for j in keyword_jobs:
        jobs.put_nowait(j)

    results: list[VideoCandidate] = []
    raw_url_counts: list[int] = []
    errors: list[tuple[str, str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            workers = [
                asyncio.create_task(
                    worker_loop(browser, cookies, jobs, results, raw_url_counts, errors,
                                scrolls, cutoff_ts, now_ts, retry)
                )
                for _ in range(parallel)
            ]
            await asyncio.gather(*workers)
        finally:
            await browser.close()

    # persona 内 dedup（同 persona 3 hashtag 合并）
    by_persona: dict[str, list[VideoCandidate]] = defaultdict(list)
    for c in results:
        by_persona[c.persona].append(c)
    final: dict[str, list[VideoCandidate]] = {}
    for persona, cands in by_persona.items():
        seen: set[str] = set()
        dedup: list[VideoCandidate] = []
        for c in sorted(cands, key=lambda x: -x.timestamp):
            if c.video_id in seen:
                continue
            seen.add(c.video_id)
            dedup.append(c)
        final[persona] = dedup
    return final, errors, sum(raw_url_counts)


# ---------- Cross-persona dedup（修 #1）----------


def cross_persona_dedup(
    by_persona: dict[str, list[VideoCandidate]],
) -> tuple[dict[str, list[VideoCandidate]], int]:
    """
    同视频被多 persona 抓到 → 归给候选数最少的（让冷门赛道优先获得素材）。
    返回 (deduped_dict, conflict_count)。

    例：'snacks' 视频同时在 ryan(15 候选) / avery(8 候选) / joey(20 候选) 出现，
    归给 avery（候选最少）。
    """
    # 每个 video_id 出现在哪些 persona
    vid_to_personas: dict[str, list[str]] = defaultdict(list)
    for persona, cands in by_persona.items():
        for c in cands:
            vid_to_personas[c.video_id].append(persona)

    # 每个 persona 候选总数（作为"赛道供给"指标，少 = 冷门 = 优先获得）
    persona_count = {p: len(cands) for p, cands in by_persona.items()}

    # 决定冲突视频归谁
    vid_owner: dict[str, str] = {}
    conflicts = 0
    for vid, personas in vid_to_personas.items():
        if len(personas) > 1:
            conflicts += 1
            owner = min(personas, key=lambda p: (persona_count[p], p))  # 平局按字母
            vid_owner[vid] = owner

    # 过滤：冲突视频只保留在 owner 那
    deduped: dict[str, list[VideoCandidate]] = {}
    for persona, cands in by_persona.items():
        deduped[persona] = [
            c for c in cands
            if c.video_id not in vid_owner or vid_owner[c.video_id] == persona
        ]
    return deduped, conflicts


# ---------- ID 解码二次验证（修 #2）----------


def verify_id_decoding_sample(
    by_persona: dict[str, list[VideoCandidate]],
    sample_size: int,
    diff_threshold_hours: float,
) -> tuple[int, int]:
    """
    抽 sample 走 yt-dlp 拿真 timestamp，对比 ID 解码值。
    返回 (verified_count, mismatch_count)。

    超过半数 mismatch → 强警告，疑似 TikTok 改 ID 格式。
    """
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
        rec = fetch_metadata(c.url)
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
        log.info("ID decoding OK: %d/%d samples within %.1fh", verified - mismatch, verified, diff_threshold_hours)
    return verified, mismatch


# ---------- yt-dlp 抓元数据 ----------


def fetch_metadata(url: str, browser: str = "chrome", timeout: int = 30) -> VideoRecord | None:
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
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    except Exception:  # noqa: BLE001 yt-dlp 偶发异常太杂
        return None


def fetch_metadata_for_all(
    candidates_by_persona: dict[str, list[VideoCandidate]],
    parallel: int,
) -> tuple[dict[str, list[VideoRecord]], int, int]:
    """并行跑 yt-dlp 给所有候选 URL 补元数据。返回 (records_by_persona, ok, fail)."""
    flat: list[tuple[str, str]] = [
        (persona, c.url)
        for persona, cands in candidates_by_persona.items()
        for c in cands
    ]
    log.info("yt-dlp fetching %d URLs (parallel=%d)", len(flat), parallel)

    records_by_persona: dict[str, list[VideoRecord]] = defaultdict(list)
    ok = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        future_map = {pool.submit(fetch_metadata, url): (p, url) for p, url in flat}
        done = 0
        for fut in as_completed(future_map):
            persona, _url = future_map[fut]
            done += 1
            if done % 30 == 0:
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
    """读 tk_keywords.yaml 展平成 [(persona, hashtag), ...]。"""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    jobs: list[tuple[str, str]] = []
    for persona, info in data.items():
        for kw in info.get("keywords", []):
            jobs.append((persona, keyword_to_hashtag(kw)))
    return jobs


def build_report(
    candidates_by_persona: dict[str, list[VideoCandidate]],
    records_by_persona: dict[str, list[VideoRecord]],
    top_n: int,
    min_likes_warn_threshold: int,
) -> dict[str, Any]:
    """组装最终输出。保留凑 Top N，但每个 persona 标注 low_heat_warning。"""
    per_persona: dict[str, Any] = {}
    for persona, records in records_by_persona.items():
        sorted_recs = sorted(records, key=lambda r: -r.like_count)
        top = sorted_recs[:top_n]
        max_likes = top[0].like_count if top else 0
        low_heat = max_likes < min_likes_warn_threshold
        per_persona[persona] = {
            "videos": [asdict(r) for r in top],
            "candidates_total": len(candidates_by_persona.get(persona, [])),
            "fetched_count": len(records),
            "max_likes": max_likes,
            "low_heat_warning": low_heat,
        }
    # 没拿到任何候选的 persona 也列出来
    for persona in candidates_by_persona:
        if persona not in per_persona:
            per_persona[persona] = {
                "videos": [],
                "candidates_total": len(candidates_by_persona[persona]),
                "fetched_count": 0,
                "max_likes": 0,
                "low_heat_warning": True,
            }
    return per_persona


def cookies_missing_error_message(cookies_path: Path) -> str:
    """修 #3：给用户清楚的导出 cookies 指引。"""
    return (
        f"Cookies file not found: {cookies_path}\n"
        f"  Run this first to export from Chrome:\n"
        f"    yt-dlp --cookies-from-browser chrome --cookies {cookies_path} \\\n"
        f"      --skip-download --quiet 'https://www.tiktok.com/@tiktok'\n"
        f"  Chrome must be **really logged in** to tiktok.com (cookies must contain sessionid)."
    )


def cookies_invalid_error_message() -> str:
    """修 #9：cookies 没含 sessionid 时的提示。"""
    return (
        "Cookies file exists but contains no `sessionid` for tiktok.com.\n"
        "  Your Chrome is not truly logged into TikTok (only anonymous cookies).\n"
        "  1. Open Chrome → https://www.tiktok.com → log in to an account\n"
        "  2. Re-export cookies (delete the old file first):\n"
        "       rm -f /tmp/tiktok-cookies.txt\n"
        "       yt-dlp --cookies-from-browser chrome --cookies /tmp/tiktok-cookies.txt \\\n"
        "         --skip-download --quiet 'https://www.tiktok.com/@tiktok'\n"
        "  3. Check `grep sessionid /tmp/tiktok-cookies.txt` shows tiktok.com entries"
    )


def all_hashtags_empty_error_message() -> str:
    """修 #9：所有 hashtag 页都拿到 0 raw URL 时的诊断。"""
    return (
        "ALL hashtag pages returned 0 video URLs. Likely causes:\n"
        "  1. Chrome cookies expired - open tiktok.com in Chrome and log in again, re-export\n"
        "  2. TikTok rate-limited your IP - wait 30min or switch network\n"
        "  3. Your TikTok account region differs from US (data won't match US trends)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="TK Template Scout 严格 24h 模式")
    parser.add_argument("--keywords", required=True, type=Path,
                        help="tk_keywords.yaml 路径")
    parser.add_argument("--cookies", type=Path, default=Path("/tmp/tiktok-cookies.txt"),
                        help="Netscape cookies 文件（必须先用 yt-dlp 导出）")
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL,
                        help="Playwright worker 数（每个复用 1 context）")
    parser.add_argument("--scrolls", type=int, default=DEFAULT_SCROLLS,
                        help="每个 hashtag 页滚动次数")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY,
                        help="单 hashtag 失败重试次数")
    parser.add_argument("--yt-dlp-parallel", type=int, default=DEFAULT_YT_DLP_PARALLEL)
    parser.add_argument("--min-likes-warn", type=int, default=DEFAULT_MIN_LIKES_WARN,
                        help="Top1 点赞 < 此值则在 JSON 里标 low_heat_warning=true")
    parser.add_argument("--no-cross-persona-dedup", action="store_true",
                        help="关闭 cross-persona dedup（默认开）")
    parser.add_argument("--skip-id-verify", action="store_true",
                        help="跳过 ID 解码 sample 验证（默认开，省时间用）")
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

    # 1. cookies（修 #3：不自动导，明确报错）
    if not args.cookies.exists():
        log.error("%s", cookies_missing_error_message(args.cookies))
        sys.exit(2)
    cookies = load_netscape_cookies(args.cookies)
    if not check_cookies_have_session(cookies):
        log.error("%s", cookies_invalid_error_message())
        sys.exit(2)
    log.info("Cookies OK: %s (contains tiktok.com sessionid)", args.cookies)

    # 2. 加载 keywords
    jobs = load_keywords(args.keywords)
    log.info("Loaded %d (persona, hashtag) jobs from %s", len(jobs), args.keywords)

    # 3. Playwright 抓所有 hashtag
    t0 = time.time()
    candidates_by_persona, errors, raw_url_total = asyncio.run(
        scrape_all_hashtags(
            jobs, cookies, args.parallel, args.scrolls, args.retry, args.max_age_hours,
        )
    )
    log.info("Playwright phase done in %.1fs, %d errors, raw_url_total=%d",
             time.time() - t0, len(errors), raw_url_total)

    # 4. cookies 失效检测（修 #9）
    if raw_url_total == 0 and len(jobs) > 0:
        log.error("%s", all_hashtags_empty_error_message())
        sys.exit(3)

    # 5. cross-persona dedup（修 #1）
    if not args.no_cross_persona_dedup:
        candidates_by_persona, conflicts = cross_persona_dedup(candidates_by_persona)
        log.info("Cross-persona dedup: %d conflicts resolved (冷门 persona 优先获得)", conflicts)
    else:
        conflicts = 0

    # 6. ID 解码二次验证（修 #2）
    id_verify_stats: dict[str, int] = {}
    if not args.skip_id_verify:
        verified, mismatch = verify_id_decoding_sample(
            candidates_by_persona, args.id_verify_sample, ID_VERIFY_DIFF_THRESHOLD_HOURS,
        )
        id_verify_stats = {"verified": verified, "mismatch": mismatch}

    # 7. yt-dlp 抓元数据
    t1 = time.time()
    records_by_persona, ok_count, fail_count = fetch_metadata_for_all(
        candidates_by_persona, args.yt_dlp_parallel,
    )
    log.info("yt-dlp phase done in %.1fs, ok=%d fail=%d",
             time.time() - t1, ok_count, fail_count)

    # 8. 组装输出
    per_persona = build_report(
        candidates_by_persona, records_by_persona, args.top_n, args.min_likes_warn,
    )

    output = {
        "mode": "strict_24h_playwright",
        "generated_at": int(time.time()),
        "max_age_hours": args.max_age_hours,
        "top_n": args.top_n,
        "min_likes_warn_threshold": args.min_likes_warn,
        "stats": {
            "total_jobs": len(jobs),
            "scrape_errors": len(errors),
            "raw_url_total": raw_url_total,
            "candidates_total": sum(len(v) for v in candidates_by_persona.values()),
            "cross_persona_conflicts_resolved": conflicts,
            "id_verify": id_verify_stats,
            "metadata_ok": ok_count,
            "metadata_fail": fail_count,
            "personas_with_data": sum(1 for v in per_persona.values() if v["videos"]),
            "personas_low_heat": sum(1 for v in per_persona.values() if v["low_heat_warning"]),
        },
        "errors": [{"persona": p, "hashtag": h, "msg": m} for p, h, m in errors],
        "personas": per_persona,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
