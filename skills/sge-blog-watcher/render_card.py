#!/usr/bin/env python3
"""render_card.py - 把翻译后的博客 JSON 渲染成飞书卡片文本（一篇一文件）。

格式 100% 代码固化，Claude 只产出内容字段（title_cn/summary_cn/tldr_lines），
不碰排版。这样多篇推送格式一致，不会被即兴加工带偏。

输入 translated.json（Claude 按 translate_prompt.md 生成）：
{
  "posts": [
    {
      "url": "https://www.socialgrowthengineers.com/...",
      "published": "2026-05-27T20:59:00",
      "section": "strategy",
      "read_minutes": 2,
      "title_cn": "4M Views：创作者光芒盖过了网站（Studora 拆解）",
      "summary_cn": "Studora 最强创作者不靠学习技巧，靠'专注'时刻取胜。",
      "tldr_lines": ["**🔑 核心**：...", "**📌 钩子**：...", "**💡 洞察**：..."]
    }
  ]
}

为每篇写出 <outdir>/card-NNN.txt（push_feishu_card.py 直接吃），
并把清单打印到 stdout（每行 `文件路径<TAB>URL`），供推送循环 + commit 用。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# SGE 文章 article:section → 中文分类（对应站点导航栏）
SECTION_CN: dict[str, str] = {
    "case study": "案例研究",
    "strategy": "战略",
    "format": "格式",
    "the growth lab": "增长实验室",
    "trend": "趋势",
    "pov": "观点",
    "opinion": "观点",
    "newbie": "新人",
    "gated": "深度报告",
}


def fmt_date(published: str | None) -> str:
    if not published:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", published)
    return m.group(1) if m else ""


def section_cn(section: str | None) -> str:
    if not section:
        return "新模版"
    return SECTION_CN.get(section.strip().lower(), section)


def render_one(post: dict) -> str:
    """单篇 → 飞书卡片文本。第一行是标题（push_feishu_card 会当 header）。"""
    title = (post.get("title_cn") or post.get("title") or "SGE 新模版").strip()

    meta_bits = [f"**{section_cn(post.get('section'))}**"]
    date = fmt_date(post.get("published"))
    if date:
        meta_bits.append(f"发布于 {date}")
    read = post.get("read_minutes")
    if read:
        meta_bits.append(f"阅读 {read} 分钟")

    lines = [title, " · ".join(meta_bits), ""]

    summary = (post.get("summary_cn") or "").strip()
    if summary:
        lines.extend([f"> {summary}", ""])

    for tldr in post.get("tldr_lines") or []:
        if tldr and tldr.strip():
            lines.append(tldr.strip())

    lines.extend(["", f"🔗 [阅读原文]({post.get('url', '')})"])
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="渲染 SGE 博客飞书卡片（一篇一文件）")
    parser.add_argument("--json", required=True, type=Path, help="translated.json 路径")
    parser.add_argument("--outdir", required=True, type=Path, help="卡片输出目录")
    args = parser.parse_args()

    data = json.loads(args.json.read_text(encoding="utf-8"))
    posts = data.get("posts", [])
    args.outdir.mkdir(parents=True, exist_ok=True)

    for i, post in enumerate(posts, 1):
        card_path = args.outdir / f"card-{i:03d}.txt"
        card_path.write_text(render_one(post), encoding="utf-8")
        print(f"{card_path}\t{post.get('url', '')}")


if __name__ == "__main__":
    main()
