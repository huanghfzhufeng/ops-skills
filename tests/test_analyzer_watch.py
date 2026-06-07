"""analyzer-watch/watch.py 纯函数 + 配置解析 + seen 持久化单测。

用 importlib 按路径显式加载（sge-blog-watcher 和 analyzer-watch 的脚本都叫 watch.py，
不能靠 sys.path import watch，会撞名）。
"""
import datetime
import importlib.util
from pathlib import Path

import pytest

_WATCH_PY = Path(__file__).parent.parent / "skills" / "analyzer-watch" / "watch.py"
_spec = importlib.util.spec_from_file_location("analyzer_watch", _WATCH_PY)
watch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch)

pytestmark = pytest.mark.unit


def _cfg(view_th=500, er_th=5, er_min=0):
    return {"view_th": float(view_th), "er_th": float(er_th), "er_min_views": float(er_min)}


def _vid(views, er, vid="1"):
    return {"tiktok_video_id": vid, "url": "https://www.tiktok.com/@x/video/1",
            "latest_metrics": {"views": views}, "engagement_rate": er}


class TestFindHits:
    def test_view_hit(self) -> None:
        hits = watch.find_hits([_vid(600, 1)], _cfg())
        assert len(hits) == 1 and "播放破500" in hits[0][3]

    def test_er_hit_no_floor(self) -> None:
        # er_min_views=0：纯 ER>5 命中，低播放也算（owen 观察期行为）
        hits = watch.find_hits([_vid(39, 12)], _cfg(er_min=0))
        assert len(hits) == 1 and any("ER破" in r for r in hits[0][3])

    def test_er_floor_blocks_low_views(self) -> None:
        # er_min_views=300：播放 39 / ER 12 不命中（低于门槛，砍噪音）
        assert watch.find_hits([_vid(39, 12)], _cfg(er_min=300)) == []

    def test_er_floor_allows_high_views(self) -> None:
        hits = watch.find_hits([_vid(400, 12)], _cfg(er_min=300))
        assert len(hits) == 1

    def test_no_hit(self) -> None:
        assert watch.find_hits([_vid(100, 2)], _cfg(er_min=300)) == []

    def test_both_reasons(self) -> None:
        _, _, _, reasons = watch.find_hits([_vid(600, 8)], _cfg(er_min=300))[0]
        assert "播放破500" in reasons and any("ER破" in r for r in reasons)

    def test_null_fields_treated_as_zero(self) -> None:
        v = {"tiktok_video_id": "1", "url": "https://x", "latest_metrics": {}, "engagement_rate": None}
        assert watch.find_hits([v], _cfg(er_min=300)) == []


class TestRelTime:
    def test_days_ago(self) -> None:
        past = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=17, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        assert watch.rel_time(past) == "发布17天前"

    def test_hours_ago(self) -> None:
        past = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
        assert watch.rel_time(past) == "发布5小时前"

    def test_empty_and_invalid(self) -> None:
        assert watch.rel_time(None) == ""
        assert watch.rel_time("") == ""
        assert watch.rel_time("not-a-date") == ""


class TestHandleOf:
    def test_normal(self) -> None:
        assert watch.handle_of({"url": "https://www.tiktok.com/@spencer.nyc/video/123"}) == "spencer.nyc"

    def test_malformed(self) -> None:
        assert watch.handle_of({"url": "https://x"}) == "?"
        assert watch.handle_of({}) == "?"


class TestSeen:
    def test_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(watch, "STATE_DIR", tmp_path)
        monkeypatch.setattr(watch, "SEEN_FILE", tmp_path / "seen.json")
        assert watch.load_seen() is None  # 不存在 → None（baseline 信号）
        watch.save_seen({"a", "b"})
        assert watch.load_seen() == {"a", "b"}

    def test_corrupt_returns_none(self, tmp_path, monkeypatch) -> None:
        bad = tmp_path / "seen.json"
        bad.write_text("{not json")
        monkeypatch.setattr(watch, "SEEN_FILE", bad)
        assert watch.load_seen() is None


class TestLoadConfig:
    def test_inline_comment_not_in_value(self, tmp_path, monkeypatch) -> None:
        """回归 de1e5c3：行内注释不能混进值（原来 float('0   # 注释') 崩溃）。"""
        cfg_file = tmp_path / "c.yaml"
        cfg_file.write_text(
            'base_url: "http://x:8001"\n'
            'email: "a@b.com"\n'
            'password: "pw"\n'
            'feishu_webhook: "https://open.feishu.cn/hook/x"\n'
            'er_min_views: 0     # 这段注释不该进值\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(watch, "CONFIG_FILE", cfg_file)
        cfg = watch.load_config()
        assert cfg["er_min_views"] == 0
        assert cfg["base_url"] == "http://x:8001"
        assert cfg["email"] == "a@b.com"

    def test_quoted_value_with_hash_kept(self, tmp_path, monkeypatch) -> None:
        """带引号的值里的 # 不算注释（webhook URL 可能含特殊字符）。"""
        cfg_file = tmp_path / "c.yaml"
        cfg_file.write_text(
            'base_url: "http://x"\n'
            'email: "a@b.com"\n'
            'password: "pw#withhash"\n'
            'feishu_webhook: "https://open.feishu.cn/hook/x"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(watch, "CONFIG_FILE", cfg_file)
        cfg = watch.load_config()
        assert cfg["password"] == "pw#withhash"
