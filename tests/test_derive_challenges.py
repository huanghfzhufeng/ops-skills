"""derive_challenges.py 数据驱动聚合纯函数单测。

用 importlib 按路径加载（skills 目录不在 sys.path；与 test_analyzer_watch 同模式）。
"""
import importlib.util
from pathlib import Path

import pytest

_PY = Path(__file__).parent.parent / "skills" / "tk-template-scout" / "derive_challenges.py"
_spec = importlib.util.spec_from_file_location("derive_challenges", _PY)
derive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(derive)

pytestmark = pytest.mark.unit


class TestExtractHashtags:
    def test_basic(self) -> None:
        assert derive.extract_hashtags("look #monacogp #fashionweek") == ["monacogp", "fashionweek"]

    def test_lowercase_normalize(self) -> None:
        assert derive.extract_hashtags("#MonacoGP #FashionWeek") == ["monacogp", "fashionweek"]

    def test_drop_generic_stopwords(self) -> None:
        # fyp / viral / foryou 等人人都打的通用噪声剔掉，只留有信息量的
        assert derive.extract_hashtags("#fyp #viral #foryou #monacogp") == ["monacogp"]

    def test_drop_pure_digits(self) -> None:
        assert derive.extract_hashtags("#2026 #monacogp") == ["monacogp"]

    def test_drop_single_char(self) -> None:
        assert derive.extract_hashtags("#f #y #monacogp") == ["monacogp"]

    def test_keep_two_char_tags(self) -> None:
        # v6.1：保留 2 字符有意义标签（#f1 #ai），只剔单字符（解决 #f1 被误剔漏热点）
        assert derive.extract_hashtags("#f1 #ai #monacogp") == ["f1", "ai", "monacogp"]

    def test_empty_or_none(self) -> None:
        assert derive.extract_hashtags("") == []
        assert derive.extract_hashtags(None) == []

    def test_no_hashtag(self) -> None:
        assert derive.extract_hashtags("just a plain title") == []


def _data(personas: dict) -> dict:
    """personas: {pk: [(likes, title), ...]} → scout result.json 结构。"""
    return {"personas": {
        pk: {"videos": [{"like_count": likes, "title": title,
                         "url": f"https://www.tiktok.com/@x/video/{pk}{i}"}
                        for i, (likes, title) in enumerate(vids)]}
        for pk, vids in personas.items()
    }}


class TestAggregate:
    def test_cross_persona_ranks_first(self) -> None:
        # #monacogp 跨 2 角色，#solo 仅 1 角色 → 跨角色的排最前（核心信号 = 跨赛道传播）
        data = _data({
            "avery": [(471200, "look #monacogp")],
            "spencer": [(29000, "paddock #monacogp")],
            "jade": [(99999, "#solo")],
        })
        rows = derive.aggregate(data)
        assert rows[0]["hashtag"] == "monacogp"
        assert rows[0]["n_personas"] == 2
        assert rows[0]["total_likes"] == 471200 + 29000

    def test_max_likes_and_sample_from_top(self) -> None:
        data = _data({
            "avery": [(471200, "#monacogp")],
            "spencer": [(29000, "#monacogp")],
        })
        row = derive.aggregate(data)[0]
        assert row["max_likes"] == 471200
        assert "avery0" in row["sample_url"]  # sample_url 取最高赞那条

    def test_same_tag_in_one_video_counts_once(self) -> None:
        data = _data({"avery": [(1000, "#fashionweek #fashionweek")]})
        row = {r["hashtag"]: r for r in derive.aggregate(data)}["fashionweek"]
        assert row["n_videos"] == 1

    def test_tie_break_by_total_likes(self) -> None:
        # 同为跨 1 角色时，按总赞降序
        data = _data({"a": [(100, "#lowtag")], "b": [(9999, "#hightag")]})
        rows = derive.aggregate(data)
        assert rows[0]["hashtag"] == "hightag"

    def test_empty(self) -> None:
        assert derive.aggregate({"personas": {}}) == []
        assert derive.aggregate({}) == []
