#!/usr/bin/env python3
"""tk-niche-scout 总指挥：等收割 → 枚举(UGC 优先) → 四道净化 → 粉丝分桶 → 出货。

用法:
  python3 autopilot.py --niche niches/fashion.yaml \
      [--workdir DIR] [--dedup-against ~/Downloads/us_beauty_*.tsv ...] \
      [--guard-window 08:28-08:55] [--target 1000]

设计（全部来自 2026-06-12 实战教训）:
  - 幂等：每步有 state/产物文件即跳过，断电/被杀后重启本脚本即断点续跑
  - 长活永远 nohup 后台 + 日志轮询，不在前台死等
  - --guard-window 内不开重活（给生产定时任务让路）
  - 四道净化：跨赛道去重 → 视频级硬广 → 账号名规则 → caption 信号打分
  - 交付到 ~/Downloads：final TSV(9 列) + 纯链接 TXT + removed 存档(带原因)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tk_lib  # noqa: E402

HARVEST_WAIT_MIN = 100
FOLLOWER_WORKERS = 3
TSV_HEADER = ("bucket\turl\tviews\tduration_s\tupload_date\tcreator"
              "\tfollowers\tviews_per_follower\tcaption\n")
REM_HEADER = "reason\turl\tviews\tduration_s\tupload_date\tcreator\tcaption\n"


def log(msg: str) -> None:
    print(f"[autopilot {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_for(path: Path, max_minutes: int) -> bool:
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(15)
    return False


def in_guard_window(window: str | None) -> bool:
    if not window:
        return False
    try:
        start, end = window.split("-")
        now = time.strftime("%H:%M")
        return start <= now < end
    except ValueError:
        return False


def hold_guard(window: str | None) -> None:
    while in_guard_window(window):
        log(f"生产窗口({window})，重活待命...")
        time.sleep(60)


def run_enum(skill_dir: Path, listfile: Path, prefix: str, workdir: Path,
             guard: str | None) -> None:
    state = workdir / f"{prefix}_state.json"
    if state.exists():
        log(f"{prefix} 已完成，跳过")
        return
    handles = tk_lib.read_handles(listfile)
    if not handles:
        state.write_text(json.dumps({"links_total": 0, "accounts_total": 0, "elapsed_s": 0,
                                     "per_account": {}, "accounts_failed": []}))
        log(f"{prefix}: 清单空，跳过")
        return
    hold_guard(guard)
    log(f"{prefix}: 开扫 {len(handles)} 号")
    with (workdir / f"{prefix}_enum.log").open("w") as lf:
        subprocess.run(
            [sys.executable, str(skill_dir / "enumerate_profiles.py"),
             "--handles", str(listfile), "--prefix", prefix, "--workdir", str(workdir)],
            stdout=lf, stderr=subprocess.STDOUT, check=False)
    if state.exists():
        s = json.loads(state.read_text())
        log(f"{prefix}: +{s['links_total']} 条 ({s['elapsed_s']}s)")
    else:
        log(f"{prefix}: enumerate 异常退出且无 state（继续后续）")


def main() -> None:  # noqa: PLR0915 编排主流程，按步骤分段已尽量短
    ap = argparse.ArgumentParser(description="tk-niche-scout 总指挥")
    ap.add_argument("--niche", required=True, type=Path)
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--dedup-against", nargs="*", type=Path, default=[],
                    help="先前赛道的 final TSV，URL 撞上即剔（视频级跨赛道去重）")
    ap.add_argument("--guard-window", default="08:28-08:55",
                    help="生产定时任务窗口，重活避让；传空串关闭")
    ap.add_argument("--target", type=int, default=1000, help="仅用于日志提示")
    args = ap.parse_args()

    skill_dir = Path(__file__).resolve().parent
    cfg = tk_lib.load_niche(args.niche)
    niche = cfg["niche"]
    workdir = args.workdir or Path.home() / ".cache" / "ops-skills" / niche
    workdir.mkdir(parents=True, exist_ok=True)
    guard = args.guard_window or None
    log(f"{niche} autopilot 启动 (workdir={workdir})")

    # 1. 等两条收割流
    s1 = wait_for(workdir / "s1_ugc.txt", HARVEST_WAIT_MIN)
    s2 = wait_for(workdir / "s2_ugc.txt", HARVEST_WAIT_MIN)
    log(f"收割流: s1={'ok' if s1 else 'miss'} s2={'ok' if s2 else 'miss'}")

    # 2. 建清单：UGC = 两流 ugc 并集；大号 = yaml 种子 + 两流大号溢出 - UGC
    ugc_list = workdir / "ugc_list.txt"
    celeb_list = workdir / "celeb_list.txt"
    if not ugc_list.exists():
        ugc = list(dict.fromkeys(
            tk_lib.read_handles(workdir / "s1_ugc.txt")
            + tk_lib.read_handles(workdir / "s2_ugc.txt")))
        ugc_list.write_text("\n".join(ugc) + "\n")
        log(f"UGC 清单 {len(ugc)} 号")
    if not celeb_list.exists():
        seeds = [h.lower() for h in cfg.get("seed_handles", [])]
        celeb = list(dict.fromkeys(
            seeds + tk_lib.read_handles(workdir / "s1_big.txt")
            + tk_lib.read_handles(workdir / "s2_big.txt")))
        ugc_set = set(tk_lib.read_handles(ugc_list))
        celeb = [h for h in celeb if h not in ugc_set]
        celeb_list.write_text("\n".join(celeb) + "\n")
        log(f"大号清单 {len(celeb)} 号")

    # 3. 枚举（UGC 优先）
    run_enum(skill_dir, ugc_list, "results_ugc", workdir, guard)
    run_enum(skill_dir, celeb_list, "results_celeb", workdir, guard)

    # 4. 合并 + 硬校验 + URL 去重
    rows_by_url: dict[str, dict] = {}
    for prefix in ["results_ugc", "results_celeb"]:
        for d in tk_lib.read_jsonl(workdir / f"{prefix}.jsonl"):
            u = d.get("url") or ""
            if u and u not in rows_by_url and tk_lib.hard_valid(d):
                rows_by_url[u] = d
    all_rows = list(rows_by_url.values())
    log(f"合并去重: {len(all_rows)} 条 (target={args.target})")

    removed: list[dict] = []

    # 道0: 跨赛道去重
    banned: set[str] = set()
    for tsv in args.dedup_against:
        banned |= tk_lib.load_tsv_urls(tsv)
    if banned:
        all_rows, dup = tk_lib.strip_dup_urls(all_rows, banned)
        removed += [dict(r, reason="与先前赛道名单重复") for r in dup]
        log(f"跨赛道去重: 剔 {len(dup)} 条")

    # 道1: 视频级硬广
    if cfg.get("ad_filter"):
        ads = [r for r in all_rows if tk_lib.is_hard_ad(r["caption"])]
        all_rows = [r for r in all_rows if not tk_lib.is_hard_ad(r["caption"])]
        removed += [dict(r, reason="硬广标签") for r in ads]
        log(f"硬广(视频级): 剔 {len(ads)} 条")

    # 道2+3: 账号级（名字规则 + caption 打分）
    by_creator: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_creator[r["uploader"].lower()].append(r)
    kick: dict[str, str] = {}
    for h, rs in by_creator.items():
        reason = tk_lib.handle_kick_reason(h, cfg)
        if reason is None:
            reason = tk_lib.caption_kick_reason([r["caption"] for r in rs], cfg)
        if reason:
            kick[h] = reason
    kept = [r for r in all_rows if r["uploader"].lower() not in kick]
    removed += [dict(r, reason=kick[r["uploader"].lower()]) for r in all_rows
                if r["uploader"].lower() in kick]
    log(f"账号净化: 剔 {len(kick)} 号, 留 {len(kept)} 条")

    # 5. 粉丝补全 + 分桶 + 排序
    fol: dict[str, int | None] = {}
    for f in ["s1_followers.json", "s2_followers.json", "creator_followers_extra.json"]:
        p = workdir / f
        if p.exists():
            fol.update(json.loads(p.read_text()))
    need = sorted({r["uploader"].lower() for r in kept}
                  - {k for k, v in fol.items() if v is not None})
    log(f"补粉丝 {len(need)} 个创作者")
    extra: dict[str, int | None] = {}
    with ThreadPoolExecutor(max_workers=FOLLOWER_WORKERS) as pool:
        for h, c in pool.map(tk_lib.follower_count, need):
            extra[h] = c
    fol.update({k: v for k, v in extra.items() if v is not None})
    (workdir / "creator_followers_extra.json").write_text(json.dumps(extra, ensure_ascii=False))

    cap = cfg["ugc_follower_cap"]
    for r in kept:
        f = fol.get(r["uploader"].lower())
        r["followers"] = f if f is not None else ""
        r["bucket"] = tk_lib.bucket_of(f, cap)
        r["ratio"] = round(r["views"] / f, 1) if isinstance(f, int) and f > 0 else ""
    kept.sort(key=tk_lib.row_sort_key)

    # 6. 写交付
    stamp = time.strftime("%Y%m%d")
    dl = Path.home() / "Downloads"
    tsv = dl / f"us_{niche}_tiktok_{tk_lib.HARD_YEAR}_final_{stamp}.tsv"
    txt = dl / f"us_{niche}_tiktok_{tk_lib.HARD_YEAR}_final_{stamp}_links.txt"
    rem = dl / f"us_{niche}_tiktok_{tk_lib.HARD_YEAR}_removed_{stamp}.tsv"
    with tsv.open("w") as f:
        f.write(TSV_HEADER)
        for r in kept:
            f.write(f"{r['bucket']}\t{r['url']}\t{r['views']}\t{r['duration']}"
                    f"\t{r['upload_date']}\t{r['uploader']}\t{r['followers']}"
                    f"\t{r['ratio']}\t{r['caption']}\n")
    txt.write_text("\n".join(r["url"] for r in kept) + "\n")
    with rem.open("w") as f:
        f.write(REM_HEADER)
        for r in removed:
            f.write(f"{r['reason']}\t{r['url']}\t{r['views']}\t{r['duration']}"
                    f"\t{r['upload_date']}\t{r['uploader']}\t{r['caption']}\n")

    summary = {
        "finished_at": time.strftime("%F %T"),
        "niche": niche,
        "total_kept": len(kept),
        "removed": len(removed),
        "removed_accounts": len(kick),
        "ugc": sum(1 for r in kept if r["bucket"] == "UGC模板"),
        "celeb": sum(1 for r in kept if r["bucket"] == "名人/大号"),
        "unknown": sum(1 for r in kept if r["bucket"] == "未知"),
        "creators": len({r["uploader"] for r in kept}),
        "tsv": str(tsv), "txt": str(txt), "removed_tsv": str(rem),
    }
    (workdir / "final_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    log(f"FINAL total={summary['total_kept']} ugc={summary['ugc']} "
        f"celeb={summary['celeb']} removed={summary['removed']} -> {tsv}")


if __name__ == "__main__":
    main()
