#!/usr/bin/env python3
"""tk-niche-scout 收割器：TikTok 搜索页雪球创作者 + curl 验粉丝。

用法:
  python3 harvest.py --niche niches/comedy.yaml --stream 1 [--workdir ~/.cache/ops-skills/comedy]

铁律（2026-06-12 实战）:
  - 单 context 串行 + 2-4s 抖动。4 并发连续轰炸 = 全员软拦截 + 会话级风控升级。
  - patchright 优先（vanilla playwright headless 会被弹 CAPTCHA）。
  - cookies 必须含 sessionid（~/.config/ops-skills/tiktok-cookies.txt）。

输出（workdir 下，按 stream 后缀）:
  s<N>_raw.json / s<N>_followers.json / s<N>_ugc.txt（≤cap+未知） / s<N>_big.txt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tk_lib  # noqa: E402

try:
    from patchright.async_api import async_playwright
    _USING_PATCHRIGHT = True
except ImportError:
    from playwright.async_api import async_playwright
    _USING_PATCHRIGHT = False

try:
    from playwright_stealth import Stealth
    _STEALTH = not _USING_PATCHRIGHT
except ImportError:
    _STEALTH = False

HANDLE_RE = re.compile(r"/@([A-Za-z0-9._]{2,24})")
PAGE_TIMEOUT_MS = 40_000
SELECTOR_TIMEOUT_MS = 12_000
SCROLLS = 4
SCROLL_PAUSE_MS = 1_100
QUERY_GAP_S = (2.0, 4.0)
FOLLOWER_WORKERS = 3
DEFAULT_COOKIES = Path.home() / ".config" / "ops-skills" / "tiktok-cookies.txt"


async def make_context(browser, cookies):
    if _USING_PATCHRIGHT:
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    else:
        ctx = await browser.new_context(
            user_agent=tk_lib.UA, viewport={"width": 1280, "height": 900}, locale="en-US")
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    await ctx.add_cookies(cookies)
    return ctx


async def harvest_query(ctx, query: str) -> list[str]:
    url = (f"https://www.tiktok.com/search/video?q={query.replace(' ', '%20')}"
           f"&publish_time=0&sort_type=0")
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        try:
            await page.wait_for_selector('a[href*="/video/"]', timeout=SELECTOR_TIMEOUT_MS)
        except Exception:
            pass
        for _ in range(SCROLLS):
            await page.evaluate("window.scrollBy(0, window.innerHeight*2)")
            await page.wait_for_timeout(SCROLL_PAUSE_MS)
        videos = await page.evaluate(
            "() => { const s=new Set();"
            " document.querySelectorAll('a[href*=\"/video/\"]').forEach(a=>s.add(a.href));"
            " return Array.from(s); }"
        )
    finally:
        await page.close()
    return sorted({m.group(1).lower() for v in videos for m in [HANDLE_RE.search(v)] if m})


async def run(cfg: dict, stream: str, workdir: Path, cookies_path: Path) -> None:
    queries = cfg[f"queries_stream{stream}"]
    cookies = tk_lib.load_netscape_cookies(cookies_path)
    if not tk_lib.check_cookies_have_session(cookies):
        print(f"FATAL: {cookies_path} 无 tiktok.com sessionid，先登录 Chrome 重导", file=sys.stderr)
        sys.exit(2)

    raw: dict[str, list[str]] = {}
    t0 = time.time()
    async with async_playwright() as p:
        kwargs = {"headless": True,
                  "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]}
        if _USING_PATCHRIGHT:
            kwargs["channel"] = "chromium"
        browser = await p.chromium.launch(**kwargs)
        ctx = await make_context(browser, cookies)
        if _STEALTH:
            await Stealth().apply_stealth_async(ctx)
        for i, q in enumerate(queries):
            try:
                raw[q] = await harvest_query(ctx, q)
                print(f"[{i+1:2d}/{len(queries)}] {q:28s} h={len(raw[q]):3d}", flush=True)
            except Exception as e:  # noqa: BLE001 单 query 失败不阻塞
                raw[q] = []
                print(f"[{i+1:2d}/{len(queries)}] {q:28s} FAIL {str(e)[:60]}", flush=True)
            await asyncio.sleep(random.uniform(*QUERY_GAP_S))
        await browser.close()
    (workdir / f"s{stream}_raw.json").write_text(json.dumps(raw, ensure_ascii=False))

    handles = sorted({h for hs in raw.values() for h in hs})
    print(f"search {time.time()-t0:.0f}s, {len(handles)} 号，{FOLLOWER_WORKERS} 线程验粉丝", flush=True)
    followers: dict[str, int | None] = {}
    with ThreadPoolExecutor(max_workers=FOLLOWER_WORKERS) as pool:
        for i, (h, f) in enumerate(pool.map(tk_lib.follower_count, handles)):
            followers[h] = f
            if (i + 1) % 40 == 0:
                print(f"  followers {i+1}/{len(handles)}", flush=True)
    (workdir / f"s{stream}_followers.json").write_text(json.dumps(followers, ensure_ascii=False))

    cap = cfg["ugc_follower_cap"]
    ugc = [h for h, f in followers.items() if f is None or 0 < f <= cap]
    big = [h for h, f in followers.items() if f is not None and f > cap]
    (workdir / f"s{stream}_ugc.txt").write_text("\n".join(ugc) + "\n")
    (workdir / f"s{stream}_big.txt").write_text("\n".join(big) + "\n")
    print(f"DONE {time.time()-t0:.0f}s | UGC(含未知): {len(ugc)} | 大号: {len(big)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="tk-niche-scout 收割器")
    ap.add_argument("--niche", required=True, type=Path, help="niches/<name>.yaml")
    ap.add_argument("--stream", choices=["1", "2"], required=True)
    ap.add_argument("--workdir", type=Path, default=None,
                    help="默认 ~/.cache/ops-skills/<niche>")
    ap.add_argument("--cookies", type=Path, default=DEFAULT_COOKIES)
    args = ap.parse_args()

    cfg = tk_lib.load_niche(args.niche)
    workdir = args.workdir or Path.home() / ".cache" / "ops-skills" / cfg["niche"]
    workdir.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(cfg, args.stream, workdir, args.cookies))


if __name__ == "__main__":
    main()
