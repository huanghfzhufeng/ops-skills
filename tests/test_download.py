"""xcmo-download/download.py 纯函数单测。

被测函数都是无 I/O 的纯函数，可以直接单测：
- sanitize_filename — 文件名安全化
- video_filename    — 视频本地命名规则
- parse_csv_list    — CLI 参数解析
"""
import pytest

import download

pytestmark = pytest.mark.unit


class TestSanitizeFilename:
    """sanitize_filename(name, max_len=50)"""

    def test_removes_path_chars(self) -> None:
        assert download.sanitize_filename('a/b\\c:d?e*f') == 'a-b-c-d-e-f'

    def test_removes_quotes_and_pipes(self) -> None:
        assert download.sanitize_filename('a<b>c"d|e') == 'a-b-c-d-e'

    def test_replaces_whitespace_chars(self) -> None:
        # \n \r \t 也在 bad 集合里
        assert download.sanitize_filename('a\nb\tc\rd') == 'a-b-c-d'

    def test_strips_surrounding_whitespace(self) -> None:
        assert download.sanitize_filename('  hello  ') == 'hello'

    def test_truncates_long_names(self) -> None:
        long = 'a' * 100
        result = download.sanitize_filename(long, max_len=50)
        assert len(result) == 50

    def test_custom_max_len(self) -> None:
        assert download.sanitize_filename('abcdefghij', max_len=5) == 'abcde'

    def test_under_max_len_unchanged(self) -> None:
        assert download.sanitize_filename('short') == 'short'

    def test_empty_string(self) -> None:
        assert download.sanitize_filename('') == ''

    def test_none_safe(self) -> None:
        # 函数内做了 (name or "") 兜底
        assert download.sanitize_filename(None) == ''

    def test_preserves_chinese_and_alphanumeric(self) -> None:
        assert download.sanitize_filename('正常名字 abc 123') == '正常名字 abc 123'


class TestVideoFilename:
    """video_filename(asset) → '{YYYYMMDD} {character} {name} {short_id}.mp4'"""

    def test_full_asset(self) -> None:
        asset = {
            "id": "abc12345-def6-7890-abcd-ef1234567890",
            "name": "get ready without me",
            "character_id": "nari",
            "created_at": "2026-05-20T11:13:01.452965",
        }
        assert download.video_filename(asset) == "20260520 nari get ready without me abc12345.mp4"

    def test_missing_created_at_uses_zero_date(self) -> None:
        asset = {
            "id": "abc12345-rest",
            "name": "video",
            "character_id": "unknown",
            "created_at": None,
        }
        assert download.video_filename(asset).startswith("00000000 ")

    def test_short_created_at_uses_zero_date(self) -> None:
        # 短于 10 字符无法切出日期
        asset = {
            "id": "abc12345-rest",
            "name": "video",
            "character_id": "unknown",
            "created_at": "2026",
        }
        assert download.video_filename(asset).startswith("00000000 ")

    def test_missing_name_falls_back_to_video(self) -> None:
        asset = {
            "id": "abc12345-rest",
            "name": None,
            "character_id": "nari",
            "created_at": "2026-05-20T10:00:00",
        }
        result = download.video_filename(asset)
        assert "video" in result

    def test_missing_character_falls_back_to_unknown(self) -> None:
        asset = {
            "id": "abc12345-rest",
            "name": "task",
            "character_id": None,
            "created_at": "2026-05-20",
        }
        assert "unknown" in download.video_filename(asset)

    def test_short_id_is_first_8_chars(self) -> None:
        asset = {
            "id": "deadbeef-cafe-1234-5678-9abcdef01234",
            "name": "x",
            "character_id": "y",
            "created_at": "2026-01-01",
        }
        assert download.video_filename(asset).endswith("deadbeef.mp4")

    def test_sanitizes_dangerous_name(self) -> None:
        asset = {
            "id": "abc12345-rest",
            "name": "video/with/slash",
            "character_id": "char",
            "created_at": "2026-01-01",
        }
        result = download.video_filename(asset)
        assert "/" not in result.replace("/", "")  # ensure slashes replaced
        assert "video-with-slash" in result

    def test_ends_with_mp4(self) -> None:
        asset = {"id": "x" * 8, "name": "a", "character_id": "b", "created_at": "2026-01-01"}
        assert download.video_filename(asset).endswith(".mp4")


class TestParseCsvList:
    """parse_csv_list(s) — 逗号分隔字符串 → 列表"""

    def test_empty_string(self) -> None:
        assert download.parse_csv_list("") == []

    def test_single_item(self) -> None:
        assert download.parse_csv_list("batch-A") == ["batch-A"]

    def test_multiple_items(self) -> None:
        assert download.parse_csv_list("a,b,c") == ["a", "b", "c"]

    def test_strips_spaces(self) -> None:
        assert download.parse_csv_list(" a , b , c ") == ["a", "b", "c"]

    def test_trailing_comma_ignored(self) -> None:
        assert download.parse_csv_list("a,b,") == ["a", "b"]

    def test_leading_comma_ignored(self) -> None:
        assert download.parse_csv_list(",a,b") == ["a", "b"]

    def test_empty_items_filtered(self) -> None:
        assert download.parse_csv_list("a,,b") == ["a", "b"]

    def test_only_commas_returns_empty(self) -> None:
        assert download.parse_csv_list(",,,") == []

    def test_only_spaces_returns_empty(self) -> None:
        assert download.parse_csv_list("   ") == []
