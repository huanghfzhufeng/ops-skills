"""us-trend-scout/scout_reddit.py 纯函数 + 历史持久化单测。

用 importlib 按路径显式加载（scout_reddit.py 名字虽唯一，为与其它 watch.py 测试统一也用 importlib）。
参照 tests/test_analyzer_watch.py 的写法。

网络层（http_get / fetch_sub / fetch_all_subs / fetch_google_trends / main）依赖真打
Reddit RSS + Google Trends，不纯，故不在此覆盖（属 integration，CI 跳过）。
本文件只测两层过滤 / 归一化 / 指纹 / 去重 / atom 解析 / 历史读写等纯函数。
"""
import importlib.util
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCOUT_PY = Path(__file__).parent.parent / "skills" / "us-trend-scout" / "scout_reddit.py"
_spec = importlib.util.spec_from_file_location("scout_reddit_mod", _SCOUT_PY)
scout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scout)

pytestmark = pytest.mark.unit


def _iso_ago(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


class TestJaccard:
    def test_identical(self) -> None:
        assert scout.jaccard("a b c", "a b c") == 1.0

    def test_disjoint(self) -> None:
        assert scout.jaccard("a b c", "x y z") == 0.0

    def test_partial_overlap(self) -> None:
        # 交集 {a,b}=2，并集 {a,b,c,d,x,y}=6 → 1/3
        assert scout.jaccard("a b c d", "a b x y") == pytest.approx(1 / 3)

    def test_empty_left(self) -> None:
        assert scout.jaccard("", "a b") == 0.0

    def test_both_empty(self) -> None:
        assert scout.jaccard("", "") == 0.0


class TestFilterEntry:
    def _entry(self, title, age_h=2.0, source_sub="AsianBeauty"):
        now = time.time()
        return {"title": title, "created_ts": now - age_h * 3600, "source_sub": source_sub}, now

    def test_passes_recent_clean(self) -> None:
        e, now = self._entry("Cool New Skincare Trend")
        assert scout.filter_entry(e, now) == (True, None)

    def test_drops_too_old(self) -> None:
        e, now = self._entry("Whatever", age_h=30)
        ok, reason = scout.filter_entry(e, now)
        assert ok is False and "age" in reason and "> 24h" in reason

    def test_drops_topic_keyword(self) -> None:
        e, now = self._entry("Trump wins the election today", source_sub="news")
        ok, reason = scout.filter_entry(e, now)
        assert ok is False and "topic kw" in reason

    def test_drops_form_keyword(self) -> None:
        e, now = self._entry("Where can I buy this jacket")
        ok, reason = scout.filter_entry(e, now)
        assert ok is False and "form kw" in reason

    def test_drops_blacklisted_source_sub(self) -> None:
        e, now = self._entry("Funny cat does a thing", source_sub="aww")
        ok, reason = scout.filter_entry(e, now)
        assert ok is False and "exclude list" in reason

    def test_zero_created_ts_treated_as_ancient(self) -> None:
        # created_ts=0 → age 取 999 → 直接超窗丢弃
        now = time.time()
        e = {"title": "X", "created_ts": 0, "source_sub": "x"}
        ok, reason = scout.filter_entry(e, now)
        assert ok is False and "999" in reason


class TestNormalizeEntry:
    def _atom_entry(self, age_h=2.0):
        now = time.time()
        return {
            "title": "Hello World",
            "permalink": "https://www.reddit.com/r/test/comments/aaa/hello/",
            "created_ts": now - age_h * 3600,
            "post_id": "t3_aaa",
            "source_sub": "AsianBeauty",
            "content_html": '<a href="https://ex.com">[link]</a> body text',
            "rank": 3,
            "fetched_from": "test",
        }, now

    def test_has_expected_keys(self) -> None:
        entry, now = self._atom_entry()
        out = scout.normalize_entry(entry, now)
        assert set(out.keys()) == {
            "title", "rank", "age_h", "permalink", "url",
            "fetched_from", "source_sub", "post_id", "selftext",
        }

    def test_age_rounded_and_url_from_content(self) -> None:
        entry, now = self._atom_entry(age_h=2.0)
        out = scout.normalize_entry(entry, now)
        assert out["age_h"] == 2.0
        assert out["url"] == "https://ex.com"  # content 外链优先
        assert out["rank"] == 3

    def test_zero_created_age_is_999(self) -> None:
        entry, now = self._atom_entry()
        entry["created_ts"] = 0
        out = scout.normalize_entry(entry, now)
        assert out["age_h"] == 999.0


class TestFingerprint:
    def test_normalizes_title(self) -> None:
        post = {"title": "Hello, World! Foo-Bar", "post_id": "t3_abc",
                "permalink": "https://reddit.com/p"}
        fp = scout.fingerprint(post)
        assert fp["title_norm"] == "hello world foo bar"
        assert fp["post_id"] == "t3_abc"
        assert fp["permalink"] == "https://reddit.com/p"

    def test_missing_post_id_defaults_empty(self) -> None:
        post = {"title": "x", "permalink": "p"}  # 无 post_id 键
        assert scout.fingerprint(post)["post_id"] == ""

    def test_title_truncated_to_120(self) -> None:
        post = {"title": "word " * 60, "post_id": "t3_x", "permalink": "p"}
        assert len(scout.fingerprint(post)["title_norm"]) == 120


class TestIsDup:
    def _hist(self):
        return [{
            "post_id": "t3_xxx",
            "permalink": "https://reddit.com/p1",
            "title_norm": "shared dinner recipe tonight",
            "ts": time.time(),
        }]

    def test_dup_by_post_id(self) -> None:
        post = {"title": "whatever", "post_id": "t3_xxx", "permalink": "different"}
        dup, why = scout.is_dup(post, self._hist())
        assert dup is True and "same post_id" in why

    def test_dup_by_permalink(self) -> None:
        post = {"title": "whatever", "post_id": "", "permalink": "https://reddit.com/p1"}
        dup, why = scout.is_dup(post, self._hist())
        assert dup is True and "same permalink" in why

    def test_dup_by_jaccard(self) -> None:
        post = {"title": "Shared dinner recipe tonight!", "post_id": "", "permalink": "none"}
        dup, why = scout.is_dup(post, self._hist())
        assert dup is True and "jaccard" in why

    def test_not_dup_when_unrelated(self) -> None:
        post = {"title": "Totally unrelated brand new headline",
                "post_id": "t3_zzz", "permalink": "other"}
        assert scout.is_dup(post, self._hist()) == (False, None)

    def test_empty_history_never_dup(self) -> None:
        post = {"title": "anything", "post_id": "t3_q", "permalink": "p"}
        assert scout.is_dup(post, []) == (False, None)


class TestParseContent:
    def test_link_post_extracts_external_url(self) -> None:
        html = ('submitted by /u/someone '
                '<a href="https://example.com/article">[link]</a> '
                '<a href="https://reddit.com/r/x">[comments]</a> body &amp; text')
        url, text = scout.parse_content(html, "https://reddit.com/perma")
        assert url == "https://example.com/article"
        # submitted by / [link] / [comments] / 实体 全部被清掉
        assert "submitted by" not in text
        assert "[link]" not in text and "[comments]" not in text
        assert "body" in text and "text" in text

    def test_self_post_falls_back_to_permalink(self) -> None:
        # 只有 reddit/redd.it 链接 → 无站外 url → 回落 permalink
        html = '<a href="https://reddit.com/r/x/comments/1">[comments]</a> just self text'
        url, text = scout.parse_content(html, "https://reddit.com/perma")
        assert url == "https://reddit.com/perma"
        assert text == "just self text"

    def test_skips_reddit_and_reddit_short_links(self) -> None:
        html = ('<a href="https://redd.it/abc">x</a> '
                '<a href="https://outbound.io/y">real</a>')
        url, _ = scout.parse_content(html, "perma")
        assert url == "https://outbound.io/y"

    def test_truncates_text_to_600(self) -> None:
        html = "x " * 500  # 远超 600 字符
        _, text = scout.parse_content(html, "perma")
        assert len(text) <= 600

    def test_empty_content_uses_permalink(self) -> None:
        url, text = scout.parse_content("", "https://reddit.com/perma")
        assert url == "https://reddit.com/perma"
        assert text == ""


class TestParseAtom:
    def _feed(self, recent):
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>First Cool Post</title>
    <link href="https://www.reddit.com/r/test/comments/aaa/first/"/>
    <published>{recent}</published>
    <id>t3_aaa</id>
    <category term="AsianBeauty"/>
    <content type="html">&lt;a href="https://ex.com"&gt;[link]&lt;/a&gt; hello</content>
  </entry>
  <entry>
    <title>Second Post</title>
    <link href="https://www.reddit.com/r/test/comments/bbb/second/"/>
    <published>{recent}</published>
    <id>t3_bbb</id>
  </entry>
</feed>""".encode("utf-8")

    def test_parses_entries_with_rank(self) -> None:
        entries = scout.parse_atom(self._feed(_iso_ago(hours=2)), "test")
        assert len(entries) == 2
        assert entries[0]["rank"] == 1 and entries[1]["rank"] == 2
        assert entries[0]["title"] == "First Cool Post"
        assert entries[0]["post_id"] == "t3_aaa"
        assert entries[0]["source_sub"] == "AsianBeauty"  # 来自 category term

    def test_source_sub_falls_back_to_fetched_from(self) -> None:
        # 第二个 entry 无 <category> → source_sub 回落 fetched_from
        entries = scout.parse_atom(self._feed(_iso_ago(hours=2)), "test")
        assert entries[1]["source_sub"] == "test"

    def test_created_ts_parsed(self) -> None:
        entries = scout.parse_atom(self._feed(_iso_ago(hours=2)), "test")
        assert entries[0]["created_ts"] > 0

    def test_bad_published_yields_zero_ts(self) -> None:
        entries = scout.parse_atom(self._feed("not-a-date"), "test")
        assert entries[0]["created_ts"] == 0.0

    def test_empty_feed_returns_empty_list(self) -> None:
        empty = (b'<?xml version="1.0"?>'
                 b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        assert scout.parse_atom(empty, "test") == []


class TestHistoryPersistence:
    def test_load_missing_returns_empty(self, tmp_path) -> None:
        assert scout.load_history(tmp_path / "nope.json") == []

    def test_save_then_load_roundtrip(self, tmp_path) -> None:
        path = tmp_path / "hist.json"
        passed = [{"title": "Hello World", "post_id": "t3_a",
                   "permalink": "https://reddit.com/p"}]
        scout.save_history(passed, [], path)
        loaded = scout.load_history(path)
        assert len(loaded) == 1
        assert loaded[0]["post_id"] == "t3_a"
        assert loaded[0]["title_norm"] == "hello world"
        assert "ts" in loaded[0]

    def test_old_records_filtered_by_cutoff(self, tmp_path) -> None:
        path = tmp_path / "hist.json"
        old_ts = time.time() - 8 * 86400   # 超 7 天
        recent_ts = time.time() - 1 * 86400
        path.write_text(json.dumps([
            {"post_id": "old", "ts": old_ts},
            {"post_id": "new", "ts": recent_ts},
        ]))
        kept = [r["post_id"] for r in scout.load_history(path)]
        assert kept == ["new"]

    def test_corrupt_file_returns_empty(self, tmp_path) -> None:
        path = tmp_path / "hist.json"
        path.write_text("{not json")
        assert scout.load_history(path) == []

    def test_save_creates_parent_dirs(self, tmp_path) -> None:
        path = tmp_path / "a" / "b" / "h.json"
        scout.save_history([{"title": "t", "post_id": "x", "permalink": "p"}], [], path)
        assert path.exists()

    def test_save_appends_to_existing(self, tmp_path) -> None:
        path = tmp_path / "h.json"
        existing = [{"title_norm": "old one", "post_id": "o",
                     "permalink": "op", "ts": 123}]
        scout.save_history(
            [{"title": "New", "post_id": "n", "permalink": "np"}], existing, path)
        data = json.loads(path.read_text())
        assert len(data) == 2
        assert any(r.get("post_id") == "o" for r in data)
        assert any(r.get("post_id") == "n" for r in data)
