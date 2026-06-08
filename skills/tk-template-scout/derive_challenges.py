#!/usr/bin/env python3
"""
derive_challenges.py - 从 scout_strict.py 真抓数据里【数据驱动】挖 Top3 候选。

为什么有这个脚本（可靠性改进 v6.1）：
  原来 Top3 候选靠 Claude WebSearch「找线索 + 猜 hashtag」，源头不稳（搜索引擎索引
  延迟 + hashtag 猜错会漏真热点）。本脚本换个思路：scout 已经【真抓】了各 persona
  24h 内高赞视频，它们标题自带 hashtag + 真点赞。把这些 hashtag 跨 persona 聚合、
  按赞加权 —— 反复出现的高赞 hashtag 就是【客观可证实】的跨赛道真热，不靠猜。

  例：#monacogp 在 avery(47万) + spencer(3.5万) 两个角色都冒头 → F1 摩纳哥是
  数据驱动抓出来的，不是 WebSearch 猜的。

  定位：本脚本出【主候选】（角色赛道内真热）；WebSearch 出【补充候选】（补 scout
  关键词覆盖不到的纯格式类，如对口型 sound）。两路都要过 grab_viral_challenges.py
  的「7 天内真样本 + 赞地板」硬关才进 Top3。

用法：
  python3 derive_challenges.py --json /tmp/tk-result.json --top 12
  # 输出 JSON：跨 persona 高频高赞 hashtag 排行，给 Claude 选数据驱动候选
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# 通用噪声 hashtag：人人都打、不代表具体挑战，聚合时剔除
STOPWORDS = {
    "fyp", "fypシ", "fypage", "foryou", "foryoupage", "foryourpage", "viral",
    "viralvideo", "trending", "trend", "tiktok", "xyzbca", "capcut", "edit",
    "explore", "explorepage", "viraltiktok", "tiktokviral", "fy", "f", "y",
    "duet", "trendingnow", "4u", "4you", "pourtoi", "parati", "reels",
}

HASHTAG_RE = re.compile(r"#([A-Za-z0-9_À-ɏ]+)")


def extract_hashtags(title: str) -> list[str]:
    """从视频标题里抽 hashtag（小写归一，剔噪声/纯数字/单字符）。"""
    out = []
    for raw in HASHTAG_RE.findall(title or ""):
        tag = raw.lower()
        # 只剔单字符（len<2）：保留 #f1 #ai #gp 这类 2 字符有意义标签，避免漏热点
        if tag in STOPWORDS or tag.isdigit() or len(tag) < 2:
            continue
        out.append(tag)
    return out


def aggregate(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    跨 persona 聚合 hashtag。
    返回排序后的 [{hashtag, n_personas, personas, n_videos, total_likes, max_likes, sample_url}]。
    排序：先跨 persona 数降序（跨赛道传播是核心信号），再总赞降序。
    """
    agg: dict[str, dict[str, Any]] = {}
    for pk, info in (data.get("personas") or {}).items():
        for v in info.get("videos", []):
            likes = v.get("like_count") or 0
            tags = set(extract_hashtags(v.get("title", "")))  # 同一视频内同 tag 只算一次
            for tag in tags:
                slot = agg.setdefault(tag, {
                    "hashtag": tag, "personas": set(), "n_videos": 0,
                    "total_likes": 0, "max_likes": 0, "sample_url": "",
                })
                slot["personas"].add(pk)
                slot["n_videos"] += 1
                slot["total_likes"] += likes
                if likes > slot["max_likes"]:
                    slot["max_likes"] = likes
                    slot["sample_url"] = v.get("url", "")

    rows = []
    for slot in agg.values():
        rows.append({
            "hashtag": slot["hashtag"],
            "n_personas": len(slot["personas"]),
            "personas": sorted(slot["personas"]),
            "n_videos": slot["n_videos"],
            "total_likes": slot["total_likes"],
            "max_likes": slot["max_likes"],
            "sample_url": slot["sample_url"],
        })
    rows.sort(key=lambda r: (-r["n_personas"], -r["total_likes"]))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="从 scout 真抓数据里数据驱动挖 Top3 候选 hashtag")
    ap.add_argument("--json", type=Path, required=True, help="scout_strict.py 输出的 result.json")
    ap.add_argument("--top", type=int, default=12, help="输出前 N 个 hashtag")
    args = ap.parse_args()

    if not args.json.exists():
        print(f"ERROR: not found: {args.json}", file=sys.stderr)
        sys.exit(2)
    data = json.load(args.json.open(encoding="utf-8"))
    rows = aggregate(data)
    print(json.dumps(rows[: args.top], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
