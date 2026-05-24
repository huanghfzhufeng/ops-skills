#!/usr/bin/env python3
"""
validate_translated.py - 协议层验证 translated.json schema

防御 Claude 主线翻译漏字段或格式漂移。在 render_briefing.py 之前跑一次，
不合格立即报错，让 Claude 必须补全。

用法：
  python3 validate_translated.py --json translated.json

退出码：
  0 = 全部 OK
  1 = schema 有错
  2 = 字段缺失但可恢复（render_briefing 会 fallback 到英文 raw title）

检查内容：
  - viral_challenges：name / desc / sample_url / fanpai_brief 字段必有
  - 每个 persona 的每条 video：必有 title_cn 和 fanpai_brief
  - title_cn 长度 5-80 中文字符（防 Claude 输出空或超长）
  - fanpai_brief 必含 persona name（句首"<Persona> 拍..."）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CHALLENGE_REQUIRED_FIELDS = {"name", "desc", "sample_url", "fanpai_brief"}
VIDEO_REQUIRED_TRANSLATION_FIELDS = {"title_cn", "fanpai_brief"}

MIN_TITLE_CN_LEN = 5     # 中文字符数下限
MAX_TITLE_CN_LEN = 80    # 中文字符数上限
MAX_FANPAI_BRIEF_LEN = 100  # 仿拍建议字符数上限


def validate_challenges(challenges: list[dict]) -> list[str]:
    """验证 viral_challenges 数组，返回错误信息 list（空 = 全 OK）."""
    errors: list[str] = []
    if not isinstance(challenges, list):
        errors.append("viral_challenges 必须是 array，当前类型: " + type(challenges).__name__)
        return errors
    if len(challenges) == 0:
        errors.append("viral_challenges 为空（应该有 Top 3）")
        return errors
    if len(challenges) > 5:
        errors.append(f"viral_challenges 超过 5 条（{len(challenges)}），简报不该太长")
    for i, ch in enumerate(challenges):
        missing = CHALLENGE_REQUIRED_FIELDS - set(ch.keys())
        if missing:
            errors.append(f"challenge #{i+1} 缺字段: {missing}")
            continue
        name = (ch.get("name") or "").strip()
        if not name:
            errors.append(f"challenge #{i+1} name 为空")
        elif " " not in name and len(name) < 5:
            errors.append(f"challenge #{i+1} name 太短（'{name}'）应为有意义的挑战名")
        desc = (ch.get("desc") or "").strip()
        if not desc:
            errors.append(f"challenge #{i+1} desc 为空（必须 1-2 句玩法描述）")
        sample = (ch.get("sample_url") or "").strip()
        if not sample.startswith("https://"):
            errors.append(f"challenge #{i+1} sample_url 不是 https URL: '{sample[:60]}'")
        brief = (ch.get("fanpai_brief") or "").strip()
        if not brief:
            errors.append(f"challenge #{i+1} fanpai_brief 为空")
        elif len(brief) > MAX_FANPAI_BRIEF_LEN:
            errors.append(
                f"challenge #{i+1} fanpai_brief 超长（{len(brief)}>{MAX_FANPAI_BRIEF_LEN}）"
            )
    return errors


def validate_persona_video(
    persona: str, idx: int, video: dict
) -> tuple[list[str], list[str]]:
    """
    验证单条 video 的翻译字段，返回 (errors, warnings)。
    errors = 必须修复的；warnings = 可降级用 raw title 但会丢质量。
    """
    errors: list[str] = []
    warnings: list[str] = []

    missing = VIDEO_REQUIRED_TRANSLATION_FIELDS - set(video.keys())
    if missing:
        warnings.append(f"  {persona} video #{idx+1} 缺翻译字段: {missing}")
        return errors, warnings

    title_cn = (video.get("title_cn") or "").strip()
    if not title_cn:
        warnings.append(f"  {persona} video #{idx+1} title_cn 为空，将 fallback 到英文")
    elif len(title_cn) < MIN_TITLE_CN_LEN:
        errors.append(
            f"  {persona} video #{idx+1} title_cn 太短（'{title_cn}' < {MIN_TITLE_CN_LEN}）"
        )
    elif len(title_cn) > MAX_TITLE_CN_LEN:
        errors.append(
            f"  {persona} video #{idx+1} title_cn 超长（{len(title_cn)}>{MAX_TITLE_CN_LEN}）"
        )

    brief = (video.get("fanpai_brief") or "").strip()
    if not brief:
        warnings.append(f"  {persona} video #{idx+1} fanpai_brief 为空，简报不会有 → 行")
    elif len(brief) > MAX_FANPAI_BRIEF_LEN:
        errors.append(
            f"  {persona} video #{idx+1} fanpai_brief 超长（{len(brief)}>{MAX_FANPAI_BRIEF_LEN}）"
        )
    else:
        # fanpai_brief 应含 "Persona 名 拍..." 句首格式
        persona_cap = persona[0].upper() + persona[1:] if persona else persona
        if not brief.startswith(persona_cap):
            warnings.append(
                f"  {persona} video #{idx+1} fanpai_brief 句首不是 '{persona_cap} 拍...'"
            )

    return errors, warnings


def validate_translated_json(data: dict) -> tuple[list[str], list[str]]:
    """主验证。返回 (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # viral_challenges（可选但强烈建议）
    if "viral_challenges" in data:
        challenge_errs = validate_challenges(data["viral_challenges"])
        errors.extend([f"  viral_challenges: {e}" for e in challenge_errs])
    else:
        warnings.append("  缺 viral_challenges 字段（v4.6.0 起强烈建议加，挑战板块不会显示）")

    # personas[*].videos[*]
    personas = data.get("personas", {})
    if not personas:
        warnings.append("  personas dict 为空")
    for persona, info in personas.items():
        for idx, video in enumerate(info.get("videos", [])):
            v_errors, v_warnings = validate_persona_video(persona, idx, video)
            errors.extend(v_errors)
            warnings.extend(v_warnings)

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="协议层验证 translated.json schema")
    parser.add_argument("--json", required=True, type=Path,
                        help="translated.json 路径")
    parser.add_argument("--quiet", action="store_true",
                        help="只输出错误数和退出码")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"ERROR: 文件不存在: {args.json}", file=sys.stderr)
        sys.exit(1)

    with args.json.open(encoding="utf-8") as f:
        data = json.load(f)

    errors, warnings = validate_translated_json(data)

    if not args.quiet:
        if warnings:
            print(f"⚠️  Warnings ({len(warnings)}):")
            for w in warnings:
                print(w)
        if errors:
            print(f"\n❌  Errors ({len(errors)}):")
            for e in errors:
                print(e)
        if not errors and not warnings:
            print("✅  translated.json schema 完美通过")
        elif not errors:
            print(f"\n✓ schema OK with {len(warnings)} warnings（可降级用 raw title）")

    if errors:
        sys.exit(1)
    elif warnings:
        sys.exit(2)  # 警告但可用
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
