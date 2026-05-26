#!/usr/bin/env python3
"""push_feishu_card.py - 把简报 .txt 推为飞书富文本卡片（interactive markdown）。

v4.8.0 起两个 skill 共用这个脚本。相比 v4.5.0 的 plain text webhook：
- 支持 **加粗**、[链接文本](url)、字号层级
- 标题独立成 header（带颜色），主体 markdown 渲染
- 飞书 markdown 元素上限 ~30K 字符，单份简报 5-8K 完全够用

用法：
    python3 push_feishu_card.py \\
        --briefing /tmp/briefing-tk.txt \\
        --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/...." \\
        --title "TK模板日推 | 5月25日"        # 可选；默认用第一行

退出码：
    0 = 飞书返回 code:0
    1 = 推送失败 / 网络错误 / 飞书报错
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


HEADER_COLOR_BY_KEYWORD: dict[str, str] = {
    # 标题里含关键词时选用对应配色，落到 default 是蓝色
    "热点": "blue",
    "趋势": "blue",
    "模板": "wathet",   # 浅蓝
    "TK模板": "wathet",
}


def pick_header_color(title: str) -> str:
    for kw, color in HEADER_COLOR_BY_KEYWORD.items():
        if kw in title:
            return color
    return "blue"


def split_title_and_body(briefing: str) -> tuple[str, str]:
    """第一行当 header title，剩余当 markdown body。"""
    text = briefing.strip()
    if not text:
        return "Briefing", ""
    parts = text.split("\n", 1)
    title = parts[0].strip()
    body = parts[1].lstrip("\n") if len(parts) > 1 else ""
    return title, body


def build_card(briefing: str, title_override: str | None = None) -> dict[str, Any]:
    """简报文本 → 飞书 interactive card JSON payload。"""
    auto_title, body = split_title_and_body(briefing)
    title = (title_override or auto_title).strip()
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": pick_header_color(title),
            },
            "elements": [
                {"tag": "markdown", "content": body or "(空简报)"}
            ],
        },
    }


def push(webhook: str, payload: dict[str, Any], timeout: int = 15) -> tuple[bool, str]:
    """POST 到飞书。返回 (success, response_body)。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        return False, f"URLError: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected error: {e}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False, body
    success = int(data.get("code", -1)) == 0
    return success, body


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把简报 .txt 推为飞书富文本卡片（interactive markdown）",
    )
    parser.add_argument("--briefing", required=True, type=Path,
                        help="简报纯文本文件路径")
    parser.add_argument("--webhook", required=True,
                        help="飞书 webhook URL")
    parser.add_argument("--title",
                        help="卡片 header 标题（可选，默认用简报第一行）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印 payload JSON，不实际推送（本地调试用）")
    args = parser.parse_args()

    if not args.briefing.exists():
        print(f"ERROR: briefing file not found: {args.briefing}", file=sys.stderr)
        sys.exit(2)

    text = args.briefing.read_text(encoding="utf-8")
    payload = build_card(text, args.title)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    ok, body = push(args.webhook, payload)
    print(f"飞书响应：{body}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
