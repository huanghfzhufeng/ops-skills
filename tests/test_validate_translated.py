"""validate_translated.py 单测（协议层验证）"""
import pytest

import validate_translated as vt

pytestmark = pytest.mark.unit


# ---------- validate_challenges ----------


class TestValidateChallenges:
    def test_valid_three_challenges(self) -> None:
        challenges = [
            {
                "name": "CORTIS Wiggle-Ears",
                "desc": "K-pop 团编排 cross-niche 挑战",
                "sample_url": "https://www.tiktok.com/@x/video/1",
                "fanpai_brief": "26 人都能蹭，先 Nari / Eleanor 拍",
            }
        ] * 3
        assert vt.validate_challenges(challenges) == []

    def test_empty_list_fails(self) -> None:
        errors = vt.validate_challenges([])
        assert any("为空" in e for e in errors)

    def test_not_array_fails(self) -> None:
        errors = vt.validate_challenges({"foo": "bar"})  # type: ignore[arg-type]
        assert any("array" in e for e in errors)

    def test_missing_required_field(self) -> None:
        challenges = [{"name": "X"}]  # 缺 desc / sample_url / fanpai_brief
        errors = vt.validate_challenges(challenges)
        assert any("缺字段" in e for e in errors)

    def test_sample_url_must_be_https(self) -> None:
        challenges = [{
            "name": "X X X",
            "desc": "y",
            "sample_url": "tiktok.com/discover/x",  # 无 https://
            "fanpai_brief": "z",
        }]
        errors = vt.validate_challenges(challenges)
        assert any("https" in e for e in errors)

    def test_fanpai_brief_too_long(self) -> None:
        challenges = [{
            "name": "X X X",
            "desc": "y",
            "sample_url": "https://x.com/v/1",
            "fanpai_brief": "z" * 200,
        }]
        errors = vt.validate_challenges(challenges)
        assert any("超长" in e for e in errors)

    def test_too_many_challenges_warns(self) -> None:
        challenges = [{
            "name": f"X{i} 挑战", "desc": "y",
            "sample_url": "https://x.com/v/1", "fanpai_brief": "z",
        } for i in range(7)]
        errors = vt.validate_challenges(challenges)
        assert any("超过 5 条" in e for e in errors)


# ---------- validate_persona_video ----------


class TestValidatePersonaVideo:
    def test_valid_video(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "quiet luxury 哲学金句",
            "fanpai_brief": "Sophie 拍策展女孩 hot take",
        })
        assert errors == []
        assert warnings == []

    def test_missing_translation_fields_is_warning(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title": "raw english",
            "like_count": 100,
        })
        assert errors == []
        assert any("缺翻译字段" in w for w in warnings)

    def test_title_cn_too_short(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "短",
            "fanpai_brief": "Sophie 拍 x",
        })
        assert any("太短" in e for e in errors)

    def test_title_cn_too_long(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "x" * 100,
            "fanpai_brief": "Sophie 拍 x",
        })
        assert any("超长" in e for e in errors)

    def test_fanpai_brief_must_start_with_persona(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "测试 title",
            "fanpai_brief": "随便写的不以 Sophie 开头",
        })
        assert any("句首不是" in w for w in warnings)
        # 但这不是 error（可降级使用）
        assert errors == []

    def test_fanpai_brief_too_long(self) -> None:
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "测试",
            "fanpai_brief": "Sophie 拍" + "x" * 200,
        })
        assert any("超长" in e for e in errors)

    def test_empty_title_cn_is_warning_not_error(self) -> None:
        """空 title_cn 让 render_briefing fallback 到英文 raw title，不算 fatal"""
        errors, warnings = vt.validate_persona_video("sophie", 0, {
            "title_cn": "",
            "fanpai_brief": "Sophie 拍 x",
        })
        assert errors == []
        assert any("fallback" in w for w in warnings)


# ---------- validate_translated_json ----------


class TestValidateTranslatedJson:
    def test_complete_valid(self) -> None:
        data = {
            "viral_challenges": [{
                "name": "X X 挑战",
                "desc": "y",
                "sample_url": "https://x.com/v/1",
                "fanpai_brief": "26 人都能蹭",
            }] * 3,
            "personas": {
                "sophie": {
                    "videos": [{
                        "title_cn": "测试中文标题",
                        "fanpai_brief": "Sophie 拍策展女孩",
                    }]
                }
            }
        }
        errors, warnings = vt.validate_translated_json(data)
        assert errors == []
        assert warnings == []

    def test_missing_viral_challenges_is_warning(self) -> None:
        data = {
            "personas": {
                "sophie": {"videos": [{
                    "title_cn": "测试", "fanpai_brief": "Sophie 拍 x"
                }]}
            }
        }
        errors, warnings = vt.validate_translated_json(data)
        assert any("缺 viral_challenges" in w for w in warnings)

    def test_empty_personas_is_warning(self) -> None:
        data = {"personas": {}}
        errors, warnings = vt.validate_translated_json(data)
        assert any("personas dict 为空" in w for w in warnings)
