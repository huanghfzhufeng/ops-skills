"""tk-niche-scout/tk_lib.py 纯函数单测。

覆盖：compile_niche / handle_kick_reason / caption_kick_reason / is_hard_ad
     / hard_valid / strip_dup_urls / bucket_of / row_sort_key
Playwright 收割与 yt-dlp 子进程不在单测范围（同 tk-template-scout 约定）。
"""
import pytest

import tk_lib

pytestmark = pytest.mark.unit


def make_cfg(**overrides):
    """最小可用 niche 配置（comedy 风格），按需覆盖。"""
    raw = {
        "niche": "testniche",
        "queries_stream1": ["q"], "queries_stream2": ["q"],
        "caption_pos": ["funny", "comedy", "skit", "😂"],
        "caption_neg": ["makeup", "recipe", "booktok"],
        "handle_pos": ["comed", "funny", "skit"],
        "handle_neg": ["beauty", "makeup", "kitchen"],
        "handle_neg_patterns": [r"(^|[^c])hair"],
        "blacklist": ["badguy"],
    }
    raw.update(overrides)
    return tk_lib.compile_niche(raw)


# ---------- compile_niche ----------


class TestCompileNiche:
    def test_defaults(self) -> None:
        cfg = make_cfg()
        assert cfg["ugc_follower_cap"] == 500_000
        assert cfg["pet_filter"] is True
        assert cfg["ad_filter"] is False
        assert cfg["strict_zero_pos"] is False

    def test_regex_compiled(self) -> None:
        cfg = make_cfg()
        assert cfg["caption_pos_re"].search("This is FUNNY stuff")
        assert cfg["caption_neg_re"].search("my makeup routine")

    def test_blacklist_lowercased(self) -> None:
        cfg = make_cfg(blacklist=["BadGuy"])
        assert "badguy" in cfg["blacklist"]


# ---------- handle_kick_reason ----------


class TestHandleKick:
    def test_blacklist(self) -> None:
        assert tk_lib.handle_kick_reason("badguy", make_cfg()) == "人工黑名单"

    def test_region_suffix(self) -> None:
        assert tk_lib.handle_kick_reason("hairsalon.de", make_cfg()) == "非美区后缀"
        assert tk_lib.handle_kick_reason("pinkinc.ph", make_cfg()) == "非美区后缀"

    def test_handle_pos_exempts_neg(self) -> None:
        # 名字带本赛道正信号 → 豁免负名单（comedybeauty 含 beauty 但 comed 优先）
        assert tk_lib.handle_kick_reason("comedybeauty", make_cfg()) is None

    def test_handle_neg_term(self) -> None:
        reason = tk_lib.handle_kick_reason("bestbeautyshop", make_cfg())
        assert reason is not None and "beauty" in reason

    def test_hair_pattern_kicks_but_chair_passes(self) -> None:
        assert tk_lib.handle_kick_reason("hairandstuff", make_cfg()) is not None
        assert tk_lib.handle_kick_reason("wheelchairguy", make_cfg()) is None

    def test_pet_filter(self) -> None:
        assert tk_lib.handle_kick_reason("megs_dogs", make_cfg()) == "宠物号"
        assert tk_lib.handle_kick_reason("megs_dogs", make_cfg(pet_filter=False)) is None

    def test_brand_only_when_ad_filter(self) -> None:
        assert tk_lib.handle_kick_reason("cutestore", make_cfg()) is None
        assert tk_lib.handle_kick_reason(
            "cutestore", make_cfg(ad_filter=True)) == "疑似品牌/带货号"

    def test_clean_handle_passes(self) -> None:
        assert tk_lib.handle_kick_reason("trevorwallace", make_cfg()) is None


# ---------- caption_kick_reason ----------


class TestCaptionKick:
    def test_zero_pos_with_neg_kicks(self) -> None:
        reason = tk_lib.caption_kick_reason(["my makeup haul today"], make_cfg())
        assert reason is not None and "无正信号" in reason

    def test_pos_present_passes(self) -> None:
        assert tk_lib.caption_kick_reason(
            ["funny makeup fail 😂"], make_cfg()) is None

    def test_neg_dominant_kicks(self) -> None:
        caps = ["makeup makeup recipe booktok", "funny"]
        reason = tk_lib.caption_kick_reason(caps, make_cfg())
        assert reason is not None and "负信号占优" in reason

    def test_strict_zero_pos(self) -> None:
        caps = ["nothing here", "plain text", "no signals at all"]
        assert tk_lib.caption_kick_reason(caps, make_cfg()) is None
        reason = tk_lib.caption_kick_reason(caps, make_cfg(strict_zero_pos=True))
        assert reason == "多条且零赛道信号"

    def test_empty_clean_single_caption_passes(self) -> None:
        assert tk_lib.caption_kick_reason(["Times are tough"], make_cfg()) is None


# ---------- is_hard_ad ----------


class TestHardAd:
    @pytest.mark.parametrize("caption", [
        "new drop #ad", "thanks brand #sponsored", "Use my code ZOE20",
        "20% off this week", "link in bio!!", "#paidpartnership with x",
    ])
    def test_ad_hits(self, caption: str) -> None:
        assert tk_lib.is_hard_ad(caption)

    @pytest.mark.parametrize("caption", [
        "made this for fun", "my fav fit today", "adding to cart lol",  # 'ad' 词内不误伤
    ])
    def test_clean_passes(self, caption: str) -> None:
        assert not tk_lib.is_hard_ad(caption)


# ---------- hard_valid / strip_dup_urls ----------


class TestHardValid:
    def test_valid(self) -> None:
        assert tk_lib.hard_valid(
            {"views": 1_000_000, "duration": 15, "upload_date": "20260101"})

    @pytest.mark.parametrize("row", [
        {"views": 999_999, "duration": 10, "upload_date": "20260101"},
        {"views": 2_000_000, "duration": 16, "upload_date": "20260101"},
        {"views": 2_000_000, "duration": 10, "upload_date": "20251231"},
        {"views": 2_000_000, "duration": 0, "upload_date": "20260101"},
    ])
    def test_invalid(self, row: dict) -> None:
        assert not tk_lib.hard_valid(row)


class TestStripDup:
    def test_split(self) -> None:
        rows = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
        kept, dropped = tk_lib.strip_dup_urls(rows, {"b"})
        assert [r["url"] for r in kept] == ["a", "c"]
        assert [r["url"] for r in dropped] == ["b"]

    def test_empty_banned(self) -> None:
        rows = [{"url": "a"}]
        kept, dropped = tk_lib.strip_dup_urls(rows, set())
        assert kept == rows and dropped == []


# ---------- bucket_of / row_sort_key ----------


class TestBucketSort:
    def test_bucket_boundaries(self) -> None:
        assert tk_lib.bucket_of(500_000, 500_000) == "UGC模板"
        assert tk_lib.bucket_of(500_001, 500_000) == "名人/大号"
        assert tk_lib.bucket_of(None, 500_000) == "未知"
        assert tk_lib.bucket_of(0, 500_000) == "未知"

    def test_sort_ugc_first_by_ratio(self) -> None:
        rows = [
            {"bucket": "名人/大号", "ratio": 9999.0, "views": 99_000_000},
            {"bucket": "UGC模板", "ratio": 10.0, "views": 1_000_000},
            {"bucket": "UGC模板", "ratio": 500.0, "views": 2_000_000},
            {"bucket": "未知", "ratio": "", "views": 5_000_000},
        ]
        rows.sort(key=tk_lib.row_sort_key)
        assert [r["bucket"] for r in rows] == ["UGC模板", "UGC模板", "未知", "名人/大号"]
        assert rows[0]["ratio"] == 500.0
