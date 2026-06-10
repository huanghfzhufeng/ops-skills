"""analyzer-watch/watch.py 纯函数 + 配置解析 + seen 持久化单测。

用 importlib 按路径显式加载（sge-blog-watcher 和 analyzer-watch 的脚本都叫 watch.py，
不能靠 sys.path import watch，会撞名）。
"""
import datetime
import importlib.util
import json
from pathlib import Path

import pytest

_WATCH_PY = Path(__file__).parent.parent / "skills" / "analyzer-watch" / "watch.py"
_spec = importlib.util.spec_from_file_location("analyzer_watch", _WATCH_PY)
watch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch)

pytestmark = pytest.mark.unit


def _cfg(view_th=1000, er_th=5, er_min=500, er_max_age=7):
    return {"view_th": float(view_th), "er_th": float(er_th),
            "er_min_views": float(er_min), "er_max_age_days": float(er_max_age)}


def _vid(views, er, vid="1", age_days=0):
    created = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(days=age_days, hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"tiktok_video_id": vid, "url": "https://www.tiktok.com/@x/video/1",
            "latest_metrics": {"views": views}, "engagement_rate": er, "created_at": created}


class TestFindHits:
    """命中逻辑 v1：播放>1000  或  (ER>5% 且 播放>500 且 发布≤7天)。"""

    def test_flow_hit_over_1000(self) -> None:
        # 纯流量：播放>1000 命中，不管 ER/发布多久
        hits = watch.find_hits([_vid(1500, 0.5, age_days=100)], _cfg())
        assert len(hits) == 1 and "播放破1000" in hits[0][3]

    def test_flow_not_hit_under_1000(self) -> None:
        # 播放<1000 且 ER 不达标 → 不命中
        assert watch.find_hits([_vid(800, 1)], _cfg()) == []

    def test_er_new_video_hit(self) -> None:
        # ER>5 且 播放>500 且 7天内 → 命中
        hits = watch.find_hits([_vid(600, 8, age_days=2)], _cfg())
        assert len(hits) == 1 and any("ER破" in r for r in hits[0][3])

    def test_er_blocked_low_views(self) -> None:
        # ER>5 但播放<500 → 不命中（砍低播放噪音）
        assert watch.find_hits([_vid(400, 12, age_days=1)], _cfg()) == []

    def test_er_blocked_old_video(self) -> None:
        # ER>5 播放>500 但发布>7天 → 不命中（7天约束砍老视频慢热）
        assert watch.find_hits([_vid(600, 12, age_days=30)], _cfg()) == []

    def test_both_reasons(self) -> None:
        # 播放>1000 且 ER>5 且 7天内 → 两个命中原因
        _, _, _, reasons = watch.find_hits([_vid(1500, 8, age_days=1)], _cfg())[0]
        assert "播放破1000" in reasons and any("ER破" in r for r in reasons)

    def test_no_hit(self) -> None:
        assert watch.find_hits([_vid(100, 2)], _cfg()) == []

    def test_created_at_missing_flow_still_hits(self) -> None:
        # created_at 缺失：ER 那条判不了，但播放>1000 仍命中（安全兜底）
        v = {"tiktok_video_id": "1", "url": "https://x",
             "latest_metrics": {"views": 1500}, "engagement_rate": 12}
        hits = watch.find_hits([v], _cfg())
        assert len(hits) == 1 and "播放破1000" in hits[0][3]

    def test_null_fields_treated_as_zero(self) -> None:
        v = {"tiktok_video_id": "1", "url": "https://x", "latest_metrics": {},
             "engagement_rate": None, "created_at": None}
        assert watch.find_hits([v], _cfg()) == []


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


class TestStateRoundtrip:
    def test_missing_file_means_double_baseline(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(watch, "SEEN_FILE", tmp_path / "seen.json")
        assert watch.load_state() == (None, None)  # (seen baseline 信号, milestones baseline 信号)

    def test_old_format_seen_ok_milestones_none(self, tmp_path, monkeypatch) -> None:
        """老格式（只有 seen 列表）→ seen 正常读出，milestones=None（触发静默记档，防上线刷屏）。"""
        f = tmp_path / "seen.json"
        f.write_text(json.dumps({"seen": ["a", "b"], "count": 2}), encoding="utf-8")
        monkeypatch.setattr(watch, "SEEN_FILE", f)
        seen, ms = watch.load_state()
        assert seen == {"a", "b"} and ms is None

    def test_new_format_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(watch, "STATE_DIR", tmp_path)
        monkeypatch.setattr(watch, "SEEN_FILE", tmp_path / "seen.json")
        watch.save_state({"a", "b"}, {"a": 10000})
        assert watch.load_state() == ({"a", "b"}, {"a": 10000})

    def test_corrupt_returns_none_none(self, tmp_path, monkeypatch) -> None:
        bad = tmp_path / "seen.json"
        bad.write_text("{not json")
        monkeypatch.setattr(watch, "SEEN_FILE", bad)
        assert watch.load_state() == (None, None)


def _mv(vid: str, views: int, er: float = 3.0) -> dict:
    """里程碑测试用视频。"""
    return {"tiktok_video_id": vid, "url": f"https://www.tiktok.com/@x/video/{vid}",
            "latest_metrics": {"views": views}, "engagement_rate": er}


class TestFindMilestoneHits:
    """爆款战报：已预警过(in seen)的视频，播放跨过新档位（>1万 / >10万）再各提醒一次。"""

    TH = [10000, 100000]

    def test_not_in_seen_ignored(self) -> None:
        # 没首推过的不爆款战报（它该走首次预警），播放再高也不报
        assert watch.find_milestone_hits([_mv("1", 500000)], set(), {}, self.TH) == []

    def test_exactly_at_threshold_no_hit(self) -> None:
        # 「大于 1万」是严格大于：恰好 10000 不报
        assert watch.find_milestone_hits([_mv("1", 10000)], {"1"}, {}, self.TH) == []

    def test_cross_first_tier(self) -> None:
        hits = watch.find_milestone_hits([_mv("1", 10001)], {"1"}, {}, self.TH)
        assert len(hits) == 1 and hits[0][3] == 10000

    def test_skip_tier_reports_only_top(self) -> None:
        # 两轮之间直接从几千蹿到 15 万 → 只报「破10万」一张，不连发两张
        hits = watch.find_milestone_hits([_mv("1", 150000)], {"1"}, {}, self.TH)
        assert len(hits) == 1 and hits[0][3] == 100000

    def test_second_tier_after_first(self) -> None:
        # 报过 1万 档后涨到 12 万 → 报 10万 档
        hits = watch.find_milestone_hits([_mv("1", 120000)], {"1"}, {"1": 10000}, self.TH)
        assert len(hits) == 1 and hits[0][3] == 100000

    def test_already_top_never_repeats(self) -> None:
        assert watch.find_milestone_hits([_mv("1", 999999)], {"1"}, {"1": 100000}, self.TH) == []

    def test_same_tier_growth_no_repeat(self) -> None:
        # 1.2万 报过 1万档，涨到 5 万（仍在 1万-10万 区间）→ 不重复报
        assert watch.find_milestone_hits([_mv("1", 50000)], {"1"}, {"1": 10000}, self.TH) == []

    def test_empty_thresholds_feature_off(self) -> None:
        assert watch.find_milestone_hits([_mv("1", 999999)], {"1"}, {}, []) == []


class TestBaselineMilestones:
    """上线第一轮静默记档：把 seen 里历史视频按当前播放记档，不发卡（防把历史爆款刷一遍群）。"""

    def test_records_top_crossed_only_for_seen(self) -> None:
        videos = [_mv("a", 150000), _mv("b", 20000), _mv("c", 500), _mv("d", 999999)]
        ms = watch.baseline_milestones(videos, {"a", "b", "c"}, [10000, 100000])
        assert ms == {"a": 100000, "b": 10000}  # c 没过档不记；d 不在 seen 不记

    def test_empty(self) -> None:
        assert watch.baseline_milestones([], set(), [10000, 100000]) == {}


class TestMilestoneLabel:
    def test_wan(self) -> None:
        assert watch.milestone_label(10000) == "播放破1万"
        assert watch.milestone_label(100000) == "播放破10万"
        assert watch.milestone_label(500000) == "播放破50万"

    def test_non_wan_fallback(self) -> None:
        assert watch.milestone_label(5000) == "播放破5000"


class TestParseMilestones:
    def test_default(self) -> None:
        assert watch.parse_milestones("10000,100000") == [10000, 100000]

    def test_dedup_sort_and_garbage(self) -> None:
        assert watch.parse_milestones("100000, 10000,10000, abc, -5") == [10000, 100000]

    def test_empty_means_off(self) -> None:
        assert watch.parse_milestones("") == []
        assert watch.parse_milestones(None) == []


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
        assert cfg["milestones"] == [10000, 100000]  # 没配 milestone_thresholds → 默认两档

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
