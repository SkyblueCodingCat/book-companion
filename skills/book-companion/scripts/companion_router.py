#!/usr/bin/env python3
"""book-companion 状态调度入口。

这个脚本只做状态读写和推进调度。**它不产出任何讲解内容**——
讲解是 agent 读 notes/ 之后的智力工作，脚本化就会退化成模板套话。

## 与 vendored deep-reader 的边界

本脚本只读写 `<workspace>/companion/` 下的文件（读者的学习状态），
**从不写 deep-reader 的产物**（`source.txt`／`chapters.tsv`／`notes/`／
`synthesis.md`，即书的知识表示）。它只读取后者来校验阶段一是否完成
（`utils/workspace.py` 的 `check_ingest`）与定位笔记文件。

间隔复习的档位设计（1/3/7/21 天）参考 SebastianElvis/hammer 的 teach skill，
见 `references/teaching-loop.md` 的来源说明。vendor 基线见项目根 VENDOR.md。

所有子命令以 JSON 输出，供 agent 直接解析。

退出码：
    0  成功
    1  状态错误（工作区结构、状态文件内容、非法推进）
    2  argparse 的参数错误（由 argparse 自己产生，输出不是 JSON）
    3  阶段一未完成，不能开始导读

2 归 argparse 占用，所以阶段一判据用 3——否则 agent 无法区分
「书还没读完」和「命令敲错了」，这两种要采取的动作完全不同。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import markdown as md  # noqa: E402
from utils import workspace as ws  # noqa: E402
from utils.state import (  # noqa: E402
    Progress,
    Review,
    StateError,
    init_companion,
)

EXIT_STATE = 1
EXIT_ARGPARSE = 2  # argparse 保留，这里不主动使用
EXIT_INGEST = 3


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require_ingest(workspace: Path) -> None:
    check = ws.check_ingest(workspace)
    if not check.ok:
        _emit(
            {
                "ok": False,
                "reason": "阶段一未完成，不能开始导读",
                "detail": check.as_dict(),
                "next_action": "回到 deep-reader 跑完 study 模式，见 references/ingest.md",
            }
        )
        raise SystemExit(EXIT_INGEST)


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #


def cmd_init(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    _require_ingest(workspace)
    chapters = ws.read_chapters(workspace)
    result = init_companion(workspace, args.book, chapters, force=args.force)
    missing_notes = [ch.id for ch in chapters if ws.note_path(workspace, ch.id) is None]
    result["ok"] = True
    result["book"] = args.book
    if missing_notes:
        result["warning"] = (
            f"以下章节在 notes/ 下没有对应笔记，讲到时会没有素材: {', '.join(missing_notes)}"
        )
    _emit(result)


def cmd_where(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    progress = Progress.load(workspace)
    review = Review.load(workspace)
    due = review.due()
    nxt = progress.next_pending()

    _emit(
        {
            "ok": True,
            "book": progress.meta.get("书名") or progress.meta.get("工作区", ""),
            "counts": progress.counts(),
            "total": len(progress.chapters),
            "current": md.find_section(progress.text, "当前位置").strip(),
            "next_chapter": None
            if nxt is None
            else {"id": nxt["章节"], "title": nxt["标题"], "state": nxt["状态"]},
            "awaiting_recheck": [
                {"id": r["章节"], "first_try": r.get("首答正确率")}
                for r in progress.awaiting_recheck()
            ],
            "review_due": len(due),
            "review_due_points": [r["点"] for r in due],
            "stuck": md.find_section(progress.text, "卡壳摘要").strip(),
            "finished": nxt is None,
        }
    )


def cmd_next(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    progress = Progress.load(workspace)
    review = Review.load(workspace)
    due = review.due()

    recheck = progress.awaiting_recheck()
    row = progress.next_pending()
    if row is None:
        _emit(
            {
                "ok": True,
                "finished": True,
                "message": "没有待讲的新章节",
                "awaiting_recheck": [r["章节"] for r in recheck],
                "note": "若 awaiting_recheck 非空，这些章节讲完但未达标，等复习队列到期重考",
            }
        )
        return

    chapter_id = row["章节"]
    chapters = {c.id: c for c in ws.read_chapters(workspace)}
    chapter = chapters.get(chapter_id)
    note = ws.note_path(workspace, chapter_id)
    brief = ws.brief_path(workspace, chapter_id)

    _emit(
        {
            "ok": True,
            "finished": False,
            "chapter": {
                "id": chapter_id,
                "title": row["标题"],
                "state": row["状态"],
                "pages": None
                if chapter is None
                else [chapter.page_from, chapter.page_to],
            },
            "note_file": None if note is None else str(note),
            "brief_file": str(brief),
            "brief_exists": brief.is_file(),
            "review_due_first": len(due),
            "reminder": (
                "先清 2-3 道到期复习题再讲新章（teaching-loop.md A 阶段）"
                if due
                else "无到期复习，直接进 B 阶段导读"
            ),
        }
    )


def cmd_mark(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    progress = Progress.load(workspace)
    before = progress.row(args.chapter)["状态"]

    if not args.allow_regress:
        try:
            if ws.state_rank(args.state) < ws.state_rank(before) and args.state != "skipped":
                _emit(
                    {
                        "ok": False,
                        "reason": f"{args.chapter} 当前是 {before}，回退到 {args.state} 需要 --allow-regress",
                    }
                )
                raise SystemExit(EXIT_STATE)
        except ws.WorkspaceError as exc:
            _emit({"ok": False, "reason": str(exc)})
            raise SystemExit(EXIT_STATE) from exc

    row = progress.set_state(
        args.chapter, args.state, feynman=args.feynman, first_try=args.first_try
    )
    if args.stuck:
        progress.append_stuck(args.stuck)
    if args.current:
        progress.set_current(args.current)
    progress.save()

    _emit({"ok": True, "chapter": args.chapter, "from": before, "to": row["状态"], "row": row})


def cmd_review(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    review = Review.load(workspace)

    if args.review_action == "due":
        due = review.due(args.on)
        _emit(
            {
                "ok": True,
                "date": args.on or None,
                "count": len(due),
                "items": due,
                "take": due[: args.limit],
            }
        )
        return

    if args.review_action == "add":
        row = review.add(args.point, args.chapter, args.page or "")
        review.save()
        _emit({"ok": True, "action": "add", "row": row})
        return

    if args.review_action == "grade":
        row = review.grade(args.point, correct=args.correct)
        review.save()
        _emit({"ok": True, "action": "grade", "correct": args.correct, "row": row})
        return

    if args.review_action == "list":
        _emit(
            {
                "ok": True,
                "pending": review.pending,
                "graduated": review.graduated,
            }
        )
        return


def cmd_status(args: argparse.Namespace) -> None:
    workspace = ws.resolve(args.workspace)
    progress = Progress.load(workspace)
    review = Review.load(workspace)
    counts = progress.counts()
    total = len(progress.chapters)
    passed = counts["passed"]

    # 覆盖度的分母必须是**可讲授**单元数，不是总章节数。
    # 阶段一可能只精读了一部分（如方案 D 只做序言+第一部分），
    # 没有 notes/ 的章节在阶段二根本讲不了——把它们算进分母会让
    # 一个叫 honest_line 的字段给出误导性的数字。
    teachable, no_notes = [], []
    for row in progress.chapters:
        if row["状态"] == "skipped":
            continue
        (teachable if ws.note_path(workspace, row["章节"]) else no_notes).append(row)

    not_passed = [
        {"id": r["章节"], "title": r["标题"], "state": r["状态"]}
        for r in teachable
        if r["状态"] != "passed"
    ]
    no_feynman = [
        r["章节"]
        for r in progress.chapters
        if r["状态"] in ("checked", "passed") and r.get("费曼") != "已做"
    ]

    _emit(
        {
            "ok": True,
            "total_chapters": total,
            "teachable": len(teachable),
            "no_notes_count": len(no_notes),
            "no_notes": [r["章节"] for r in no_notes],
            "skipped": counts["skipped"],
            "passed": passed,
            "coverage": f"{passed}/{len(teachable)}",
            "counts": counts,
            "not_passed": not_passed,
            "missing_feynman": no_feynman,
            "review_pending": len(review.pending),
            "review_due": len(review.due()),
            "review_graduated": len(review.graduated),
            "honest_line": (
                f"可讲授 {len(teachable)} 单元，达标 {passed}，未达标 {len(not_passed)}；"
                f"另有 {len(no_notes)} 章无笔记（阶段一未覆盖）、"
                f"{counts['skipped']} 章已跳过；全书共 {total} 章。"
                f"复习队列 {len(review.pending)} 项"
            ),
        }
    )


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="companion_router.py",
        description="book-companion 状态调度。只管状态，不产出讲解内容。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_ws(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workspace", required=True, help="deep-reader 工作区目录")

    p_init = sub.add_parser("init", help="初始化 companion/ 导读工作区")
    add_ws(p_init)
    p_init.add_argument("--book", required=True, help="书名")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在的状态文件")
    p_init.set_defaults(func=cmd_init)

    p_where = sub.add_parser("where", help="读到哪了")
    add_ws(p_where)
    p_where.set_defaults(func=cmd_where)

    p_next = sub.add_parser("next", help="下一章该讲什么")
    add_ws(p_next)
    p_next.set_defaults(func=cmd_next)

    p_mark = sub.add_parser("mark", help="推进章节状态")
    add_ws(p_mark)
    p_mark.add_argument("--chapter", required=True)
    p_mark.add_argument("--state", required=True, choices=ws.CHAPTER_STATES)
    p_mark.add_argument("--feynman", choices=["已做", "未做"], default=None)
    p_mark.add_argument("--first-try", dest="first_try", default=None, help="如 3/5")
    p_mark.add_argument("--stuck", default=None, help="追加一条卡壳摘要")
    p_mark.add_argument("--current", default=None, help="覆盖「当前位置」区块内容")
    p_mark.add_argument("--allow-regress", action="store_true", help="允许状态回退")
    p_mark.set_defaults(func=cmd_mark)

    p_review = sub.add_parser("review", help="复习队列")
    review_sub = p_review.add_subparsers(dest="review_action", required=True)

    r_due = review_sub.add_parser("due", help="列出到期项")
    add_ws(r_due)
    r_due.add_argument("--on", default=None, help="指定日期 YYYY-MM-DD，默认今天")
    r_due.add_argument("--limit", type=int, default=3, help="本次建议取几道")
    r_due.set_defaults(func=cmd_review)

    r_add = review_sub.add_parser("add", help="卡壳点入队")
    add_ws(r_add)
    r_add.add_argument("--point", required=True)
    r_add.add_argument("--chapter", required=True)
    r_add.add_argument("--page", default=None)
    r_add.set_defaults(func=cmd_review)

    r_grade = review_sub.add_parser("grade", help="复习结果升档或退档")
    add_ws(r_grade)
    r_grade.add_argument("--point", required=True)
    grade_group = r_grade.add_mutually_exclusive_group(required=True)
    grade_group.add_argument("--correct", dest="correct", action="store_true")
    grade_group.add_argument("--wrong", dest="correct", action="store_false")
    r_grade.set_defaults(func=cmd_review)

    r_list = review_sub.add_parser("list", help="列出整个队列")
    add_ws(r_list)
    r_list.set_defaults(func=cmd_review)

    p_status = sub.add_parser("status", help="覆盖度报告")
    add_ws(p_status)
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (StateError, ws.WorkspaceError, md.StateFormatError) as exc:
        _emit({"ok": False, "reason": str(exc)})
        return EXIT_STATE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
