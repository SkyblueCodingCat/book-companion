#!/usr/bin/env python3
"""从 EPUB 提取插图并关联图号 —— 补上管线丢图的缺口。

## 为什么需要它

vendored 的 deep-reader 管线（`../../deep-reader/scripts/prepare-text.sh`）
与本项目的 `prepare_source.py` 都把一切转成纯文本，**图像全部丢失**。
这不是 vendor 的缺陷——它面向的是以文字论证为主的书；但对依赖图的书，
损失是实质性的：《思考，快与慢》图 5（认知放松的原因和结果）是第 5 章的结构
骨架、图 9（走廊透视）是第 9 章的核心演示，正文反复回指却无图可看。

本脚本是纯增量能力，不改动也不替代 vendor 的任何行为。vendor 基线见
项目根目录的 `VENDOR.md`。

EPUB 本质是 zip，插图原样躺在里面。本脚本解包、提图、并从 XHTML 的上下文
推断每张图的图号与所属章节。

## 图号关联是启发式的，必须人工确认

做法是在 `<img>` 标签前后若干字符内搜索「图N」字样。这对规范排版的书有效，
但**不可靠**：图注可能缺失、可能出现邻近图的编号、同一图号可能重复出现。

因此输出的 `figures/INDEX.md` 里每条都带 `confidence` 与 `confirmed` 两栏。
**agent 必须用图像查看工具实际打开每张图核对内容**，确认后把 `confirmed`
改为 `yes`。未经确认的图号不得写进笔记——实测本项目九张图里有三张的
文字重建与实际内容不符，只有打开看才能发现。

## 用法

    python3 scripts/extract_figures.py <书.epub> <工作区目录>
    python3 scripts/extract_figures.py <书.epub> <工作区> --all   # 含未编号的图
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
FIG_RE = re.compile(r"图\s*([0-9]{1,2})")
CHAP_RE = re.compile(r"(第\d+章|序言|结语|附录[AB])")
TAG_RE = re.compile(r"<[^>]+>")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
CONTEXT = 600


class FigureError(RuntimeError):
    pass


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", fragment))).strip()


def scan(root: Path) -> list[dict]:
    """遍历 XHTML，为每个 img 标签推断图号与章节。"""
    docs = sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in {".xhtml", ".html", ".htm"}
    )
    found: list[dict] = []
    for doc in docs:
        raw = doc.read_text(encoding="utf-8", errors="replace")
        for m in IMG_RE.finditer(raw):
            name = m.group(1).split("/")[-1]
            if Path(name).suffix.lower() not in IMAGE_EXT:
                continue
            ctx = plain(raw[max(0, m.start() - CONTEXT) : m.end() + CONTEXT])
            nums = FIG_RE.findall(ctx)
            chaps = CHAP_RE.findall(plain(raw[: m.start()]))

            fig_no, confidence = None, "none"
            if nums:
                tally = Counter(nums).most_common()
                fig_no = int(tally[0][0])
                # 上下文里同一编号出现多次，且没有竞争编号 → 可信度较高
                if tally[0][1] >= 2 and len(tally) == 1:
                    confidence = "high"
                elif len(tally) == 1:
                    confidence = "medium"
                else:
                    confidence = "low"

            found.append(
                {
                    "source_file": name,
                    "doc": doc.name,
                    "figure": fig_no,
                    "confidence": confidence,
                    "chapter_hint": chaps[-1] if chaps else None,
                    "caption_context": ctx[:120],
                }
            )
    return found


def extract(epub: Path, workspace: Path, include_all: bool) -> dict:
    if not epub.is_file():
        raise FigureError(f"找不到 EPUB: {epub}")
    if not zipfile.is_zipfile(epub):
        raise FigureError(f"不是合法的 zip/EPUB: {epub}")

    figures_dir = workspace / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="epub-fig-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(epub) as zf:
            zf.extractall(root)

        entries = scan(root)
        images = {p.name: p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXT}

        written, skipped, seen = [], [], set()
        for e in entries:
            src = images.get(e["source_file"])
            if src is None:
                continue
            if e["figure"] is None:
                if not include_all:
                    skipped.append(e["source_file"])
                    continue
                target = figures_dir / f"unnumbered-{e['source_file']}"
            else:
                target = figures_dir / f"fig{e['figure']:02d}{src.suffix.lower()}"
                if target.name in seen:
                    # 同一图号撞车：保留首个，其余加后缀待人工裁决
                    target = figures_dir / f"fig{e['figure']:02d}-dup-{e['source_file']}"
                    e["confidence"] = "low"
            seen.add(target.name)
            shutil.copy2(src, target)
            e["saved_as"] = target.name
            written.append(e)

        total_images = len(images)

    write_index(figures_dir, written, epub)
    return {
        "ok": True,
        "epub": str(epub),
        "figures_dir": str(figures_dir),
        "images_in_epub": total_images,
        "extracted": len(written),
        "unnumbered_skipped": len(skipped),
        "by_confidence": dict(Counter(e["confidence"] for e in written)),
        "figures": sorted(
            (
                {k: e[k] for k in ("figure", "saved_as", "confidence", "chapter_hint")}
                for e in written
            ),
            key=lambda d: (d["figure"] is None, d["figure"] or 0),
        ),
        "next_action": (
            "用图像查看工具逐张打开核对内容，确认后把 figures/INDEX.md 的 "
            "confirmed 改为 yes。未确认的图号不得写进笔记。"
        ),
    }


def write_index(figures_dir: Path, entries: list[dict], epub: Path) -> None:
    lines = [
        "# 插图索引",
        "",
        f"- 来源: `{epub.name}`",
        f"- 提取数量: {len(entries)}",
        "",
        "## 确认状态",
        "",
        "`confidence` 是脚本对图号推断的自信度（基于 `<img>` 上下文里「图N」字样的",
        "出现情况），**不代表内容正确**。`confirmed` 必须由 agent 实际打开图片核对后填写。",
        "",
        "> 实测提醒：本书九张图里有三张的纯文字重建与实际内容不符",
        "> （图 5 原因项多列一条、图 6 漏掉中间一框、图 8 的线段是散乱而非并排）。",
        "> 只有打开看才能发现。",
        "",
        "| 图号 | 文件 | confidence | confirmed | 章节线索 | 图注上下文 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in sorted(entries, key=lambda d: (d["figure"] is None, d["figure"] or 0)):
        fig = f"图 {e['figure']}" if e["figure"] is not None else "未编号"
        ctx = e["caption_context"][:46].replace("|", "｜")
        lines.append(
            f"| {fig} | `{e['saved_as']}` | {e['confidence']} | no | "
            f"{e['chapter_hint'] or '—'} | {ctx} |"
        )
    (figures_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从 EPUB 提取插图并关联图号，补上管线丢图的缺口"
    )
    ap.add_argument("epub", help="EPUB 文件路径")
    ap.add_argument("workspace", help="deep-reader 工作区目录")
    ap.add_argument(
        "--all", action="store_true", dest="include_all",
        help="同时提取无法关联图号的图片（封面、装饰图等）",
    )
    args = ap.parse_args()

    try:
        payload = extract(
            Path(args.epub).expanduser(),
            Path(args.workspace).expanduser(),
            args.include_all,
        )
    except FigureError as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
