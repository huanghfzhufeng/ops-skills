#!/usr/bin/env python3
"""
render_briefing.py - 把 scout_strict.py 的 JSON 输出渲染成 TK 模板日推简报。

严格按用户原 spec 输出格式，不带 emoji 分组、不带统计行、不带 ⚠️ low_heat 标。
理由：之前靠 Claude 在 SKILL.md 里手工拼简报，连续两次偏离原 spec。代码固化
后下游不管谁调用都拿到完全一致的格式。

用法（两种）：
  # 1. stdin（用管道）
  python3 scout_strict.py --keywords kw.yaml | python3 render_briefing.py

  # 2. 文件
  python3 scout_strict.py --keywords kw.yaml > result.json
  python3 render_briefing.py --json result.json

输出格式（严格按用户 spec）：
  TK模板日推 | M月D日（周X）

  Sophie (@sophie.fits2)

  <title> | <likes> | <url>
  <title> | <likes> | <url>
  <title> | <likes> | <url>

  Ava (@ava.glow3)

  (24h 内 0 命中)

  ...（26 人按固定顺序展开）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


# 用户原 spec 里 26 人的展示顺序（赛道松散分组 + 人设流转）
DISPLAY_ORDER = [
    "sophie", "ava", "ezra", "riley", "clara", "leila", "ryan", "max",
    "mia", "charlotte", "priya", "ro", "silver", "nari", "avery", "joey",
    "caden", "mason", "kai", "jesse", "emma", "spencer", "jade", "eleanor",
    "iris", "leo",
]

WEEKDAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------- 工具函数 ----------


def fmt_likes(n: int) -> str:
    """点赞数字中文化：12345 → '1.2万赞'，3456 → '3.5K赞'，234 → '234赞'。"""
    if n >= 10000:
        return f"{n / 10000:.1f}万赞"
    if n >= 1000:
        return f"{n / 1000:.1f}K赞"
    return f"{n}赞"


def fmt_duration(seconds: int) -> str:
    """视频时长：12 → '12s'，65 → '1m5s'，0 / 缺失 → ''。"""
    if not seconds or seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m{s}s" if s else f"{m}m"


def capitalize_persona(pk: str) -> str:
    """'sophie' → 'Sophie'。简单首字母大写。"""
    return pk[0].upper() + pk[1:] if pk else pk


def clean_title(title: str) -> str:
    """折叠空白字符，空标题给个 placeholder。"""
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    return cleaned if cleaned else "(无标题)"


# ---------- personas.yaml 加载 ----------


def load_personas(path: Path) -> dict[str, dict[str, str]]:
    """读 personas.yaml 返回 {persona_key: {handle, persona, ...}}"""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("personas", {})


def find_personas_yaml() -> Path | None:
    """
    优先级查找 personas.yaml：
    1. 用户级配置 ~/.config/ops-skills/personas.yaml
    2. plugin 自带 <this-script>/../us-trend-scout/personas.yaml
    """
    user_path = Path.home() / ".config" / "ops-skills" / "personas.yaml"
    if user_path.exists():
        return user_path
    here = Path(__file__).resolve().parent
    plugin_path = here.parent / "us-trend-scout" / "personas.yaml"
    if plugin_path.exists():
        return plugin_path
    return None


# ---------- 核心渲染 ----------


def format_briefing(
    data: dict[str, Any],
    personas: dict[str, dict[str, str]],
    today: datetime | None = None,
) -> str:
    """
    把 scout_strict.py 的 JSON 输出渲染成简报。

    Args:
        data: scout_strict.py 输出的 JSON dict（顶层含 'personas' key）
        personas: personas.yaml 解析出来的 {persona_key: persona_def}
        today: 简报日期，默认今天

    Returns:
        简报文本（按用户原 spec 格式）
    """
    if today is None:
        today = datetime.now()

    mon = today.strftime("%-m")
    day = today.strftime("%-d")
    wd = WEEKDAYS_CN[today.weekday()]

    lines: list[str] = [f"TK模板日推 | {mon}月{day}日（{wd}）", ""]

    # v4.6.0：顶部全平台热门挑战 Top 3（Claude 主线填到 data['viral_challenges']）
    challenges = data.get("viral_challenges") or []
    if challenges:
        lines.append("🔥 全平台热门挑战 Top 3")
        lines.append("")
        for i, ch in enumerate(challenges[:3], 1):
            name = ch.get("name", "").strip() or "(挑战名缺失)"
            desc = ch.get("desc", "").strip()
            sample_url = ch.get("sample_url", "").strip()
            sample_likes = ch.get("sample_likes")
            fanpai = ch.get("fanpai_brief", "").strip()
            lines.append(f"{i}. {name}")
            if desc:
                lines.append(f"   玩法：{desc}")
            if sample_url:
                likes_str = f" | {fmt_likes(sample_likes)}" if sample_likes else ""
                lines.append(f"   样本：{sample_url}{likes_str}")
            if fanpai:
                lines.append(f"   仿拍：{fanpai}")
            lines.append("")
        lines.append("—— 以下为各赛道 Top 1 ——")
        lines.append("")

    persona_data = data.get("personas", {})

    for pk in DISPLAY_ORDER:
        pdef = personas.get(pk, {})
        handle = pdef.get("handle", f"@{pk}")
        cap = capitalize_persona(pk)

        lines.append(f"{cap} ({handle})")
        lines.append("")

        info = persona_data.get(pk)
        if not info or not info.get("videos"):
            lines.append("(24h 内 0 命中 ≤15s 模板)")
        else:
            for v in info["videos"]:
                # v4.5.0：优先用 title_cn（Claude 翻译后写回 JSON），fallback 用 raw title
                title = clean_title(v.get("title_cn") or v.get("title", ""))
                likes = fmt_likes(v.get("like_count") or 0)
                url = v.get("url", "")
                # v4.6.0：视频时长显示在点赞数后
                dur = fmt_duration(v.get("duration") or 0)
                dur_str = f" | {dur}" if dur else ""
                lines.append(f"{title} | {likes}{dur_str} | {url}")
                # v4.5.0：如果有 fanpai_brief（Claude 生成的仿拍建议），加一行 →
                brief = (v.get("fanpai_brief") or "").strip()
                if brief:
                    lines.append(f"→ {brief}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------- CLI ----------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 scout_strict.py 的 JSON 渲染成 TK 模板日推简报"
    )
    parser.add_argument(
        "--json", type=Path,
        help="scout_strict.py 输出 JSON 文件路径（默认从 stdin 读）",
    )
    parser.add_argument(
        "--personas", type=Path,
        help="personas.yaml 路径（默认按 ~/.config/ops-skills/ → plugin 自带顺序查找）",
    )
    args = parser.parse_args()

    # 1. 加载 scout 数据
    if args.json:
        if not args.json.exists():
            print(f"ERROR: JSON file not found: {args.json}", file=sys.stderr)
            sys.exit(2)
        with args.json.open(encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    # 2. 加载 personas
    personas_path = args.personas or find_personas_yaml()
    if not personas_path or not personas_path.exists():
        print(
            "ERROR: personas.yaml not found. Looked in:\n"
            "  ~/.config/ops-skills/personas.yaml\n"
            "  <skill-dir>/../us-trend-scout/personas.yaml",
            file=sys.stderr,
        )
        sys.exit(2)
    personas = load_personas(personas_path)

    # 3. 渲染
    print(format_briefing(data, personas), end="")


if __name__ == "__main__":
    main()
