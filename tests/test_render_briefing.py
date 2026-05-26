"""tk-template-scout/render_briefing.py 纯函数单测。

覆盖：
- fmt_likes：3 个区间（万 / K / 个位）
- clean_title：折叠空白、空标题 fallback
- capitalize_persona：首字母大写
- format_briefing：完整渲染（含 0 命中 + 标准条目 + 26 人顺序）
"""
from datetime import datetime

import pytest

import render_briefing

pytestmark = pytest.mark.unit


# ---------- fmt_likes ----------


class TestFmtLikes:
    def test_ten_thousand_uses_wan(self) -> None:
        assert render_briefing.fmt_likes(10000) == "1.0万赞"
        assert render_briefing.fmt_likes(123456) == "12.3万赞"
        # 注：Python 默认 banker's rounding（round half to even），23.65 → 23.6
        # 简报里 0.1 万赞精度差异不影响运营决策，跟着默认行为即可
        assert render_briefing.fmt_likes(236500) == "23.6万赞"

    def test_thousand_uses_K(self) -> None:
        assert render_briefing.fmt_likes(1000) == "1.0K赞"
        assert render_briefing.fmt_likes(9999) == "10.0K赞"
        assert render_briefing.fmt_likes(3500) == "3.5K赞"

    def test_below_thousand_raw(self) -> None:
        assert render_briefing.fmt_likes(999) == "999赞"
        assert render_briefing.fmt_likes(123) == "123赞"
        assert render_briefing.fmt_likes(0) == "0赞"

    def test_boundary_999_vs_1000(self) -> None:
        assert render_briefing.fmt_likes(999) == "999赞"
        assert render_briefing.fmt_likes(1000) == "1.0K赞"

    def test_boundary_9999_vs_10000(self) -> None:
        assert render_briefing.fmt_likes(9999) == "10.0K赞"
        assert render_briefing.fmt_likes(10000) == "1.0万赞"


# ---------- clean_title ----------


class TestCleanTitle:
    def test_basic(self) -> None:
        assert render_briefing.clean_title("hello world") == "hello world"

    def test_collapses_multiple_spaces(self) -> None:
        assert render_briefing.clean_title("hello    world") == "hello world"

    def test_collapses_newlines(self) -> None:
        assert render_briefing.clean_title("line1\nline2\n\nline3") == "line1 line2 line3"

    def test_strips_outer_whitespace(self) -> None:
        assert render_briefing.clean_title("  hello  ") == "hello"

    def test_empty_falls_back(self) -> None:
        assert render_briefing.clean_title("") == "(无标题)"
        assert render_briefing.clean_title("   ") == "(无标题)"
        assert render_briefing.clean_title(None) == "(无标题)"  # type: ignore[arg-type]


# ---------- capitalize_persona ----------


class TestCapitalizePersona:
    def test_basic(self) -> None:
        assert render_briefing.capitalize_persona("sophie") == "Sophie"
        assert render_briefing.capitalize_persona("eleanor") == "Eleanor"

    def test_already_capital(self) -> None:
        assert render_briefing.capitalize_persona("Sophie") == "Sophie"

    def test_single_char(self) -> None:
        assert render_briefing.capitalize_persona("a") == "A"

    def test_empty(self) -> None:
        assert render_briefing.capitalize_persona("") == ""


# ---------- format_briefing 完整渲染 ----------


@pytest.fixture
def sample_personas() -> dict:
    return {
        "sophie":  {"handle": "@sophie.fits2"},
        "ava":     {"handle": "@ava.glow3"},
        "ezra":    {"handle": "@ezra.style2"},
        "riley":   {"handle": "@finn.fits2"},
        "clara":   {"handle": "@clara.wellness2"},
        "leila":   {"handle": "@evelyn.pilates"},
        "ryan":    {"handle": "@ryan.eats8"},
        "max":     {"handle": "@max.walks0"},
        "mia":     {"handle": "@mia.apps"},
        "charlotte": {"handle": "@charlotte.ai"},
        "priya":   {"handle": "@jake.setup"},
        "ro":      {"handle": "@eli.hacks"},
        "silver":  {"handle": "@silver.szn_"},
        "nari":    {"handle": "@nari.actually"},
        "avery":   {"handle": "@averyyyinla"},
        "joey":    {"handle": "@joey.actually"},
        "caden":   {"handle": "@caden.actually"},
        "mason":   {"handle": "@its.mason_7"},
        "kai":     {"handle": "@kai.szn_1"},
        "jesse":   {"handle": "@its.jesse_1"},
        "emma":    {"handle": "@emma.era_"},
        "spencer": {"handle": "@spencer.nyc"},
        "jade":    {"handle": "@its.jade_9"},
        "eleanor": {"handle": "@eleanor.core0"},
        "iris":    {"handle": "@iris.moods"},
        "leo":     {"handle": "@leo.thoughts0"},
    }


@pytest.fixture
def fixed_date() -> datetime:
    # 2026-05-24 是周日（weekday=6 → 周日）
    return datetime(2026, 5, 24, 9, 0)


class TestFormatBriefing:
    def test_header_has_correct_date(self, sample_personas, fixed_date) -> None:
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        first_line = result.split("\n")[0]
        assert first_line == "TK模板日推 | 5月24日（周日）"

    def test_persona_no_data_shows_zero_hit(self, sample_personas, fixed_date) -> None:
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "Sophie (@sophie.fits2)" in result
        assert "(24h 内 0 命中 ≤15s 竖版模板)" in result

    def test_persona_with_videos_shows_three_lines(self, sample_personas, fixed_date) -> None:
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title": "video A", "like_count": 12345,
                         "url": "https://www.tiktok.com/@a/video/1"},
                        {"title": "video B", "like_count": 567,
                         "url": "https://www.tiktok.com/@b/video/2"},
                        {"title": "video C", "like_count": 3500,
                         "url": "https://www.tiktok.com/@c/video/3"},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "video A | 1.2万赞 | https://www.tiktok.com/@a/video/1" in result
        assert "video B | 567赞 | https://www.tiktok.com/@b/video/2" in result
        assert "video C | 3.5K赞 | https://www.tiktok.com/@c/video/3" in result

    def test_persona_order_matches_spec(self, sample_personas, fixed_date) -> None:
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        # 检查前几个 persona 出现的顺序
        sophie_idx = result.find("Sophie (")
        ava_idx = result.find("Ava (")
        ezra_idx = result.find("Ezra (")
        leo_idx = result.find("Leo (")
        assert sophie_idx < ava_idx < ezra_idx, "Order: Sophie → Ava → Ezra"
        assert leo_idx > 0, "Leo 在末尾"
        assert leo_idx == max(sophie_idx, ava_idx, ezra_idx, leo_idx), "Leo 是最后"

    def test_all_26_personas_appear(self, sample_personas, fixed_date) -> None:
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        for pk in render_briefing.DISPLAY_ORDER:
            handle = sample_personas[pk]["handle"]
            cap = render_briefing.capitalize_persona(pk)
            assert f"{cap} ({handle})" in result, f"Missing {pk}"

    def test_title_cn_takes_priority_over_title(self, sample_personas, fixed_date) -> None:
        """v4.5.0：title_cn 存在时优先用，fallback 才用 raw title"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title": "raw english", "title_cn": "中文标题描述",
                         "like_count": 9641, "url": "https://x/1"},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "中文标题描述 | 9.6K赞 | https://x/1" in result
        assert "raw english" not in result

    def test_fallback_to_raw_title_when_no_title_cn(self, sample_personas, fixed_date) -> None:
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title": "raw english only", "like_count": 100, "url": "https://x"},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "raw english only | 100赞 | https://x" in result

    def test_fanpai_brief_shown_as_arrow_line(self, sample_personas, fixed_date) -> None:
        """v4.5.0：fanpai_brief 存在时在视频条目后加一行 → <brief>"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {
                            "title_cn": "测试中文标题",
                            "fanpai_brief": "Sophie 拍策展女孩在画廊门口的 outfit",
                            "like_count": 1000, "url": "https://x",
                        },
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "测试中文标题 | 1.0K赞 | https://x" in result
        assert "→ Sophie 拍策展女孩在画廊门口的 outfit" in result

    def test_duration_shown_after_likes(self, sample_personas, fixed_date) -> None:
        """v4.6.0：视频时长在点赞数后用 | 分隔显示"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title_cn": "测试", "like_count": 1000, "url": "https://x", "duration": 12},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "测试 | 1.0K赞 | 12s | https://x" in result

    def test_no_duration_no_extra_pipe(self, sample_personas, fixed_date) -> None:
        """duration 缺失或 0 时不显示，也不留多余 | 分隔"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title_cn": "测试", "like_count": 1000, "url": "https://x"},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "测试 | 1.0K赞 | https://x" in result
        assert "测试 | 1.0K赞 |  | https://x" not in result

    def test_viral_challenges_block_shown_at_top(self, sample_personas, fixed_date) -> None:
        """v4.6.0：全平台挑战块在简报顶部，标题 + 玩法 + 样本 + 仿拍"""
        data = {
            "viral_challenges": [
                {
                    "name": "Hold the moan（憋反应对比格式）",
                    "desc": "正式场合表情 vs 私下情绪反应",
                    "sample_url": "https://www.tiktok.com/@x/video/1",
                    "sample_likes": 500000,
                    "fanpai_brief": "26 人都能蹭，建议 Iris 先拍",
                },
            ],
            "personas": {},
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        # 挑战块在 Sophie segment 之前
        challenge_idx = result.find("🔥 全平台热门挑战 Top 3")
        sophie_idx = result.find("Sophie (")
        assert challenge_idx < sophie_idx
        # 挑战内容
        assert "1. Hold the moan（憋反应对比格式）" in result
        assert "玩法：正式场合表情 vs 私下情绪反应" in result
        assert "样本：https://www.tiktok.com/@x/video/1 | 50.0万赞" in result
        assert "仿拍：26 人都能蹭" in result
        assert "—— 以下为各赛道 Top 1 ——" in result

    def test_no_challenges_no_challenge_block(self, sample_personas, fixed_date) -> None:
        """没有 viral_challenges 字段时不显示挑战块"""
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "全平台热门挑战" not in result
        assert "—— 以下为各赛道 Top 1 ——" not in result

    def test_zero_hit_uses_v460_wording(self, sample_personas, fixed_date) -> None:
        """v4.6.0：0 命中文案改成「24h 内 0 命中 ≤15s 模板」"""
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "(24h 内 0 命中 ≤15s 竖版模板)" in result

    def test_fanpai_brief_empty_no_arrow_line(self, sample_personas, fixed_date) -> None:
        """没有 fanpai_brief 时不要打 → 空行"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [
                        {"title_cn": "测试", "like_count": 100, "url": "https://x"},
                    ],
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "→" not in result

    def test_no_decorative_artifacts(self, sample_personas, fixed_date) -> None:
        """没有 emoji 分组、统计行、低热度标记等装饰。"""
        data = {
            "personas": {
                "sophie": {
                    "videos": [{"title": "x", "like_count": 100, "url": "https://x"}],
                    "low_heat_warning": True,
                    "candidates_total": 5,
                    "max_likes": 100,
                },
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        # 不应出现这些
        assert "💄" not in result
        assert "💪" not in result
        assert "📱" not in result
        assert "🎭" not in result
        assert "⚠️" not in result
        assert "low_heat" not in result
        assert "候选" not in result
        assert "数据说明" not in result
        assert "人设：" not in result
        # 也不应出现 1./2./3. 编号
        assert not any(line.strip().startswith("1.") for line in result.split("\n"))

    def test_uses_at_handle_format(self, sample_personas, fixed_date) -> None:
        """格式是 Sophie (@sophie.fits2)，不是 Sophie | @sophie.fits2"""
        data = {"personas": {}}
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        assert "Sophie (@sophie.fits2)" in result
        assert "Sophie | @sophie.fits2" not in result

    def test_persona_missing_from_data_still_shows(self, sample_personas, fixed_date) -> None:
        """scout 输出可能没有某个 persona，简报仍要按 26 人顺序显示 (0 命中)。"""
        data = {
            "personas": {
                "sophie": {"videos": [{"title": "x", "like_count": 100, "url": "https://x"}]},
                # ava 缺失
            },
        }
        result = render_briefing.format_briefing(data, sample_personas, today=fixed_date)
        # ava 段仍应该出现
        assert "Ava (@ava.glow3)" in result
        # 且显示 0 命中
        ava_pos = result.find("Ava (@ava.glow3)")
        ezra_pos = result.find("Ezra (@ezra.style2)")
        ava_section = result[ava_pos:ezra_pos]
        assert "(24h 内 0 命中 ≤15s 竖版模板)" in ava_section


# ---------- 日期 / 星期映射 ----------


class TestDateMapping:
    @pytest.mark.parametrize("date,expected_wd", [
        (datetime(2026, 5, 18), "周一"),
        (datetime(2026, 5, 19), "周二"),
        (datetime(2026, 5, 20), "周三"),
        (datetime(2026, 5, 21), "周四"),
        (datetime(2026, 5, 22), "周五"),
        (datetime(2026, 5, 23), "周六"),
        (datetime(2026, 5, 24), "周日"),
    ])
    def test_weekday_chinese_mapping(self, date, expected_wd) -> None:
        # 直接验证 WEEKDAYS_CN 索引
        assert render_briefing.WEEKDAYS_CN[date.weekday()] == expected_wd
