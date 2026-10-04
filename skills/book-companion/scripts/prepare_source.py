#!/usr/bin/env python3
"""阶段一的转换入口 —— CJK 感知的分页。

## 为什么不直接用 deep-reader 的 prepare-text.sh

那个脚本对 EPUB / DOCX / TXT / MD 用 awk 的 `NF` 按空白分词，每 500 词一页。
**中文没有空格分词**，一整段中文 NF = 1，于是「500 词一页」退化成
「500 段一页」——一本中文书会全部塞进第 1 页。

实测：5325 字符的中文 EPUB 被算成 209 words、1 页。

后果不是显示问题。页码是整个方法论的坐标系：只有 1 页意味着 `read-pages.sh`
无法定点回查、`verify-quotes.sh` 的页码校验失去意义、导读层所有 `(p. N)`
全部指向 p.1。

## 分派

| 格式 | 走哪条路 | 理由 |
| --- | --- | --- |
| PDF | 委托 deep-reader prepare-text.sh | pdftotext 用真实 form feed 分页，正确 |
| EPUB / DOCX | pandoc 转纯文本 + 本脚本分页 | 绕开 NF 计数 |
| TXT / MD | 直接读 + 本脚本分页 | 同上 |

不修改 vendor 的 deep-reader，这样上游更新仍可直接合并。

## 计量口径

CJK 字符各计 1 个单位，拉丁词各计 1 个单位，每页默认 500 个单位。
切页只发生在安全边界（CJK 字符之后、或空白处），**绝不改动原文字符**。

输出 JSON 与 deep-reader 的 prepare-text.sh 字段兼容，额外给出
`units`、`cjk_chars`、`cjk_ratio`、`units_per_page`、`pager`。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

PAGE_MARKER = "[[page {}]]"  # 必须匹配 deep-reader 的 ^\[\[page [0-9]+\]\]$
DEFAULT_UNITS_PER_PAGE = 500

DELEGATED = {"pdf"}
# pandoc 实测支持的电子书输入格式（`pandoc --list-input-formats`）。
# MOBI / AZW / AZW3 不在其中，需先用 Calibre 的 ebook-convert 转成 EPUB。
PANDOC_FORMATS = {"epub", "docx", "fb2", "rtf", "html", "htm", "odt"}
PLAIN_FORMATS = {"txt", "md", "markdown"}

# 需要显式 -f 的格式：pandoc 不总能从扩展名推断
PANDOC_EXPLICIT_FORMAT = {"fb2": "fb2", "rtf": "rtf", "htm": "html"}

# est_tokens 口径：中文 1 字约 0.75 token，拉丁 1 词约 1.33 token。
CJK_TOKENS_PER_CHAR = 0.75
LATIN_TOKENS_PER_WORD = 1.33


class PrepareError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# CJK 判定与计量
# --------------------------------------------------------------------------- #

_CJK_BLOCKS = (
    (0x2E80, 0x2EFF),    # CJK 部首补充
    (0x3000, 0x303F),    # CJK 标点
    (0x3040, 0x30FF),    # 日文假名
    (0x3100, 0x312F),    # 注音
    (0x3130, 0x318F),    # 韩文兼容字母
    (0x3400, 0x4DBF),    # 扩展 A
    (0x4E00, 0x9FFF),    # 统一汉字
    (0xA000, 0xA4CF),    # 彝文
    (0xAC00, 0xD7AF),    # 韩文音节
    (0xF900, 0xFAFF),    # 兼容汉字
    (0xFF00, 0xFFEF),    # 全角/半角
    (0x20000, 0x2FA1F),  # 扩展 B 及以上
)


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    for lo, hi in _CJK_BLOCKS:
        if lo <= code <= hi:
            return True
    return False


def measure(text: str) -> tuple[int, int]:
    """返回 (cjk 字符数, 拉丁词数)。拉丁词 = 连续的非空白非 CJK 串。"""
    cjk = 0
    words = 0
    in_word = False
    for ch in text:
        if is_cjk(ch):
            cjk += 1
            in_word = False
        elif ch.isspace():
            in_word = False
        else:
            if not in_word:
                words += 1
                in_word = True
    return cjk, words


def unit_weight(text: str) -> int:
    cjk, words = measure(text)
    return cjk + words


# --------------------------------------------------------------------------- #
# 分页
# --------------------------------------------------------------------------- #


def _cut_points(para: str, budgets: list[int]) -> list[int]:
    """按给定配额序列算出切分位置。只在安全边界切，返回字符下标列表。"""
    cuts: list[int] = []
    if not budgets:
        return cuts

    budget_iter = iter(budgets)
    budget = next(budget_iter)
    used = 0
    in_word = False

    for i, ch in enumerate(para):
        if is_cjk(ch):
            used += 1
            in_word = False
            safe = True
        elif ch.isspace():
            in_word = False
            safe = True
        else:
            if not in_word:
                used += 1
                in_word = True
            safe = False

        if used >= budget and safe and i + 1 < len(para):
            cuts.append(i + 1)
            used = 0
            try:
                budget = next(budget_iter)
            except StopIteration:
                break
    return cuts


def paginate(
    paragraphs: list[str],
    units_per_page: int,
    force_break: set[int] | None = None,
) -> list[list[str]]:
    """把段落列表铺进页。段落级优先，只有单段超过一页才内部切。

    force_break 里的段落索引会强制开新页——用来让页边界和章节边界对齐。
    不对齐的后果是每章切片头部带上一章的尾巴、尾部被下一章切走，
    逐章笔记会被系统性污染。
    """
    pages: list[list[str]] = [[]]
    used = 0
    force_break = force_break or set()

    for index, para in enumerate(paragraphs):
        if index in force_break and any(l.strip() for l in pages[-1]):
            pages.append([])
            used = 0

        if not para.strip():
            pages[-1].append("")
            continue

        weight = unit_weight(para)

        # 放不下且当前页已有内容 → 先翻页
        if used > 0 and used + weight > units_per_page:
            pages.append([])
            used = 0

        if weight <= units_per_page:
            pages[-1].append(para)
            used += weight
            continue

        # 单段超过一页：内部切，第一片用当前页剩余配额
        first = units_per_page - used if used else units_per_page
        remaining = weight - first
        budgets = [first] + [units_per_page] * (remaining // units_per_page + 1)
        cuts = _cut_points(para, budgets)

        prev = 0
        for idx, cut in enumerate(cuts):
            pages[-1].append(para[prev:cut].rstrip())
            pages.append([])
            prev = cut
        tail = para[prev:]
        if tail:
            pages[-1].append(tail)
            used = unit_weight(tail)
        else:
            used = 0

    if pages and not any(line.strip() for line in pages[-1]):
        pages.pop()
    return pages or [[""]]


def render(pages: list[list[str]]) -> str:
    out: list[str] = []
    for number, lines in enumerate(pages, 1):
        out.append(PAGE_MARKER.format(number))
        out.extend(lines)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# 取文本
# --------------------------------------------------------------------------- #


def extract_text(path: Path, ext: str) -> str:
    if ext in PLAIN_FORMATS:
        return path.read_text(encoding="utf-8", errors="replace")

    if shutil.which("pandoc") is None:
        raise PrepareError(
            f"缺少 pandoc，无法处理 .{ext}。\n"
            f"  安装指引: 运行 ./install.sh --check，它会按你的平台给出命令\n"
            f"  或见 https://pandoc.org/installing.html\n"
            f"  降级路径见 references/ingest.md"
        )

    cmd = ["pandoc", "-t", "plain", "--wrap=none"]
    if ext in PANDOC_EXPLICIT_FORMAT:
        cmd += ["-f", PANDOC_EXPLICIT_FORMAT[ext]]
    cmd.append(str(path))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PrepareError(f"pandoc 转换失败: {proc.stderr.strip()}")
    return proc.stdout


def delegate_pdf(path: Path, workspace: Path | None) -> dict:
    script = Path(__file__).resolve().parent.parent.parent / "deep-reader" / "scripts" / "prepare-text.sh"
    if not script.is_file():
        raise PrepareError(f"找不到 vendored deep-reader 脚本: {script}")

    cmd = ["bash", str(script), str(path)]
    if workspace is not None:
        cmd.append(str(workspace))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        raise PrepareError(
            f"deep-reader prepare-text.sh 退出码 {proc.returncode}。"
            "缺 pdftotext 时执行 `brew install poppler`。"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PrepareError(f"deep-reader 输出不是合法 JSON: {proc.stdout!r}") from exc
    payload["pager"] = "deep-reader/pdftotext（真实分页）"
    payload["units_per_page"] = None
    payload["chapter_aligned"] = None  # 真实分页，不适用

    # PDF 是最可能静默缺字的来源，必须审计
    source_txt = Path(payload.get("source_txt", ""))
    if source_txt.is_file():
        payload["quality"] = audit_text(
            source_txt.read_text(encoding="utf-8", errors="replace")
        )
    return payload


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def audit_text(text: str) -> dict:
    """检测字体缺字的痕迹。

    PDF 最危险的失败模式不是乱码而是**静默缺字**：字体没有某个汉字的字形时，
    渲染会留下空白，pdftotext 提取出来就是空格。句子读着依然通顺，不报错、
    不留标记。实测 cupsfilter 生成的中文 PDF 丢了 32% 的汉字而毫无提示。

    判据：规范的中文正文里，汉字与汉字之间不应出现空格。统计这种间隔的
    密度即可把缺字暴露出来。注意 pdftotext -layout 会保留排版缩进，
    所以只统计**行内**的汉字间空格，忽略行首缩进。
    """
    cjk_gap = re.compile(r"[\u4e00-\u9fff][ \t]+[\u4e00-\u9fff]")
    gaps = 0
    cjk = 0
    for line in text.splitlines():
        if line.startswith("[[page "):
            continue
        body = line.lstrip()
        gaps += len(cjk_gap.findall(body))
        cjk += sum(1 for c in body if 0x4E00 <= ord(c) <= 0x9FFF)

    per_1k = round(gaps / max(cjk / 1000, 1e-9), 1) if cjk else 0.0
    # 阈值由实测定标：Chrome 规范 PDF 约 0.3/千字，cupsfilter 缺字版约 50/千字
    if cjk < 200:
        level = "样本过小"
    elif per_1k >= 10:
        level = "可疑：疑似字体缺字，务必抽查原文"
    elif per_1k >= 3:
        level = "留意：汉字间空格偏多，建议抽查几页"
    else:
        level = "正常"
    return {"cjk_gaps": gaps, "gaps_per_1k_cjk": per_1k, "verdict": level}


def mode_hint(est_tokens: int) -> str:
    if est_tokens < 50_000:
        return "small — 篇幅小，overview 模式可能就够；陪读仍需 study"
    if est_tokens <= 150_000:
        return "medium — study 模式，顺序读"
    return "large — study 模式，考虑逐章 subagent fan-out"


def compute_breaks(
    paragraphs: list[str], pattern: str | None, after_line: int
) -> set[int]:
    """算出需要强制开新页的段落索引。

    after_line 用来跳过目录区——目录里的章节标题和正文里的长得一样，
    不跳过会把目录切成几十个短页。行号是 1-based，对应源文件的行。
    """
    if not pattern:
        return set()
    regex = re.compile(pattern)
    return {
        i
        for i, para in enumerate(paragraphs)
        if i + 1 > after_line and regex.match(para.strip())
    }


def prepare(
    input_path: Path,
    workspace: Path | None,
    units_per_page: int,
    force: bool,
    break_before: str | None = None,
    break_after_line: int = 0,
) -> dict:
    if not input_path.is_file():
        raise PrepareError(f"找不到输入文件: {input_path}")

    ext = input_path.suffix.lower().lstrip(".")
    if ext in DELEGATED:
        return delegate_pdf(input_path, workspace)

    if ext not in PANDOC_FORMATS and ext not in PLAIN_FORMATS:
        hint = ""
        if ext in {"mobi", "azw", "azw3", "prc"}:
            hint = (
                "\n  MOBI / AZW 系列需先转换：\n"
                "    brew install --cask calibre\n"
                f"    ebook-convert 书.{ext} 书.epub\n"
                "  然后对生成的 .epub 重跑本脚本。"
            )
        raise PrepareError(
            f"不支持的格式 .{ext}。\n"
            f"  直读: {', '.join(sorted(PLAIN_FORMATS))}\n"
            f"  经 pandoc: {', '.join(sorted(PANDOC_FORMATS))}\n"
            f"  经 pdftotext: pdf{hint}"
        )

    if workspace is None:
        workspace = input_path.parent / f"{input_path.stem}-notes"
    (workspace / "notes").mkdir(parents=True, exist_ok=True)
    workspace = workspace.resolve()
    source_txt = workspace / "source.txt"

    if source_txt.is_file() and source_txt.stat().st_size > 0 and not force:
        text = source_txt.read_text(encoding="utf-8", errors="replace")
        pages = sum(
            1 for ln in text.splitlines() if ln.startswith("[[page ") and ln.endswith("]]")
        )
        cjk, words = measure(text)
        print(f"工作区已就绪，报告现有统计: {source_txt}", file=sys.stderr)
        est = round(cjk * CJK_TOKENS_PER_CHAR + words * LATIN_TOKENS_PER_WORD)
        return {
            "workspace": str(workspace),
            "source_txt": str(source_txt),
            "format": ext,
            "pages": pages,
            "synthetic_pages": True,
            "words": words,
            "units": cjk + words,
            "cjk_chars": cjk,
            "cjk_ratio": round(cjk / max(cjk + words, 1), 3),
            "est_tokens": est,
            "units_per_page": units_per_page,
            "pager": "book-companion/CJK 感知（已存在）",
            "quality": audit_text(text),
            "mode_hint": mode_hint(est),
            "existing": True,
        }

    print(f"转换 {input_path.name}（.{ext}）到 {workspace}", file=sys.stderr)
    raw = extract_text(input_path, ext)
    raw = unicodedata.normalize("NFC", raw)
    paragraphs = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    breaks = compute_breaks(paragraphs, break_before, break_after_line)
    pages = paginate(paragraphs, units_per_page, breaks)
    source_txt.write_text(render(pages), encoding="utf-8")

    cjk, words = measure(raw)
    est = round(cjk * CJK_TOKENS_PER_CHAR + words * LATIN_TOKENS_PER_WORD)

    return {
        "workspace": str(workspace),
        "source_txt": str(source_txt),
        "format": ext,
        "pages": len(pages),
        "synthetic_pages": True,
        "words": words,
        "units": cjk + words,
        "cjk_chars": cjk,
        "cjk_ratio": round(cjk / max(cjk + words, 1), 3),
        "est_tokens": est,
        "units_per_page": units_per_page,
        "pager": "book-companion/CJK 感知",
        "chapter_aligned": bool(breaks),
        "forced_breaks": len(breaks),
        "quality": audit_text(raw),
        "mode_hint": mode_hint(est),
        "existing": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare_source.py",
        description="阶段一转换入口。PDF 委托 deep-reader，其余格式走 CJK 感知分页。",
    )
    parser.add_argument("input", help="书籍文件 (pdf/epub/docx/txt/md)")
    parser.add_argument("workspace", nargs="?", default=None, help="工作区目录，默认 <书名>-notes")
    parser.add_argument(
        "--units-per-page",
        type=int,
        default=DEFAULT_UNITS_PER_PAGE,
        help=f"每页单位数，CJK 字符与拉丁词各计 1（默认 {DEFAULT_UNITS_PER_PAGE}）",
    )
    parser.add_argument("--force", action="store_true", help="已有 source.txt 也重新转换")
    parser.add_argument(
        "--break-before",
        default=None,
        metavar="REGEX",
        help="匹配该正则的行强制开新页，让页边界与章节边界对齐。"
        r"例：'^(第\d+章\s|序言$|结语$|附录[AB]\s)'",
    )
    parser.add_argument(
        "--break-after-line",
        type=int,
        default=0,
        metavar="N",
        help="--break-before 只在源文件第 N 行之后生效（1-based），用来跳过目录区。"
        "目录里的章节标题与正文同形，不跳过会把目录切成几十个短页。",
    )
    args = parser.parse_args(argv)

    if args.units_per_page < 50:
        print(
            json.dumps({"ok": False, "reason": "units-per-page 不应小于 50"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    try:
        if args.break_before and Path(args.input).suffix.lower() == ".pdf":
            print(
                "警告：PDF 走 deep-reader 的真实分页，--break-before 不生效（也不需要）。",
                file=sys.stderr,
            )
        payload = prepare(
            Path(args.input).expanduser(),
            Path(args.workspace).expanduser() if args.workspace else None,
            args.units_per_page,
            args.force,
            args.break_before,
            args.break_after_line,
        )
    except PrepareError as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
