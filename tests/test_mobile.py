"""xcmo-mobile/mobile.py 纯函数单测。

测无 I/O 的工具函数：
- normalize_date / parse_date_range — 日期解析
- sanitize_filename / safe_character_id — 字符串安全化
- video_filename / thumb_filename — 文件名生成规则
- find_free_port — 端口探测
"""
import socket

import pytest

import mobile  # 由 conftest.py 加到 sys.path

pytestmark = pytest.mark.unit


class TestNormalizeDate:
    def test_iso_format_passthrough(self) -> None:
        assert mobile.normalize_date("2026-05-22") == "2026-05-22"

    def test_compact_8_digits(self) -> None:
        assert mobile.normalize_date("20260522") == "2026-05-22"

    def test_strips_whitespace(self) -> None:
        assert mobile.normalize_date("  2026-05-22  ") == "2026-05-22"

    def test_rejects_invalid_format(self) -> None:
        with pytest.raises(ValueError):
            mobile.normalize_date("2026/05/22")

    def test_rejects_chinese_format(self) -> None:
        with pytest.raises(ValueError):
            mobile.normalize_date("5月22日")

    def test_rejects_short_string(self) -> None:
        with pytest.raises(ValueError):
            mobile.normalize_date("2026")


class TestParseDateRange:
    def test_single_day(self) -> None:
        assert mobile.parse_date_range("2026-05-22") == ("2026-05-22", "2026-05-22")

    def test_single_day_compact(self) -> None:
        assert mobile.parse_date_range("20260522") == ("2026-05-22", "2026-05-22")

    def test_range_with_tilde(self) -> None:
        assert mobile.parse_date_range("2026-05-21~2026-05-22") == ("2026-05-21", "2026-05-22")

    def test_range_with_to(self) -> None:
        assert mobile.parse_date_range("2026-05-21to2026-05-22") == ("2026-05-21", "2026-05-22")

    def test_range_with_spaces(self) -> None:
        assert mobile.parse_date_range("2026-05-21 ~ 2026-05-22") == ("2026-05-21", "2026-05-22")

    def test_range_compact(self) -> None:
        assert mobile.parse_date_range("20260521~20260522") == ("2026-05-21", "2026-05-22")


class TestSanitizeFilename:
    def test_removes_path_chars(self) -> None:
        assert mobile.sanitize_filename("a/b\\c:d?e*f") == "a-b-c-d-e-f"

    def test_strips_whitespace(self) -> None:
        assert mobile.sanitize_filename("  hello  ") == "hello"

    def test_truncates_long_names(self) -> None:
        assert len(mobile.sanitize_filename("a" * 100, max_len=50)) == 50

    def test_empty_string(self) -> None:
        assert mobile.sanitize_filename("") == ""

    def test_none_safe(self) -> None:
        assert mobile.sanitize_filename(None) == ""

    def test_preserves_chinese_and_alphanumeric(self) -> None:
        assert mobile.sanitize_filename("正常名字 abc 123") == "正常名字 abc 123"

    def test_replaces_newlines(self) -> None:
        assert mobile.sanitize_filename("a\nb\tc\rd") == "a-b-c-d"


class TestSafeCharacterId:
    def test_normal_id(self) -> None:
        assert mobile.safe_character_id("asian-blond") == "asian-blond"

    def test_none_falls_back_to_unknown(self) -> None:
        assert mobile.safe_character_id(None) == "_unknown"

    def test_empty_falls_back_to_unknown(self) -> None:
        assert mobile.safe_character_id("") == "_unknown"

    def test_sanitizes_special_chars(self) -> None:
        assert mobile.safe_character_id("char/with/slash") == "char-with-slash"


class TestVideoFilename:
    def test_full_asset(self) -> None:
        asset = {
            "id": "abc12345-def6-7890-abcd-ef1234567890",
            "name": "get ready without me",
        }
        assert mobile.video_filename(asset) == "get ready without me abc12345.mp4"

    def test_missing_name_falls_back(self) -> None:
        asset = {"id": "abc12345-rest", "name": None}
        assert "video" in mobile.video_filename(asset)
        assert mobile.video_filename(asset).endswith(".mp4")

    def test_sanitizes_name_path_chars(self) -> None:
        asset = {"id": "abc12345-rest", "name": "video/with/slash"}
        result = mobile.video_filename(asset)
        assert "/" not in result.replace("/", "")  # no slash
        assert "video-with-slash" in result

    def test_short_id_is_first_8(self) -> None:
        asset = {"id": "deadbeef-cafe-1234-5678", "name": "x"}
        assert mobile.video_filename(asset).endswith("deadbeef.mp4")


class TestThumbFilename:
    def test_same_pattern_jpg_ext(self) -> None:
        asset = {"id": "abc12345-rest", "name": "test name"}
        thumb = mobile.thumb_filename(asset)
        video = mobile.video_filename(asset)
        assert thumb.endswith(".jpg")
        assert video.endswith(".mp4")
        assert thumb.removesuffix(".jpg") == video.removesuffix(".mp4")


class TestFindFreePort:
    def test_finds_available_port(self) -> None:
        # 用一个高位区间避开真在用的端口
        port = mobile.find_free_port(55000, 55100)
        assert 55000 <= port < 55100

    def test_skips_busy_port(self) -> None:
        # 占住一个端口，验证它会跳过
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.bind(("", 0))
        busy_port = busy.getsockname()[1]
        busy.listen(1)
        try:
            found = mobile.find_free_port(busy_port, busy_port + 5)
            assert found != busy_port
        finally:
            busy.close()

    def test_raises_when_all_busy(self) -> None:
        # 占住一段连续区间，验证抛错
        sockets = []
        try:
            for _ in range(3):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("", 0))
                s.listen(1)
                sockets.append(s)
            busy_ports = sorted(s.getsockname()[1] for s in sockets)
            if busy_ports[-1] == busy_ports[0] + 2:  # 连续 3 个
                with pytest.raises(RuntimeError):
                    mobile.find_free_port(busy_ports[0], busy_ports[-1] + 1)
        finally:
            for s in sockets:
                s.close()
