"""sge-blog-watcher/watch.py 纯函数 + seen 持久化单测。

用 importlib 按路径显式加载（sge-blog-watcher 和 analyzer-watch 的脚本都叫 watch.py，
不能靠 sys.path import watch，会撞名）。参照 tests/test_analyzer_watch.py 的写法。

注意：本模块用 STATE_FILE / STATE_DIR 作为 state 路径（不是 analyzer 的 SEEN_FILE），
监听 SGE 博客 sitemap，故 load_seen/save_seen 测试 monkeypatch 的是 STATE_FILE / STATE_DIR。
"""
import importlib.util
from pathlib import Path

import pytest

_WATCH_PY = Path(__file__).parent.parent / "skills" / "sge-blog-watcher" / "watch.py"
_spec = importlib.util.spec_from_file_location("sge_blog_watcher", _WATCH_PY)
watch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch)

pytestmark = pytest.mark.unit

_BASE = "https://www.socialgrowthengineers.com"


class TestNormalize:
    def test_adds_www_and_https(self) -> None:
        # 无 www / http → 统一补 www + https
        assert watch.normalize("http://socialgrowthengineers.com/my-post") == f"{_BASE}/my-post"

    def test_strips_trailing_slash(self) -> None:
        assert watch.normalize(f"{_BASE}/my-post/") == f"{_BASE}/my-post"

    def test_drops_query_and_fragment(self) -> None:
        # ?# 之后全丢；多段路径保留
        assert watch.normalize(f"{_BASE}/foo/bar/?x=1#frag") == f"{_BASE}/foo/bar"

    def test_root_url_no_path(self) -> None:
        # 无 path → 回落到根（无尾斜杠）
        assert watch.normalize(_BASE) == _BASE

    def test_garbage_input_falls_back_to_root(self) -> None:
        # 不匹配域名的垃圾串不抛异常，回落到根 URL
        assert watch.normalize("totally garbage no domain") == _BASE


class TestIsBlogUrl:
    def test_single_segment_is_blog(self) -> None:
        assert watch.is_blog_url("/my-post") is True

    def test_trailing_slash_still_blog(self) -> None:
        # rstrip 尾斜杠后仍是单段
        assert watch.is_blog_url("/my-post/") is True

    def test_two_segments_excluded(self) -> None:
        # /apps/foo 有两个 / → 非博客
        assert watch.is_blog_url("/apps/foo") is False

    def test_exact_exclude_static_page(self) -> None:
        # 命中 EXCLUDE_EXACT 静态导航页
        assert watch.is_blog_url("/about") is False
        assert watch.is_blog_url("/contact") is False

    def test_root_not_blog(self) -> None:
        # 根路径 rstrip 后是空串，count('/')==0 != 1 → 非博客
        assert watch.is_blog_url("/") is False


class TestMetaProp:
    def test_extracts_and_unescapes(self) -> None:
        text = '<meta property="og:title" content="Hello &amp; World">'
        assert watch._meta_prop(text, "og:title") == "Hello & World"

    def test_missing_returns_none(self) -> None:
        text = '<meta property="og:title" content="x">'
        assert watch._meta_prop(text, "og:image") is None

    def test_empty_text(self) -> None:
        assert watch._meta_prop("", "og:title") is None


class TestMetaName:
    def test_extracts_and_unescapes(self) -> None:
        text = '<meta name="description" content="Desc &lt;here&gt;">'
        assert watch._meta_name(text, "description") == "Desc <here>"

    def test_missing_returns_none(self) -> None:
        text = '<meta name="description" content="x">'
        assert watch._meta_name(text, "keywords") is None

    def test_does_not_match_property_meta(self) -> None:
        # name= 正则不该匹配 property= 的 meta
        text = '<meta property="og:description" content="prop only">'
        assert watch._meta_name(text, "og:description") is None


class TestReadTime:
    def test_plain_minutes(self) -> None:
        assert watch._read_time("about 5 min read here") == "5 min read"

    def test_double_digit(self) -> None:
        assert watch._read_time("roughly 12 min read") == "12 min read"

    def test_less_than_one(self) -> None:
        # 字面 "< 1 min read" 走 (<\s*1) 分支，整段保留
        assert watch._read_time("< 1 min read") == "< 1 min read"

    def test_none_when_absent(self) -> None:
        assert watch._read_time("no time info at all") is None


class TestExtractBody:
    def test_pulls_article_text_double_unescape(self) -> None:
        # <article> 内取正文；SGE 二次转义 &amp;amp; → &amp; → & ；script 被剥掉
        body = ("<html><article> Hello &amp;amp; <b>world</b> "
                "<script>var x=1;</script> end </article></html>")
        assert watch._extract_body(body) == "Hello & world end"

    def test_falls_back_to_whole_text_when_no_article(self) -> None:
        # 无 <article> 标签时退化为整段文本
        assert watch._extract_body("<p>just &amp;amp; text</p>") == "just & text"

    def test_strips_style_blocks(self) -> None:
        body = "<article><style>.a{color:red}</style>keep this</article>"
        assert watch._extract_body(body) == "keep this"

    def test_truncates_to_body_max(self) -> None:
        # 超长正文截断到 BODY_MAX_CHARS
        long_text = "<article>" + ("a" * (watch.BODY_MAX_CHARS + 500)) + "</article>"
        assert len(watch._extract_body(long_text)) == watch.BODY_MAX_CHARS

    def test_empty_input(self) -> None:
        assert watch._extract_body("") == ""


class TestSeen:
    def test_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(watch, "STATE_DIR", tmp_path)
        monkeypatch.setattr(watch, "STATE_FILE", tmp_path / "seen.json")
        assert watch.load_seen() is None  # 不存在 → None（baseline 信号）
        watch.save_seen({"https://a", "https://b"})
        assert watch.load_seen() == {"https://a", "https://b"}

    def test_missing_file_returns_none(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(watch, "STATE_FILE", tmp_path / "nope.json")
        assert watch.load_seen() is None

    def test_corrupt_returns_none(self, tmp_path, monkeypatch) -> None:
        bad = tmp_path / "seen.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(watch, "STATE_FILE", bad)
        assert watch.load_seen() is None

    def test_save_creates_state_dir(self, tmp_path, monkeypatch) -> None:
        nested = tmp_path / "deep" / "dir"
        monkeypatch.setattr(watch, "STATE_DIR", nested)
        monkeypatch.setattr(watch, "STATE_FILE", nested / "seen.json")
        watch.save_seen({"x"})
        assert (nested / "seen.json").exists()
        assert watch.load_seen() == {"x"}

    def test_save_writes_sorted_with_count(self, tmp_path, monkeypatch) -> None:
        import json
        monkeypatch.setattr(watch, "STATE_DIR", tmp_path)
        monkeypatch.setattr(watch, "STATE_FILE", tmp_path / "seen.json")
        watch.save_seen({"https://c", "https://a", "https://b"})
        payload = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
        assert payload["seen"] == ["https://a", "https://b", "https://c"]
        assert payload["count"] == 3
