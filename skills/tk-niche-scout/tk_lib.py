#!/usr/bin/env python3
"""tk-niche-scout 共享库：niche 配置加载 + 净化纯函数 + 通用 I/O。

纯函数（无 I/O，tests/test_tk_niche_scout.py 全覆盖）：
  compile_niche / handle_kick_reason / caption_kick_reason / is_hard_ad
  bucket_of / row_sort_key / hard_valid / strip_dup_urls

I/O 工具（不在单测内）：
  load_netscape_cookies / check_cookies_have_session（沿用 tk-template-scout 实现）
  follower_count（curl 主页 HTML 抠 followerCount，2026-06 实测可用）
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 区域后缀黑名单：handle 以 .xx 国别码结尾基本是非美区商号
REGION_SUFFIX = re.compile(
    r"\.(de|uk|fr|it|es|nl|se|pl|br|mx|ph|my|id|in|pk|ng|ke|gh|au|nz|jp|kr|th|vn|tr|sa|ae|eg|hn|cl|ar|co)$"
)
# 宠物号（toggle: niche.pet_filter）
PET_HANDLE = re.compile(r"(?:^|[._\d])(dogs?|pups?|paws?|cats?)(?:$|[._\d])|dog$|pup$|paw$")
# 硬广（toggle: niche.ad_filter）—— 只能抓"明示广告"，未打标签的软性带货是无解边界
AD_PAT = re.compile(
    r"#ad\b|#sponsored|#paidpartnership|#tiktokshopcreator|#commissionearned|#affiliate|"
    r"use my code|promo code|discount code|coupon code|\b\d{1,2}% off\b|"
    r"link in bio|linkinbio|shop now|shopnow|tap the link", re.I)
# 品牌/店铺号（ad_filter 开启时账号级生效）
BRAND_HANDLE = re.compile(r"shop|store|boutique|apparel|clothing|thelabel|official(store|brand)")

HARD_MIN_VIEWS = 1_000_000
HARD_MAX_DURATION = 15
HARD_YEAR = "2026"


# ---------- niche 配置 ----------


def load_niche(path: Path) -> dict[str, Any]:
    """读 niches/<name>.yaml 并编译正则。失败抛 ValueError（fail fast）。"""
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    required = ["niche", "queries_stream1", "queries_stream2",
                "caption_pos", "caption_neg", "handle_pos", "handle_neg"]
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise ValueError(f"niche yaml 缺字段: {missing} ({path})")
    return compile_niche(raw)


def compile_niche(raw: dict[str, Any]) -> dict[str, Any]:
    """纯函数：把 yaml 原始 dict 编译成可用配置（正则 compile + 默认值）。"""
    cfg = dict(raw)
    cfg["caption_pos_re"] = re.compile("|".join(raw["caption_pos"]), re.I)
    cfg["caption_neg_re"] = re.compile("|".join(raw["caption_neg"]), re.I)
    cfg["handle_pos_re"] = re.compile("|".join(raw["handle_pos"]), re.I)
    cfg["handle_neg_terms"] = [t.lower() for t in raw["handle_neg"]]
    cfg["handle_neg_regex"] = [re.compile(p, re.I) for p in raw.get("handle_neg_patterns", [])]
    cfg["blacklist"] = {h.lower() for h in raw.get("blacklist", [])}
    cfg.setdefault("ugc_follower_cap", 500_000)
    cfg.setdefault("pet_filter", True)
    cfg.setdefault("ad_filter", False)
    cfg.setdefault("strict_zero_pos", False)  # True: 多条且零正信号 → 整号踢（美妆/时尚用）
    return cfg


# ---------- 净化纯函数 ----------


def handle_kick_reason(handle: str, cfg: dict[str, Any]) -> str | None:
    """账号名一票否决类规则。None = 放行到 caption 打分。"""
    h = handle.lower()
    if h in cfg["blacklist"]:
        return "人工黑名单"
    if REGION_SUFFIX.search(h):
        return "非美区后缀"
    if cfg["handle_pos_re"].search(h):
        return None  # 名字自带本赛道正信号 → 豁免负名单
    if cfg.get("ad_filter") and BRAND_HANDLE.search(h):
        return "疑似品牌/带货号"
    for t in cfg["handle_neg_terms"]:
        if t in h:
            return f"账号名负信号({t})"
    for p in cfg["handle_neg_regex"]:
        if p.search(h):
            return f"账号名负信号({p.pattern})"
    if cfg.get("pet_filter") and PET_HANDLE.search(h):
        return "宠物号"
    return None


def caption_kick_reason(captions: list[str], cfg: dict[str, Any]) -> str | None:
    """账号级 caption 汇总打分。None = 保留。"""
    text = " ".join(captions)
    pos = len(cfg["caption_pos_re"].findall(text))
    neg = len(cfg["caption_neg_re"].findall(text))
    if pos == 0 and neg >= 1:
        return f"无正信号+负信号x{neg}"
    if pos == 0 and cfg.get("strict_zero_pos") and len(captions) >= 3:
        return "多条且零赛道信号"
    if neg >= 3 and neg > pos * 1.5:
        return f"负信号占优({neg}>{pos})"
    return None


def is_hard_ad(caption: str) -> bool:
    """视频级硬广判定（明示广告标签/带货话术）。"""
    return bool(AD_PAT.search(caption))


def hard_valid(row: dict[str, Any]) -> bool:
    """三条硬标准末道复验：≥100万 · ≤15s · 2026。"""
    return (row.get("views", 0) >= HARD_MIN_VIEWS
            and 0 < row.get("duration", 99) <= HARD_MAX_DURATION
            and str(row.get("upload_date", "")).startswith(HARD_YEAR))


def strip_dup_urls(rows: list[dict], banned_urls: set[str]) -> tuple[list[dict], list[dict]]:
    """跨赛道去重：URL 撞上 banned 的拆出来。返回 (保留, 剔除)。"""
    kept = [r for r in rows if r.get("url") not in banned_urls]
    dropped = [r for r in rows if r.get("url") in banned_urls]
    return kept, dropped


def bucket_of(followers: int | None, cap: int) -> str:
    if isinstance(followers, int) and followers > 0:
        return "UGC模板" if followers <= cap else "名人/大号"
    return "未知"


def row_sort_key(row: dict[str, Any]) -> tuple:
    """UGC 桶置顶，桶内按播放/粉丝比降序（模板价值），其余按播放。"""
    order = {"UGC模板": 0, "未知": 1, "名人/大号": 2}
    ratio = row.get("ratio")
    ratio_v = ratio if isinstance(ratio, (int, float)) else 0
    return (order.get(row.get("bucket", "未知"), 1), -ratio_v, -row.get("views", 0))


# ---------- I/O 工具 ----------


def load_netscape_cookies(path: Path) -> list[dict[str, Any]]:
    """Netscape cookies.txt → Playwright 格式（沿用 tk-template-scout 实现）。"""
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
    return "sessionid" in {c["name"] for c in cookies if "tiktok.com" in c["domain"]}


def follower_count(handle: str) -> tuple[str, int | None]:
    """curl 主页 HTML 抠 followerCount。None = 没拿到（限流/号没了）。"""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "20", "-A", UA,
             f"https://www.tiktok.com/@{handle}"],
            capture_output=True, text=True, timeout=25,
        )
        m = re.search(r'"followerCount":(\d+)', r.stdout)
        time.sleep(random.uniform(0.2, 0.5))
        return handle, (int(m.group(1)) if m else None)
    except Exception:  # noqa: BLE001 curl 异常种类杂，统一当未拿到
        return handle, None


def read_handles(path: Path) -> list[str]:
    """读 handle 清单（# 注释行跳过，@ 前缀剥掉，保序去重）。"""
    if not path.exists():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for ln in path.read_text().splitlines():
        h = ln.strip().lstrip("@").lower()
        if h and not h.startswith("#") and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for ln in path.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def load_tsv_urls(path: Path, url_col: int = 1) -> set[str]:
    """读交付 TSV 的 URL 列（跨赛道去重用）。"""
    urls: set[str] = set()
    if not path.exists():
        return urls
    for ln in path.read_text().splitlines()[1:]:
        parts = ln.split("\t")
        if len(parts) > url_col:
            urls.add(parts[url_col])
    return urls
