#!/usr/bin/env python3
"""tk-niche-scout 枚举器：yt-dlp 扫创作者主页，硬标准过滤出达标链接。

用法:
  python3 enumerate_profiles.py --handles <list.txt> --prefix results_ugc \
      [--workdir DIR] [--parallel 6] [--playlist-end 250]

硬标准写死: 2026 年发布 · ≤15 秒 · 播放 ≥100 万（改标准请改 tk_lib 常量）。
限流退避借 tk-template-scout scout_strict v5.3 配方:
  失败率 >= 40% 判整体限流 → sleep 60s*轮次 → 只重试失败号，最多 2 轮。
免 cookie：主页枚举不需要登录态（实战 3 赛道 ~1900 号零封禁）。

输出: <workdir>/<prefix>.jsonl + <prefix>_state.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tk_lib  # noqa: E402

DEFAULT_PARALLEL = 6
DEFAULT_PLAYLIST_END = 250
PER_ACCOUNT_TIMEOUT = 240
MAX_RETRY_ROUNDS = 2
RATE_LIMIT_THRESHOLD = 0.4
BACKOFF_SECONDS = 60
MATCH_FILTER = f"view_count>={tk_lib.HARD_MIN_VIEWS} & duration<={tk_lib.HARD_MAX_DURATION}"
DATE_AFTER = f"{tk_lib.HARD_YEAR}0101"


def scan_account(handle: str, playlist_end: int) -> tuple[str, list[dict] | None]:
    """返回 (handle, 达标视频列表)；None = 抓取失败可重试；[] = 真 0 命中。"""
    cmd = [
        "yt-dlp", "--skip-download", "--no-warnings", "--ignore-errors",
        "--socket-timeout", "15",
        "--playlist-end", str(playlist_end),
        "--dateafter", DATE_AFTER,
        "--match-filter", MATCH_FILTER,
        "--dump-json",
        f"https://www.tiktok.com/@{handle}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_ACCOUNT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return handle, None
    except Exception:  # noqa: BLE001
        return handle, None

    vids: list[dict] = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        caption = (d.get("title") or d.get("description") or "")
        caption = caption.replace("\t", " ").replace("\n", " ")
        vids.append({
            "url": d.get("webpage_url") or "",
            "views": int(d.get("view_count") or 0),
            "duration": int(d.get("duration") or 0),
            "upload_date": d.get("upload_date") or "",
            "uploader": d.get("uploader") or handle,
            "caption": caption[:200],
        })
    if vids:
        return handle, vids
    err = (r.stderr or "").lower()
    if "unable to" in err or "403" in err or "timed out" in err or "rate" in err:
        return handle, None
    return handle, []


def main() -> None:
    ap = argparse.ArgumentParser(description="tk-niche-scout 枚举器")
    ap.add_argument("--handles", required=True, type=Path)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--workdir", type=Path, default=None, help="默认 = handles 所在目录")
    ap.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    ap.add_argument("--playlist-end", type=int, default=DEFAULT_PLAYLIST_END)
    args = ap.parse_args()

    workdir = args.workdir or args.handles.parent
    out_jsonl = workdir / f"{args.prefix}.jsonl"
    state_path = workdir / f"{args.prefix}_state.json"

    handles = tk_lib.read_handles(args.handles)
    total = len(handles)
    print(f"accounts: {total}, parallel={args.parallel}, playlist_end={args.playlist_end}",
          flush=True)

    out_jsonl.write_text("")
    per_account: dict[str, int] = {}
    failed_final: list[str] = []
    seen_urls: set[str] = set()
    kept_total = 0

    pending = handles
    round_no = 0
    t0 = time.time()
    while pending:
        round_failed: list[str] = []
        done = 0
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futs = {pool.submit(scan_account, h, args.playlist_end): h for h in pending}
            for fut in as_completed(futs):
                handle, vids = fut.result()
                done += 1
                if vids is None:
                    round_failed.append(handle)
                    print(f"  [{done:3d}/{len(pending)}] @{handle:24s} FAIL(retryable)", flush=True)
                    continue
                fresh = [v for v in vids if v["url"] and v["url"] not in seen_urls]
                seen_urls.update(v["url"] for v in fresh)
                with out_jsonl.open("a") as f:
                    for v in fresh:
                        f.write(json.dumps(v, ensure_ascii=False) + "\n")
                per_account[handle] = len(fresh)
                kept_total += len(fresh)
                if done % 10 == 0 or fresh:
                    print(f"  [{done:3d}/{len(pending)}] @{handle:24s} +{len(fresh):3d}  "
                          f"total={kept_total}  {time.time()-t0:5.0f}s", flush=True)

        fail_rate = len(round_failed) / len(pending) if pending else 0.0
        if round_failed and round_no < MAX_RETRY_ROUNDS and fail_rate >= RATE_LIMIT_THRESHOLD:
            wait = BACKOFF_SECONDS * (round_no + 1)
            print(f"round {round_no+1}: {len(round_failed)}/{len(pending)} failed "
                  f"({fail_rate:.0%}) — 疑似限流，退避 {wait}s", flush=True)
            time.sleep(wait)
            pending, round_no = round_failed, round_no + 1
        elif round_failed and round_no < MAX_RETRY_ROUNDS:
            pending, round_no = round_failed, round_no + 1
        else:
            failed_final, pending = round_failed, []

    state_path.write_text(json.dumps({
        "finished_at": int(time.time()),
        "elapsed_s": round(time.time() - t0),
        "accounts_total": total,
        "accounts_failed": failed_final,
        "per_account": dict(sorted(per_account.items(), key=lambda kv: -kv[1])),
        "links_total": kept_total,
    }, ensure_ascii=False, indent=1))
    print(f"DONE links={kept_total} accounts={total} failed={len(failed_final)} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
