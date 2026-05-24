"""tk-template-scout/scout.py 纯函数单测。

测无 I/O 的工具函数：
- parse_input — 'persona:url' 输入解析
- pick_top_n — 时间窗过滤 + 排序 + 降级
"""
import time

import pytest

import scout

pytestmark = pytest.mark.unit


class TestParseInput:
    def test_basic_two_personas(self) -> None:
        lines = [
            "sophie:https://www.tiktok.com/@a/video/1\n",
            "sophie:https://www.tiktok.com/@b/video/2\n",
            "ava:https://www.tiktok.com/@c/video/3\n",
        ]
        result = scout.parse_input(lines)
        assert result == {
            "sophie": [
                "https://www.tiktok.com/@a/video/1",
                "https://www.tiktok.com/@b/video/2",
            ],
            "ava": ["https://www.tiktok.com/@c/video/3"],
        }

    def test_skips_blank_and_comments(self) -> None:
        lines = [
            "\n",
            "# this is a comment\n",
            "sophie:https://www.tiktok.com/@a/video/1\n",
            "  \n",
        ]
        assert scout.parse_input(lines) == {
            "sophie": ["https://www.tiktok.com/@a/video/1"],
        }

    def test_skips_non_http(self) -> None:
        lines = [
            "sophie:not-a-url\n",
            "sophie:https://www.tiktok.com/@a/video/1\n",
        ]
        assert scout.parse_input(lines) == {
            "sophie": ["https://www.tiktok.com/@a/video/1"],
        }

    def test_lowercases_persona_key(self) -> None:
        lines = ["SOPHIE:https://www.tiktok.com/@a/video/1\n"]
        assert scout.parse_input(lines) == {
            "sophie": ["https://www.tiktok.com/@a/video/1"],
        }

    def test_handles_https_in_url_correctly(self) -> None:
        lines = ["sophie:https://www.tiktok.com/@a/video/1?foo=bar\n"]
        assert scout.parse_input(lines) == {
            "sophie": ["https://www.tiktok.com/@a/video/1?foo=bar"],
        }

    def test_empty_input(self) -> None:
        assert scout.parse_input([]) == {}


class TestPickTopN:
    @pytest.fixture
    def now(self) -> float:
        return time.time()

    def _rec(self, ts_offset_hours: float, like_count: int, vid: str = "x") -> dict:
        return {
            "id": vid,
            "timestamp": int(time.time() - ts_offset_hours * 3600),
            "like_count": like_count,
        }

    def test_fresh_when_enough_within_24h(self) -> None:
        records = [
            self._rec(1, 1000, "a"),
            self._rec(2, 5000, "b"),
            self._rec(20, 3000, "c"),
            self._rec(30, 9999, "d"),  # > 24h
        ]
        cutoff = time.time() - 24 * 3600
        top, age = scout.pick_top_n(records, cutoff, top_n=3)
        assert age == "fresh"
        assert [r["id"] for r in top] == ["b", "c", "a"]

    def test_degrade_to_7d_when_24h_short(self) -> None:
        records = [
            self._rec(1, 1000, "a"),  # 24h 内
            self._rec(50, 5000, "b"),  # 7d 内
            self._rec(100, 8000, "c"),  # 7d 内
            self._rec(200, 999, "d"),  # > 7d
        ]
        cutoff = time.time() - 24 * 3600
        top, age = scout.pick_top_n(records, cutoff, top_n=3)
        assert age == "7d"
        assert [r["id"] for r in top] == ["c", "b", "a"]

    def test_degrade_to_all_when_7d_short(self) -> None:
        records = [
            self._rec(1, 100, "a"),
            self._rec(500, 999, "b"),
            self._rec(1000, 50, "c"),
        ]
        cutoff = time.time() - 24 * 3600
        top, age = scout.pick_top_n(records, cutoff, top_n=3)
        assert age == "all"
        assert [r["id"] for r in top] == ["b", "a", "c"]

    def test_empty_records(self) -> None:
        cutoff = time.time() - 24 * 3600
        top, age = scout.pick_top_n([], cutoff, top_n=3)
        assert top == []
        assert age == "all"

    def test_top_n_respected(self) -> None:
        records = [self._rec(1, i, str(i)) for i in range(10)]
        cutoff = time.time() - 24 * 3600
        top, _ = scout.pick_top_n(records, cutoff, top_n=3)
        assert len(top) == 3
        assert [r["id"] for r in top] == ["9", "8", "7"]

    def test_no_timestamp_records_excluded_from_fresh(self) -> None:
        records = [
            {"id": "a", "timestamp": None, "like_count": 9999},
            self._rec(1, 100, "b"),
            self._rec(2, 200, "c"),
            self._rec(3, 300, "d"),
        ]
        cutoff = time.time() - 24 * 3600
        top, age = scout.pick_top_n(records, cutoff, top_n=3)
        assert age == "fresh"
        assert "a" not in [r["id"] for r in top]
