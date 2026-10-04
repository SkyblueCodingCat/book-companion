#!/usr/bin/env python3
"""CJK 感知的引文校验 —— deep-reader verify-quotes.sh 的中文替代。

## 为什么需要它

`deep-reader/scripts/verify-quotes.sh` 的 normalize() 里有一行

    gsub(/[^a-z0-9 -]/, "", r)

它删除所有非 ASCII 字母数字的字符。中文引文归一化后变成空字符串，
于是一条都提取不到——实测对中文工作区输出 `{"checked": 0}`。

引文校验是防编造引文和防页码错位的**唯一自动手段**。它对中文静默失效，
意味着阶段一的质量保障在中文书上等于不存在，而"失效且不报错"比"不存在"更危险。

本脚本对拉丁文同样适用（归一化更宽容一些），所以中英文书都可以只用这一个。

## 判定

| 结果 | 含义 | 处理 |
| --- | --- | --- |
| ok | 在引用的页范围内找到 | 无需处理 |
| near | 在别的页找到 | 页码写错了，改页码 |
| cross | 只在相邻页拼接后找到 | 引文跨页被 [[page N]] 切断，改成页内连续片段或转述 |
| fail | 全书都找不到 | 疑似编造或改写过，必须回原文核对 |

near / cross / fail 任何一项非零都以退出码 1 结束——照 deep-reader 的语义，
这些都必须修到退出 0 为止。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# "引文" (p. N) / (pp. A-B)，支持中英文引号与 en dash
QUOTE_RE = re.compile(
    r"[\"“]([^\"”\n]{4,}?)[\"”]\s*[（(]\s*(?:p\.|pp\.|tr\.)\s*(\d+)"
    r"(?:\s*[-–—]\s*(\d+))?\s*[）)]"
)
PAGE_RE = re.compile(r"^\[\[page (\d+)\]\]$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def norm(text: str) -> str:
    """归一化：全角转半角、去空白、只留字母数字与汉字。

    去空白是关键——中文文本里的空白没有词边界意义，而 source.txt 里
    同一句话可能因为分页而被插入换行。
    """
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if ch.isalnum()).lower()


def load_pages(source: Path) -> dict[int, str]:
    pages: dict[int, str] = {}
    current = 0
    buf: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        m = PAGE_RE.match(line)
        if m:
            if current:
                pages[current] = norm("".join(buf))
            current = int(m.group(1))
            buf = []
        else:
            buf.append(line)
    if current:
        pages[current] = norm("".join(buf))
    return pages


def extract(md: Path) -> list[tuple[str, int, int | None, int]]:
    """从 markdown 提取 (引文, 起始页, 结束页, 行号)，跳过代码块。"""
    out = []
    in_fence = False
    for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in QUOTE_RE.finditer(line):
            quote, start, end = m.group(1), int(m.group(2)), m.group(3)
            out.append((quote, start, int(end) if end else None, lineno))
    return out


def check_one(
    quote: str, start: int, end: int | None, pages: dict[int, str]
) -> tuple[str, str]:
    """返回 (状态, 说明)。"""
    needle = norm(quote)
    if not needle:
        return "fail", "归一化后为空（引文可能只有标点）"

    span = list(range(start, (end or start) + 1))

    # 1. 引用的页范围内
    for p in span:
        if needle in pages.get(p, ""):
            return "ok", f"命中 p.{p}"

    # 2. 引用范围内相邻页拼接（跨页被页标记切断）
    for p in span:
        joined = pages.get(p, "") + pages.get(p + 1, "")
        if needle in joined:
            return "cross", f"跨 p.{p}/p.{p + 1} 边界，单页内不连续"

    # 3. 全书其它页
    hits = [p for p, body in pages.items() if needle in body]
    if hits:
        return "near", f"实际在 p.{', p.'.join(map(str, sorted(hits)[:3]))}"

    # 4. 全书相邻页拼接
    for p in sorted(pages):
        if needle in pages.get(p, "") + pages.get(p + 1, ""):
            return "near", f"跨 p.{p}/p.{p + 1}，且与标注页 {start} 不符"

    return "fail", "全书未找到"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="CJK 感知的引文校验，替代 deep-reader 的 verify-quotes.sh"
    )
    ap.add_argument("workspace", help="deep-reader 工作区目录")
    ap.add_argument("--quiet", action="store_true", help="只输出 JSON 汇总")
    args = ap.parse_args()

    ws = Path(args.workspace).expanduser().resolve()
    source = ws / "source.txt"
    if not source.is_file():
        print(json.dumps({"ok": False, "reason": f"找不到 {source}"}, ensure_ascii=False))
        return 1

    pages = load_pages(source)
    md_files = sorted(p for p in ws.rglob("*.md"))
    if not md_files:
        print(json.dumps({"checked": 0, "reason": "工作区没有 markdown 文件"}, ensure_ascii=False))
        return 0

    tally = {"ok": 0, "near": 0, "cross": 0, "fail": 0}
    problems: list[dict] = []

    for md in md_files:
        for quote, start, end, lineno in extract(md):
            status, detail = check_one(quote, start, end, pages)
            tally[status] += 1
            if status != "ok":
                problems.append(
                    {
                        "file": str(md.relative_to(ws)),
                        "line": lineno,
                        "status": status,
                        "page_cited": start if end is None else f"{start}-{end}",
                        "detail": detail,
                        "quote": quote[:60] + ("…" if len(quote) > 60 else ""),
                    }
                )

    checked = sum(tally.values())
    if not args.quiet and problems:
        print(f"共 {checked} 条引文，{len(problems)} 条需处理：\n", file=sys.stderr)
        for p in problems:
            print(
                f"  [{p['status'].upper():5}] {p['file']}:{p['line']}  "
                f"标注 p.{p['page_cited']} — {p['detail']}\n"
                f"          「{p['quote']}」",
                file=sys.stderr,
            )
        print("", file=sys.stderr)

    print(
        json.dumps(
            {
                "checked": checked,
                **tally,
                "pages_indexed": len(pages),
                "files": len(md_files),
                "clean": not problems,
            },
            ensure_ascii=False,
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
