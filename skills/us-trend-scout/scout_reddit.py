#!/usr/bin/env python3
"""
us-trend-scout / scout_reddit.py

拉 17 个精选 Reddit sub 的 24h top 100 → 三层闸门过滤 → 7 天去重 → 输出 candidates.json

第一层信源（脚本）：Reddit + Google Trends RSS（侧路）
第二层评估（Claude 在 SKILL.md 里）：每条候选 3 yes 定性判断（v5.2 起取代 v5.0 TAEP 评分）+ 可选 WebSearch 跨平台 cross-check

用法：
    python3 scout_reddit.py --output candidates.json
    python3 scout_reddit.py --output candidates.json --no-dedupe
    python3 scout_reddit.py --output candidates.json --history ~/.config/ops-skills/us-trend-history.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── 配置区 ────────────────────────────────────────────────────────────────

USER_AGENT = "us-trend-scout/1.0 by u/ops-skills"
REDDIT_BASE = "https://www.reddit.com"
TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"
DEFAULT_LIMIT = 100  # 每 sub 拉取条数（Reddit API 单次上限）
FETCH_TIMEOUT = 15
FETCH_WORKERS = 8  # 并发数（避免 Reddit rate limit）

# 精选 sub（按测试结果调整 — v2 修正错名 sub）
SUBS = [
    # 核心：文化引爆点金矿
    "OutOfTheLoop",
    # 美妆
    "AsianBeauty", "Sephora", "30PlusSkinCare",
    # 时尚（v2: 修正 sub 名）
    "streetwear", "femalefashionadvice",
    # 健康
    "loseit", "biohackers",
    # 科技
    "artificial", "technology", "OpenAI",
    # 大盘 + 兜底（噪声大，靠 source-sub 黑名单过滤）
    "popular", "news",
    # 影视/娱乐
    "movies", "television", "popculture",
]

# ─── 三层闸门规则 ──────────────────────────────────────────────────────────

# 闸门 1：24h 硬窗口（由代码强制）
MAX_AGE_HOURS = 24

# 闸门 2a：title 关键词排除（主题）
EXCLUDE_TOPIC = [
    "politic", "election", "trump", "biden", "war ", "military",
    "nba", "nfl", "nhl", "baseball", "cricket", "soccer", "hockey",
    "nsfw", "true crime", "shooting", "ukraine", "russia ", "israel", "gaza",
    "putin", "zelensky", "republican", "democrat", "senate", "congress",
    "supreme court", "scotus", "senator",
]

# 闸门 2b：title 关键词排除（形态）
EXCLUDE_FORM = [
    "where can i buy", "rate my", "help with", "progress pic", "before and after",
    "[ootd]", "[wdywt]", "daily megathread", "weekly discussion",
    "routine help", "looking for", "recommendations", "wayww", "throwback",
    "advice needed", "what should i", "should i wear", "how do i", "id help",
    "id this", "id check", "outfit check", "fit check", "what's this",
    "is this normal", "am i the only",
]

# 闸门 2c：source-subreddit 黑名单（按 r/popular crosspost 来源排除娱乐性内容）
# v2 大幅扩展 — 第一轮测试发现 30+ 个娱乐/体育/fandom sub 漏过
# 这是核心改进：r/popular 96% 通过率里 80% 来自这些娱乐 sub crosspost
EXCLUDE_SOURCE_SUB = {
    # 动物/萌宠
    "aww", "cats", "dogs", "AnimalsBeingBros", "rarepuppers", "eyebleach",
    "puppies", "kittens",
    # 感动/温情
    "MadeMeSmile", "wholesomememes", "HumansBeingBros", "UpliftingNews",
    # 搞笑/meme
    "SipsTea", "funny", "memes", "me_irl", "meirl", "dankmemes",
    "Whatcouldgowrong", "PoursTea", "ContagiousLaughter",
    "clevercomebacks", "MurderedByWords", "technicallythetruth",
    "GuysBeingDudes", "TwoSentenceHorror", "TwoSentenceComedy",
    "BlackPeopleTwitter", "WhitePeopleTwitter", "ScottishPeopleTwitter",
    "KidsAreFuckingStupid", "ParentsAreFuckingStupid",
    "BlackPeopleofReddit", "AskOldPeople", "AskMen", "AskWomen",
    "TikTokCringe", "cringe", "facepalm", "iamatotalpieceofshit",
    "blursedimages", "blessedimages", "BlessedComments",
    "whenthe", "ComedyHeaven", "lostredditors", "rareinsults",
    "ChatGPTComedy",
    # 怀旧/讲故事
    "OldSchoolCool", "blunderyears", "OldPhotosInRealLife", "WhatYearWasIt",
    # 视觉爆款（看着爽但不可仿拍）
    "todayilearned", "BeAmazed", "oddlysatisfying", "interesting",
    "Damnthatsinteresting", "interestingasfuck", "nextfuckinglevel",
    "mildlyinfuriating", "mildlyinteresting", "Whatisthis_answered",
    "pics", "gifs", "videos", "PublicFreakout",
    "NatureIsFuckingLit", "gardening", "aquariums", "cozyplaces",
    "AccidentalRenaissance", "FoodPorn", "EarthPorn",
    # 极客/技术 fandom
    "programmerhumor", "ProgrammerHumor", "linuxmemes", "pcmasterrace",
    "gaming", "Games", "gamingcirclejerk",
    # 社交剧/职场剧
    "MaliciousCompliance", "AmItheAsshole", "AITAH", "tifu",
    "relationship_advice", "relationships", "datinginstincts",
    "datingoverthirty", "askMRP", "OutOfTheTombs",
    "legaladvice", "JustNoMIL", "raisedbynarcissists", "ChoosingBeggars",
    "EntitledParents", "EntitledPeople", "JUSTNOFAMILY",
    "antiwork", "WorkReform",
    # 政治讽刺/边缘
    "PoliticalHumor", "ShitAmericansSay", "TheRightCantMeme",
    # fandom/同人/电影/电视周边（fans-only，非主流热点）
    "lotrmemes", "lotr", "marvelmemes", "marvelstudios", "DC_Cinematic",
    "shittymoviedetails", "moviescirclejerk", "shittyaskhistory",
    "GenV", "TheBoys", "starwars", "starwarsmemes", "harrypotter",
    "PrequelMemes", "SequelMemes", "OriginalMemes",
    "anime", "AnimeART", "manga",
    "comics", "comicbooks", "DCcomics", "Marvel",
    # 艺术/手作
    "Art", "drawing", "Painting", "sketches", "ArtTutorials",
    # 体育（全部 source-sub，避免漏过）
    "nba", "NBA", "NBASpurs", "NYKnicks", "lakers", "warriors",
    "nfl", "NFL", "denverbroncos", "eagles", "cowboys", "Patriots",
    "NHL", "hockey", "DenverNuggets",
    "MLB", "baseball", "yankees", "dodgers",
    "soccer", "football", "formula1", "F1Technical",
    "golf", "tennis", "ufc", "mma", "boxing",
    "FantasyHockey", "fantasyfootball", "DynastyFF",
    "collegebasketball", "CFB", "CollegeBasketball",
    # 其他
    "BuyFromEU", "shittyrobots", "SubredditDrama", "OutOfTheLoop_Drama",
    "HilariousAffronts", "mildlyfunny",
    # v3 补：第二轮测试发现的漏过 sub
    "nostalgia", "Unexpected", "countwithchickenlady", "lovethissmug",
    "Fauxmoi",  # 名人八卦，娱乐性
    # 个人作品/手作 sub
    "lego", "sewing", "crochet", "knitting", "Embroidery", "woodworking",
    "DIY", "Baking", "Cooking", "carpentry", "metalworking",
    "PenmanshipPorn", "calligraphy",
    # 动画/漫画扩展
    "anime_irl", "Animemes", "manhwa", "OnePiece", "AttackOnTitan",
    "TheLastAirbender", "AvatarMemes",
    # 游戏扩展
    "Warframe", "Genshin_Impact", "leagueoflegends", "DotA2",
    "Minecraft", "Terraria", "FortNiteBR", "apexlegends",
    "EldenRing", "Fallout", "Skyrim", "stardewvalley",
    # 地方/城市（噪声大）
    "jaipur", "mumbai", "delhi", "bangalore", "india",
    "AskUK", "AskAnAmerican", "AskEurope",
    # 电视/电影 fandom 补漏
    "DunderMifflin", "Seinfeld", "BetterCallSaul", "BreakingBad",
    "GameOfThrones", "HouseOfTheDragon", "RingsOfPower", "WheelOfTime",
    "Stranger_Things", "TheOffice", "PeakyBlinders",
}

# 闸门 2d：flair 关键词排除
EXCLUDE_FLAIR = [
    "DOGGO", "Wholesome", "Cute", "Funny", "Made Me Smile",
    "Animal", "Pet", "Cat", "Dog", "Puppy", "Kitten",
    "Shitpost", "Meme",
]

# 闸门 3：注意力阈值（按 sub 调）
THRESHOLDS = {
    # 核心金矿（量少质高，阈值偏低）
    "OutOfTheLoop": {"ups": 100, "comments": 15},
    # niche 科技 sub（顶帖天花板低）
    "artificial": {"ups": 20, "comments": 10},
    "OpenAI": {"ups": 100, "comments": 30},
    # 冷门兜底（保留但调低）
    "popculture": {"ups": 30, "comments": 15},
    "30PlusSkinCare": {"ups": 30, "comments": 15},
    "femalefashion": {"ups": 30, "comments": 15},
    "streetweardiscussion": {"ups": 30, "comments": 15},
    "biohackers": {"ups": 50, "comments": 20},
    "loseit": {"ups": 100, "comments": 50},  # 个人帖多，阈值提高
    # 默认（适用 popular / news / technology / movies / television / AsianBeauty / Sephora）
    "DEFAULT": {"ups": 200, "comments": 50},
}

# 去重默认配置
DEFAULT_HISTORY_PATH = "~/.config/ops-skills/us-trend-history.json"
HISTORY_DAYS = 7
JACCARD_THRESHOLD = 0.6  # 标题相似度 > 此值即视为重复

# ─── 拉取层 ────────────────────────────────────────────────────────────────


def http_get(url: str, accept_xml: bool = False) -> bytes:
    """带 UA 的 HTTP GET，失败抛异常。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml" if accept_xml else "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()


def fetch_sub(sub: str, limit: int = DEFAULT_LIMIT) -> tuple[str, list[dict[str, Any]], str | None]:
    """拉单个 sub 的 24h top。返回 (sub, posts, error_msg)。"""
    url = f"{REDDIT_BASE}/r/{sub}/top.json?t=day&limit={limit}"
    try:
        body = http_get(url)
        data = json.loads(body)
        if "error" in data:
            return sub, [], f"API error: {data.get('message', data.get('error'))}"
        posts = data.get("data", {}).get("children", [])
        return sub, posts, None
    except urllib.error.HTTPError as e:
        return sub, [], f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return sub, [], f"URL error: {e.reason}"
    except json.JSONDecodeError:
        return sub, [], "JSON parse fail (sub may be private)"
    except Exception as e:
        return sub, [], f"unexpected: {type(e).__name__}: {e}"


def fetch_all_subs(subs: list[str]) -> dict[str, Any]:
    """并发拉所有 sub。返回 {sub: {posts, error}}。"""
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        futures = {ex.submit(fetch_sub, s): s for s in subs}
        for fut in as_completed(futures):
            sub, posts, err = fut.result()
            results[sub] = {"posts": posts, "error": err}
    return results


def fetch_google_trends() -> tuple[list[dict[str, Any]], str | None]:
    """拉 Google Trends Realtime US RSS（侧路 cross-check 用）。"""
    try:
        body = http_get(TRENDS_RSS, accept_xml=True)
        root = ET.fromstring(body)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            traffic_el = item.find("ht:approx_traffic", ns)
            traffic = traffic_el.text if traffic_el is not None else "N/A"
            news_titles = [
                (n.findtext("ht:news_item_title", default="", namespaces=ns) or "").strip()
                for n in item.findall("ht:news_item", ns)[:2]
            ]
            items.append({
                "term": title,
                "traffic": traffic,
                "pub_date": pub_date,
                "news_titles": news_titles,
            })
        return items, None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


# ─── 过滤层 ────────────────────────────────────────────────────────────────


def extract_source_sub(permalink: str, url: str) -> str:
    """从 permalink / url 解析 source subreddit（区分大小写敏感问题，统一小写比对）。"""
    for s in (permalink, url):
        m = re.search(r"/r/([A-Za-z0-9_]+)/", s)
        if m:
            return m.group(1)
    return ""


def filter_post(post: dict[str, Any], fetched_from: str, now_ts: float) -> tuple[bool, str | None]:
    """三层闸门。返回 (是否通过, drop 原因)。"""
    d = post.get("data", {}) or {}
    title = (d.get("title") or "")
    tl = title.lower()
    ups = int(d.get("ups") or 0)
    comments = int(d.get("num_comments") or 0)
    created = float(d.get("created") or 0)
    age_h = (now_ts - created) / 3600 if created else 999
    source_sub = extract_source_sub(d.get("permalink", ""), d.get("url", ""))
    flair = (d.get("link_flair_text") or "").strip()

    # 闸门 1：24h 硬过滤
    if age_h > MAX_AGE_HOURS:
        return False, f"age {age_h:.1f}h > {MAX_AGE_HOURS}h"
    # 排除 stickied / NSFW
    if d.get("stickied"):
        return False, "stickied"
    if d.get("over_18"):
        return False, "NSFW"

    # 闸门 2a/b：title 关键词
    for kw in EXCLUDE_TOPIC:
        if kw in tl:
            return False, f"topic kw '{kw}'"
    for kw in EXCLUDE_FORM:
        if kw in tl:
            return False, f"form kw '{kw}'"

    # 闸门 2c：source sub 黑名单（针对 popular/news 的 crosspost）
    if source_sub and source_sub != fetched_from:
        # 这是 crosspost，检查源 sub 是否在黑名单
        if source_sub.lower() in {s.lower() for s in EXCLUDE_SOURCE_SUB}:
            return False, f"src sub '{source_sub}' in exclude list"

    # 闸门 2d：flair 黑名单
    if flair:
        flair_lower = flair.lower()
        for kw in EXCLUDE_FLAIR:
            if kw.lower() in flair_lower:
                return False, f"flair '{flair}' matches '{kw}'"

    # 闸门 3：阈值
    threshold = THRESHOLDS.get(fetched_from, THRESHOLDS["DEFAULT"])
    if ups < threshold["ups"]:
        return False, f"ups {ups} < {threshold['ups']}"
    if comments < threshold["comments"]:
        return False, f"comments {comments} < {threshold['comments']}"

    return True, None


def normalize_post(post: dict[str, Any], fetched_from: str, now_ts: float) -> dict[str, Any]:
    """提取候选需要的字段（结构化输出给 Claude）。"""
    d = post.get("data", {}) or {}
    return {
        "title": d.get("title") or "",
        "ups": int(d.get("ups") or 0),
        "comments": int(d.get("num_comments") or 0),
        "age_h": round((now_ts - float(d.get("created") or 0)) / 3600, 1),
        "permalink": f"https://reddit.com{d.get('permalink', '')}",
        "url": d.get("url") or "",
        "fetched_from": fetched_from,
        "source_sub": extract_source_sub(d.get("permalink", ""), d.get("url", "")),
        "flair": (d.get("link_flair_text") or "").strip(),
        "selftext": (d.get("selftext") or "")[:600],
        "upvote_ratio": d.get("upvote_ratio"),
    }


# ─── 去重层 ────────────────────────────────────────────────────────────────


def fingerprint(post: dict[str, Any]) -> dict[str, Any]:
    """生成帖子指纹（标题归一化 + permalink）。"""
    title = post["title"].lower()
    title_norm = re.sub(r"[^\w\s]", " ", title)
    title_norm = " ".join(title_norm.split())[:120]
    return {
        "title_norm": title_norm,
        "permalink": post["permalink"],
    }


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def load_history(path: Path) -> list[dict[str, Any]]:
    """读 7 天内的历史指纹。"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    cutoff = time.time() - HISTORY_DAYS * 86400
    return [item for item in data if item.get("ts", 0) > cutoff]


def is_dup(post: dict[str, Any], history: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """跟历史比对。返回 (是否重复, 命中描述)。"""
    fp = fingerprint(post)
    for h in history:
        if fp["permalink"] == h.get("permalink"):
            return True, f"same permalink {h['permalink']}"
        sim = jaccard(fp["title_norm"], h.get("title_norm", ""))
        if sim >= JACCARD_THRESHOLD:
            ts_str = datetime.fromtimestamp(h.get("ts", 0), tz=timezone.utc).strftime("%Y-%m-%d")
            return True, f"jaccard {sim:.2f} vs {ts_str}: {h.get('title_norm', '')[:60]}"
    return False, None


def save_history(passed: list[dict[str, Any]], history: list[dict[str, Any]], path: Path) -> None:
    """把新通过的帖子加入历史，写回文件。"""
    now = time.time()
    new_records = []
    for p in passed:
        fp = fingerprint(p)
        fp["ts"] = now
        new_records.append(fp)
    all_records = history + new_records
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_records, indent=2, ensure_ascii=False))


# ─── 主流程 ────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--output", default="candidates.json", help="输出 JSON 路径（默认 candidates.json）")
    parser.add_argument("--history", default=DEFAULT_HISTORY_PATH, help="7 天去重历史文件路径")
    parser.add_argument("--no-dedupe", action="store_true", help="跳过去重（首次跑或调试用）")
    parser.add_argument("--no-trends", action="store_true", help="跳过 Google Trends 拉取")
    parser.add_argument("--verbose", action="store_true", help="打印每条 drop 原因（调试用）")
    args = parser.parse_args()

    now = time.time()
    history_path = Path(args.history).expanduser()

    print(f"[scout] fetching {len(SUBS)} subs (limit={DEFAULT_LIMIT}, workers={FETCH_WORKERS})…", file=sys.stderr)
    sub_results = fetch_all_subs(SUBS)

    trends, trends_err = ([], None)
    if not args.no_trends:
        print("[scout] fetching Google Trends RSS…", file=sys.stderr)
        trends, trends_err = fetch_google_trends()

    # 过滤 + 归一化
    candidates: list[dict[str, Any]] = []
    drop_reasons: dict[str, int] = {}
    per_sub_stats: dict[str, dict[str, int]] = {}

    for sub, res in sub_results.items():
        raw = res["posts"]
        if res["error"]:
            per_sub_stats[sub] = {"raw": 0, "passed": 0, "error": res["error"]}
            continue
        passed_n = 0
        for p in raw:
            ok, reason = filter_post(p, sub, now)
            if ok:
                candidates.append(normalize_post(p, sub, now))
                passed_n += 1
            elif args.verbose and reason:
                drop_reasons[reason.split()[0]] = drop_reasons.get(reason.split()[0], 0) + 1
        per_sub_stats[sub] = {"raw": len(raw), "passed": passed_n}

    pre_dedup_n = len(candidates)

    # 同跑内去重（同一条 crosspost 到多个 sub 只保留一次，按 ups 高的留）
    seen_permalinks: dict[str, dict[str, Any]] = {}
    for c in candidates:
        pl = c["permalink"]
        if pl not in seen_permalinks or c["ups"] > seen_permalinks[pl]["ups"]:
            seen_permalinks[pl] = c
    intra_dedup_dropped = len(candidates) - len(seen_permalinks)
    candidates = list(seen_permalinks.values())

    # 跨天历史去重
    history: list[dict[str, Any]] = []
    history_deduped = 0
    if not args.no_dedupe:
        history = load_history(history_path)
        kept = []
        for c in candidates:
            dup, why = is_dup(c, history)
            if dup:
                history_deduped += 1
                if args.verbose:
                    print(f"[dedupe] DROP {c['title'][:60]} — {why}", file=sys.stderr)
            else:
                kept.append(c)
        candidates = kept
    deduped_count = intra_dedup_dropped + history_deduped

    # 排序：upvote desc
    candidates.sort(key=lambda x: -x["ups"])

    # 输出
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "subs_attempted": len(SUBS),
            "subs_succeeded": sum(1 for s in per_sub_stats.values() if not s.get("error")),
            "total_raw_posts": sum(s["raw"] for s in per_sub_stats.values()),
            "passed_filter": pre_dedup_n,
            "intra_dedup_dropped": intra_dedup_dropped,
            "history_deduped": history_deduped,
            "final_candidates": len(candidates),
            "trends_items": len(trends),
            "trends_error": trends_err,
        },
        "per_sub": per_sub_stats,
        "candidates": candidates,
        "google_trends": trends,
    }
    Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False))

    # 保存历史
    if not args.no_dedupe:
        save_history(candidates, history, history_path)

    # 简洁报告到 stderr
    print(f"[scout] done: {pre_dedup_n} passed filter → {deduped_count} deduped → {len(candidates)} final → {args.output}", file=sys.stderr)
    print(f"[scout] per-sub: " + " ".join(f"r/{s}:{st['passed']}/{st['raw']}" for s, st in sorted(per_sub_stats.items())), file=sys.stderr)
    if trends_err:
        print(f"[scout] trends error: {trends_err}", file=sys.stderr)
    if args.verbose and drop_reasons:
        print(f"[scout] drop reasons: {drop_reasons}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
