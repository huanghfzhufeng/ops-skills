"""tk-template-scout/scout_strict.py 纯函数单测。

测无 I/O 的工具函数：
- keyword_to_hashtag — 'old money outfit' → 'oldmoneyoutfit'
- check_cookies_have_session — 检查 sessionid 是否在 cookies 里
- cross_persona_dedup — 同视频归给候选最少的 persona
- build_report — Top N + low_heat_warning 标注

Playwright 流程（async）和 yt-dlp 子进程不在单测覆盖（需要 mock + chromium 装机，
归 integration 测试范围）。
"""
import time

import pytest

import scout_strict

pytestmark = pytest.mark.unit


# ---------- keyword_to_hashtag ----------


class TestKeywordToHashtag:
    def test_basic_space_removal(self) -> None:
        assert scout_strict.keyword_to_hashtag("old money outfit") == "oldmoneyoutfit"

    def test_lowercases(self) -> None:
        assert scout_strict.keyword_to_hashtag("Old Money Outfit") == "oldmoneyoutfit"
        assert scout_strict.keyword_to_hashtag("NYC IT GIRL") == "nycitgirl"

    def test_strips_punctuation(self) -> None:
        assert scout_strict.keyword_to_hashtag("PR girl life!") == "prgirllife"
        assert scout_strict.keyword_to_hashtag("data-science") == "datascience"
        assert scout_strict.keyword_to_hashtag("hot.take.tech") == "hottaketech"

    def test_keeps_digits(self) -> None:
        assert scout_strict.keyword_to_hashtag("2026 trends") == "2026trends"

    def test_strips_emoji_and_unicode(self) -> None:
        assert scout_strict.keyword_to_hashtag("café latte 🍵") == "caflatte"

    def test_empty_input(self) -> None:
        assert scout_strict.keyword_to_hashtag("") == ""
        assert scout_strict.keyword_to_hashtag("   ") == ""


# ---------- check_cookies_have_session ----------


class TestCheckCookiesHaveSession:
    def test_has_sessionid_on_tiktok(self) -> None:
        cookies = [
            {"name": "sessionid", "value": "x" * 32, "domain": ".tiktok.com"},
            {"name": "ttwid", "value": "y", "domain": ".tiktok.com"},
        ]
        assert scout_strict.check_cookies_have_session(cookies) is True

    def test_only_anonymous_cookies(self) -> None:
        cookies = [
            {"name": "ttwid", "value": "y", "domain": ".tiktok.com"},
            {"name": "msToken", "value": "z", "domain": ".tiktok.com"},
        ]
        assert scout_strict.check_cookies_have_session(cookies) is False

    def test_sessionid_on_other_domain_doesnt_count(self) -> None:
        # douyin / instagram / 别的网站也叫 sessionid
        cookies = [
            {"name": "sessionid", "value": "x", "domain": ".douyin.com"},
            {"name": "sessionid", "value": "y", "domain": ".instagram.com"},
            {"name": "ttwid", "value": "z", "domain": ".tiktok.com"},
        ]
        assert scout_strict.check_cookies_have_session(cookies) is False

    def test_empty_cookies(self) -> None:
        assert scout_strict.check_cookies_have_session([]) is False


# ---------- cross_persona_dedup ----------


class TestCrossPersonaDedup:
    def _make(self, persona: str, video_id: str, ts_offset: int = 0) -> scout_strict.VideoCandidate:
        return scout_strict.VideoCandidate(
            persona=persona,
            keyword="dummy",
            source="hashtag",
            url=f"https://www.tiktok.com/@u/video/{video_id}",
            video_id=video_id,
            timestamp=1_780_000_000 + ts_offset,
            age_hours=1.0,
        )

    def test_no_conflict_no_change(self) -> None:
        by_persona = {
            "sophie": [self._make("sophie", "1"), self._make("sophie", "2")],
            "ava": [self._make("ava", "3")],
        }
        deduped, conflicts = scout_strict.cross_persona_dedup(by_persona)
        assert conflicts == 0
        assert {p: [c.video_id for c in cs] for p, cs in deduped.items()} == {
            "sophie": ["1", "2"], "ava": ["3"],
        }

    def test_shared_video_goes_to_smallest_persona(self) -> None:
        # ryan 3 候选, avery 1 候选, joey 2 候选；共享 video_id=100 → 归 avery
        by_persona = {
            "ryan": [self._make("ryan", "100"), self._make("ryan", "r1"), self._make("ryan", "r2")],
            "avery": [self._make("avery", "100")],
            "joey": [self._make("joey", "100"), self._make("joey", "j1")],
        }
        deduped, conflicts = scout_strict.cross_persona_dedup(by_persona)
        assert conflicts == 1
        owners = {
            p: sorted(c.video_id for c in cs) for p, cs in deduped.items()
        }
        assert owners["avery"] == ["100"]  # 拿到了
        assert "100" not in owners["ryan"]
        assert "100" not in owners["joey"]
        assert owners["ryan"] == ["r1", "r2"]
        assert owners["joey"] == ["j1"]

    def test_tiebreak_alphabetical(self) -> None:
        # ava 和 ezra 候选数一样（都 1），共享视频 → 字母序 ava 拿
        by_persona = {
            "ava": [self._make("ava", "shared")],
            "ezra": [self._make("ezra", "shared")],
        }
        deduped, conflicts = scout_strict.cross_persona_dedup(by_persona)
        assert conflicts == 1
        assert [c.video_id for c in deduped["ava"]] == ["shared"]
        assert [c.video_id for c in deduped["ezra"]] == []

    def test_three_way_conflict(self) -> None:
        # 三人都共享，归候选最少的
        by_persona = {
            "a": [self._make("a", "shared"), self._make("a", "a1")],
            "b": [self._make("b", "shared")],
            "c": [self._make("c", "shared"), self._make("c", "c1"), self._make("c", "c2")],
        }
        deduped, conflicts = scout_strict.cross_persona_dedup(by_persona)
        assert conflicts == 1
        assert [c.video_id for c in deduped["b"]] == ["shared"]
        assert "shared" not in [c.video_id for c in deduped["a"]]
        assert "shared" not in [c.video_id for c in deduped["c"]]


# ---------- build_report ----------


class TestBuildReport:
    def _rec(self, like_count: int, url: str = "https://x") -> scout_strict.VideoRecord:
        return scout_strict.VideoRecord(
            url=url, title="t", uploader="u",
            like_count=like_count, view_count=like_count * 10,
            comment_count=0, timestamp=1_780_000_000, source="hashtag",
        )

    def _cand(self, video_id: str) -> scout_strict.VideoCandidate:
        return scout_strict.VideoCandidate(
            persona="p", keyword="k", source="hashtag",
            url=f"https://www.tiktok.com/@u/video/{video_id}",
            video_id=video_id, timestamp=1_780_000_000, age_hours=1.0,
        )

    def test_picks_top_n_by_likes(self) -> None:
        cands = {"sophie": [self._cand("1"), self._cand("2"), self._cand("3"), self._cand("4")]}
        recs = {"sophie": [self._rec(100), self._rec(500), self._rec(200), self._rec(50)]}
        report = scout_strict.build_report(
            cands, recs, top_n=3, min_likes_warn_threshold=500,
            tight_max=999, relaxed_max=999,
        )
        likes = [v["like_count"] for v in report["sophie"]["videos"]]
        assert likes == [500, 200, 100]
        assert report["sophie"]["max_likes"] == 500
        # 500 不严格小于 500，所以 low_heat 为 False
        assert report["sophie"]["low_heat_warning"] is False

    def test_low_heat_warning_when_top1_below_threshold(self) -> None:
        cands = {"silver": [self._cand("1")]}
        recs = {"silver": [self._rec(200)]}
        report = scout_strict.build_report(
            cands, recs, top_n=3, min_likes_warn_threshold=500,
            tight_max=999, relaxed_max=999,
        )
        assert report["silver"]["max_likes"] == 200
        assert report["silver"]["low_heat_warning"] is True

    def test_persona_with_no_records_still_listed(self) -> None:
        # silver 有候选但 yt-dlp 一条没成功
        cands = {"silver": [self._cand("1"), self._cand("2")]}
        recs: dict[str, list[scout_strict.VideoRecord]] = {}  # 空
        report = scout_strict.build_report(
            cands, recs, top_n=3, min_likes_warn_threshold=500,
            tight_max=999, relaxed_max=999,
        )
        assert "silver" in report
        assert report["silver"]["videos"] == []
        assert report["silver"]["candidates_total"] == 2
        assert report["silver"]["fetched_count"] == 0
        assert report["silver"]["max_likes"] == 0
        assert report["silver"]["low_heat_warning"] is True

    def test_top_n_respected_when_more_records(self) -> None:
        cands = {"x": [self._cand(str(i)) for i in range(10)]}
        recs = {"x": [self._rec(i * 100) for i in range(10)]}
        report = scout_strict.build_report(
            cands, recs, top_n=3, min_likes_warn_threshold=0,
            tight_max=999, relaxed_max=999,
        )
        assert len(report["x"]["videos"]) == 3
        assert [v["like_count"] for v in report["x"]["videos"]] == [900, 800, 700]


# ---------- load_netscape_cookies ----------


class TestLoadNetscapeCookies:
    def test_basic_parse(self, tmp_path) -> None:
        f = tmp_path / "cookies.txt"
        f.write_text(
            "# Netscape HTTP Cookie File\n"
            "# comment line\n"
            "\n"
            ".tiktok.com\tTRUE\t/\tTRUE\t1900000000\tsessionid\tabc123\n"
            ".tiktok.com\tTRUE\t/\tFALSE\t0\tttwid\txyz\n"
        )
        cookies = scout_strict.load_netscape_cookies(f)
        assert len(cookies) == 2
        assert cookies[0]["name"] == "sessionid"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["secure"] is True
        assert cookies[0]["expires"] == 1900000000
        assert cookies[1]["expires"] == -1  # 0 → -1 (session cookie)
        assert cookies[1]["secure"] is False

    def test_clamps_huge_expiry(self, tmp_path) -> None:
        f = tmp_path / "cookies.txt"
        # Chrome 的 cookies 有时 expiry 是 13xxxxxxxxxxxxx（webkit 时间）
        f.write_text(
            ".tiktok.com\tTRUE\t/\tTRUE\t13446126504000000\tdelay_guest_mode_vid\t8\n"
        )
        cookies = scout_strict.load_netscape_cookies(f)
        assert cookies[0]["expires"] == -1  # 超出阈值 → -1

    def test_handles_short_lines_gracefully(self, tmp_path) -> None:
        f = tmp_path / "cookies.txt"
        f.write_text(
            "broken\tline\n"
            ".tiktok.com\tTRUE\t/\tTRUE\t1900000000\tsessionid\tabc\n"
        )
        cookies = scout_strict.load_netscape_cookies(f)
        assert len(cookies) == 1
        assert cookies[0]["name"] == "sessionid"


# ---------- build_urls（双源融合）----------


class TestBuildUrls:
    def test_search_mode_only_search_url(self) -> None:
        urls = scout_strict.build_urls("high fashion", "highfashion", "search")
        assert len(urls) == 1
        src, u = urls[0]
        assert src == "search"
        assert "search/video?q=high%20fashion" in u
        assert "publish_time=1" in u
        assert "sort_type=2" in u

    def test_hashtag_mode_only_hashtag_url(self) -> None:
        urls = scout_strict.build_urls("high fashion", "highfashion", "hashtag")
        assert len(urls) == 1
        src, u = urls[0]
        assert src == "hashtag"
        assert u == "https://www.tiktok.com/tag/highfashion"

    def test_both_mode_returns_two_urls(self) -> None:
        urls = scout_strict.build_urls("high fashion", "highfashion", "both")
        assert len(urls) == 2
        sources = {s for s, _ in urls}
        assert sources == {"search", "hashtag"}

    def test_invalid_source_raises(self) -> None:
        import pytest as _pytest
        with _pytest.raises(ValueError):
            scout_strict.build_urls("x", "x", "bogus")

    def test_keyword_space_encoded_only_in_search(self) -> None:
        urls = dict(scout_strict.build_urls("data science life", "datasciencelife", "both"))
        assert "data%20science%20life" in urls["search"]
        assert urls["hashtag"].endswith("/tag/datasciencelife")


# ---------- ID 解码（snowflake 假设） ----------


class TestIDDecodingMath:
    """直接测 `timestamp = video_id >> 32` 的边界，没走 Playwright/yt-dlp。"""

    def test_known_video_id_decodes_to_expected_year(self) -> None:
        # 实测样本：sophie 的 noahaltink 视频 ID 7474676890679201046 → 2025-02-24
        vid = 7474676890679201046
        ts = vid >> 32
        # 2025-02-24 00:00 UTC = 1740355200，给宽松一点
        assert 1_740_000_000 < ts < 1_741_000_000

    def test_higher_id_means_newer(self) -> None:
        old_id = 7474676890679201046  # 2025-02
        new_id = 7641531551506763029  # 2026-05
        assert (new_id >> 32) > (old_id >> 32)
