#!/usr/bin/env python3
"""
us-trend-scout / scout_reddit.py  (v5.3 — RSS 端点)

拉 16 个精选 Reddit sub 的 24h top RSS → 两层闸门过滤 → 7 天去重 → 输出 candidates.json

为什么是 RSS（v5.3 改动，critical）：
    Reddit 已封 .json 端点（无 OAuth 一律 HTTP 403，换浏览器 UA / old.reddit.com 均无效）。
    唯一零配置可达的是 RSS（/r/<sub>/top/.rss?t=day，任何 UA 都能过）。
    代价：RSS 没有 ups / num_comments。热度信号改用 RSS feed 内排名（rank 字段，
    feed 本身按 24h 热度排序，#1 即当日该 sub 最热）。
    RSS 也有滑动窗口限流 → 并发降到 3 + 失败重试，避免批量 403。

第一层信源（脚本）：Reddit RSS + Google Trends RSS（侧路）
第二层评估（Claude 在 SKILL.md 里）：每条候选 3 yes 定性判断 + 可选 WebSearch 跨平台 cross-check

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
DEFAULT_LIMIT = 25  # RSS 单 feed 上限（Reddit RSS 固定 ~25，与 .json 的 100 不同）
MAX_CANDIDATES = 120  # 候选池上限：RSS 无 ups/comments，按 rank 排序后取前 N 给 Claude，砍各大 sub 长尾
FETCH_TIMEOUT = 15
FETCH_WORKERS = 3  # 并发数（RSS 限流敏感，v5.3 从 8 降到 3）
FETCH_RETRIES = 2  # 单 sub 失败重试次数（403/429/网络抖动）
RETRY_BACKOFF = 3  # 重试退避基数秒（第 n 次等 n*RETRY_BACKOFF）

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# 精选 sub（按测试结果调整）
SUBS = [
    # 核心：文化引爆点金矿
    "OutOfTheLoop",
    # 美妆
    "AsianBeauty", "Sephora", "30PlusSkinCare",
    # 时尚
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

# ─── 闸门规则 ──────────────────────────────────────────────────────────────
# 注意（v5.3）：原"闸门 3 注意力阈值（ups/comments）"已删除 —— RSS 无此数据。
# 热度由 RSS feed 排名（rank）隐含表达：能上某 sub 24h top RSS 即足够热。

# 闸门 1：24h 硬窗口（由代码强制，用 RSS published 时间戳）
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

# 闸门 2c：source-subreddit 黑名单（RSS 的 <category term="..."> 给出真实来源 sub，
# 含 r/popular 聚合进来的 crosspost 原 sub —— 已实测可用）
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
_EXCLUDE_SOURCE_SUB_LOWER = {s.lower() for s in EXCLUDE_SOURCE_SUB}

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
            "Accept": "application/rss+xml" if accept_xml else "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()


def parse_content(content_html: str, permalink: str) -> tuple[str, str]:
    """从 RSS <content> 的 HTML 里提取（外链 url, 正文文本）。

    link post：content 含指向站外的 [link] href → 取为 url。
    self post：无站外链接 → url 回落到 permalink。
    正文：去 HTML 标签 + 实体 + Reddit RSS 固定噪声（submitted by / [link] / [comments]）。
    """
    external = ""
    for u in re.findall(r'href="([^"]+)"', content_html):
        if "reddit.com" in u or "redd.it" in u:
            continue
        external = u
        break
    text = re.sub(r"<[^>]+>", " ", content_html)
    text = re.sub(r"&#?\w+;", " ", text)
    text = re.sub(r"submitted by\s+/u/\S+", "", text)
    text = text.replace("[link]", "").replace("[comments]", "")
    text = " ".join(text.split())
    return (external or permalink), text[:600]


def parse_atom(body: bytes, fetched_from: str) -> list[dict[str, Any]]:
    """解析单个 sub 的 Atom RSS，返回 entry dict 列表（含 feed 内 rank）。"""
    root = ET.fromstring(body)
    entries: list[dict[str, Any]] = []
    for idx, e in enumerate(root.findall("a:entry", ATOM_NS), start=1):
        title = (e.findtext("a:title", "", ATOM_NS) or "").strip()
        link_el = e.find("a:link", ATOM_NS)
        permalink = link_el.attrib.get("href", "") if link_el is not None else ""
        published = (e.findtext("a:published", "", ATOM_NS) or "").strip()
        post_id = (e.findtext("a:id", "", ATOM_NS) or "").strip()  # t3_xxx
        cat_el = e.find("a:category", ATOM_NS)
        source_sub = cat_el.attrib.get("term", "") if cat_el is not None else fetched_from
        content_el = e.find("a:content", ATOM_NS)
        content_html = (content_el.text or "") if content_el is not None else ""
        try:
            created_ts = datetime.fromisoformat(published).timestamp() if published else 0.0
        except ValueError:
            created_ts = 0.0
        entries.append({
            "title": title,
            "permalink": permalink,
            "created_ts": created_ts,
            "post_id": post_id,
            "source_sub": source_sub or fetched_from,
            "content_html": content_html,
            "rank": idx,
            "fetched_from": fetched_from,
        })
    return entries


def fetch_sub(sub: str, limit: int = DEFAULT_LIMIT) -> tuple[str, list[dict[str, Any]], str | None]:
    """拉单个 sub 的 24h top RSS，带重试。返回 (sub, entries, error_msg)。"""
    url = f"{REDDIT_BASE}/r/{sub}/top/.rss?t=day&limit={limit}"
    last_err = "unknown"
    for attempt in range(FETCH_RETRIES + 1):
        try:
            body = http_get(url, accept_xml=True)
            return sub, parse_atom(body, sub), None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (403, 429, 500, 502, 503) and attempt < FETCH_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            return sub, [], last_err
        except urllib.error.URLError as e:
            last_err = f"URL error: {e.reason}"
            if attempt < FETCH_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            return sub, [], last_err
        except ET.ParseError as e:
            return sub, [], f"XML parse fail: {e}"
        except Exception as e:
            return sub, [], f"unexpected: {type(e).__name__}: {e}"
    return sub, [], last_err


def fetch_all_subs(subs: list[str]) -> dict[str, Any]:
    """并发拉所有 sub 的 RSS。返回 {sub: {entries, error}}。"""
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        futures = {ex.submit(fetch_sub, s): s for s in subs}
        for fut in as_completed(futures):
            sub, entries, err = fut.result()
            results[sub] = {"entries": entries, "error": err}
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


def filter_entry(entry: dict[str, Any], now_ts: float) -> tuple[bool, str | None]:
    """两层闸门（24h + title/source-sub 黑名单）。返回 (是否通过, drop 原因)。"""
    title = entry["title"]
    tl = title.lower()
    created = entry["created_ts"]
    age_h = (now_ts - created) / 3600 if created else 999
    source_sub = entry["source_sub"]

    # 闸门 1：24h 硬过滤
    if age_h > MAX_AGE_HOURS:
        return False, f"age {age_h:.1f}h > {MAX_AGE_HOURS}h"

    # 闸门 2a/b：title 关键词
    for kw in EXCLUDE_TOPIC:
        if kw in tl:
            return False, f"topic kw '{kw}'"
    for kw in EXCLUDE_FORM:
        if kw in tl:
            return False, f"form kw '{kw}'"

    # 闸门 2c：source sub 黑名单（RSS category 给出真实来源 sub）
    if source_sub and source_sub.lower() in _EXCLUDE_SOURCE_SUB_LOWER:
        return False, f"src sub '{source_sub}' in exclude list"

    return True, None


def normalize_entry(entry: dict[str, Any], now_ts: float) -> dict[str, Any]:
    """提取候选需要的字段（结构化输出给 Claude）。"""
    created = entry["created_ts"]
    url, selftext = parse_content(entry["content_html"], entry["permalink"])
    return {
        "title": entry["title"],
        "rank": entry["rank"],  # RSS feed 内 24h top 排名（热度信号，替代 ups/comments）
        "age_h": round((now_ts - created) / 3600, 1) if created else 999.0,
        "permalink": entry["permalink"],
        "url": url,
        "fetched_from": entry["fetched_from"],
        "source_sub": entry["source_sub"],
        "post_id": entry["post_id"],
        "selftext": selftext,
    }


# ─── 去重层 ────────────────────────────────────────────────────────────────


def fingerprint(post: dict[str, Any]) -> dict[str, Any]:
    """生成帖子指纹（标题归一化 + post_id + permalink）。"""
    title = post["title"].lower()
    title_norm = re.sub(r"[^\w\s]", " ", title)
    title_norm = " ".join(title_norm.split())[:120]
    return {
        "title_norm": title_norm,
        "post_id": post.get("post_id", ""),
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
        if fp["post_id"] and fp["post_id"] == h.get("post_id"):
            return True, f"same post_id {fp['post_id']}"
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--output", default="candidates.json", help="输出 JSON 路径（默认 candidates.json）")
    parser.add_argument("--history", default=DEFAULT_HISTORY_PATH, help="7 天去重历史文件路径")
    parser.add_argument("--no-dedupe", action="store_true", help="跳过去重（首次跑或调试用）")
    parser.add_argument("--no-trends", action="store_true", help="跳过 Google Trends 拉取")
    parser.add_argument("--verbose", action="store_true", help="打印每条 drop 原因（调试用）")
    args = parser.parse_args()

    now = time.time()
    history_path = Path(args.history).expanduser()

    print(f"[scout] fetching {len(SUBS)} subs via RSS (limit={DEFAULT_LIMIT}, workers={FETCH_WORKERS}, retries={FETCH_RETRIES})…", file=sys.stderr)
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
        raw = res["entries"]
        if res["error"]:
            per_sub_stats[sub] = {"raw": 0, "passed": 0, "error": res["error"]}
            continue
        passed_n = 0
        for entry in raw:
            ok, reason = filter_entry(entry, now)
            if ok:
                candidates.append(normalize_entry(entry, now))
                passed_n += 1
            elif args.verbose and reason:
                key = reason.split()[0]
                drop_reasons[key] = drop_reasons.get(key, 0) + 1
        per_sub_stats[sub] = {"raw": len(raw), "passed": passed_n}

    pre_dedup_n = len(candidates)

    # 同跑内去重（同一帖被多个 sub 收录，如 popular 聚合，按 post_id/permalink 留一次）
    seen: dict[str, dict[str, Any]] = {}
    for c in candidates:
        key = c["post_id"] or c["permalink"]
        # 保留 rank 更靠前（更热）的那条
        if key not in seen or c["rank"] < seen[key]["rank"]:
            seen[key] = c
    intra_dedup_dropped = len(candidates) - len(seen)
    candidates = list(seen.values())

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

    # 排序：rank 升序（各 sub 头部热帖优先），同 rank 取更新的
    candidates.sort(key=lambda x: (x["rank"], x["age_h"]))

    # 全局收敛：取按 rank 排序后的前 N 条（砍各大 sub 长尾，垂类小 sub 头部因 rank 小自然保留）
    pre_cap_n = len(candidates)
    cap_dropped = max(0, pre_cap_n - MAX_CANDIDATES)
    candidates = candidates[:MAX_CANDIDATES]

    # 输出
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "reddit RSS (/top/.rss?t=day) — .json 端点已被 Reddit 封禁",
        "heat_signal": "rank = RSS feed 内 24h top 排名（越小越热）；RSS 无 ups/comments",
        "stats": {
            "subs_attempted": len(SUBS),
            "subs_succeeded": sum(1 for s in per_sub_stats.values() if not s.get("error")),
            "total_raw_posts": sum(s["raw"] for s in per_sub_stats.values()),
            "passed_filter": pre_dedup_n,
            "intra_dedup_dropped": intra_dedup_dropped,
            "history_deduped": history_deduped,
            "cap_dropped": cap_dropped,
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
    print("[scout] per-sub: " + " ".join(
        f"r/{s}:{st['passed']}/{st['raw']}" + ("!" if st.get("error") else "")
        for s, st in sorted(per_sub_stats.items())), file=sys.stderr)
    errored = {s: st["error"] for s, st in per_sub_stats.items() if st.get("error")}
    if errored:
        print(f"[scout] sub errors: {errored}", file=sys.stderr)
    if trends_err:
        print(f"[scout] trends error: {trends_err}", file=sys.stderr)
    if args.verbose and drop_reasons:
        print(f"[scout] drop reasons: {drop_reasons}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
