#!/usr/bin/env python3
"""book-companion 自包含回归。

在临时目录里造一个合成 deep-reader 工作区跑全链路，不依赖真实书，
不读写项目目录。既是回归，也是安装体检——先报环境，再跑用例。

用法:
    python3 tests/run_regression.py
    python3 tests/run_regression.py --report tests/regression_results.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ROUTER = SKILL_DIR / "scripts" / "companion_router.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from utils import markdown as md  # noqa: E402
from utils import workspace as ws  # noqa: E402
from utils.state import INTERVAL_SEQ, Progress, Review  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))
    line = f"{status:<5} {name}"
    if detail and status != "PASS":
        line += f" -- {detail}"
    print(line)


def check(name: str, condition: bool, detail: str = "") -> bool:
    record("PASS" if condition else "FAIL", name, detail)
    return condition


def run_router(*args: str, expect_code: int = 0) -> dict:
    """调 router 并解析 JSON。退出码不符预期时把原始输出带进异常。"""
    proc = subprocess.run(
        [sys.executable, str(ROUTER), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != expect_code:
        raise AssertionError(
            f"退出码 {proc.returncode} != {expect_code}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"输出不是合法 JSON: {proc.stdout!r}") from exc


# --------------------------------------------------------------------------- #
# 合成工作区
# --------------------------------------------------------------------------- #

CHAPTERS = [
    ("ch01", 1, 10, "阅读的活动"),
    ("ch02", 11, 20, "阅读的层次"),
    ("ch03", 21, 30, "检视阅读"),
]


def make_workspace(root: Path, *, with_notes: bool = True) -> Path:
    workspace = root / "synthetic-notes"
    (workspace / "notes").mkdir(parents=True)

    pages = []
    for page in range(1, 31):
        pages.append(f"[[page {page}]]")
        pages.append(f"这是第 {page} 页的合成正文，用于回归测试。")
    (workspace / "source.txt").write_text("\n".join(pages), encoding="utf-8")

    (workspace / "chapters.tsv").write_text(
        "".join(f"{c}\t{a}\t{b}\t{t}\n" for c, a, b, t in CHAPTERS),
        encoding="utf-8",
    )

    if with_notes:
        for cid, _, _, title in CHAPTERS:
            (workspace / "notes" / f"{cid}-{cid}-slug.md").write_text(
                f"# {cid} {title}\n\n合成笔记正文。\n", encoding="utf-8"
            )
    (workspace / "synthesis.md").write_text("# 综合\n\n合成内容。\n", encoding="utf-8")
    return workspace


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #


def test_markdown_roundtrip() -> None:
    columns = ["点", "章节", "档位"]
    rows = [{"点": "甲", "章节": "ch01", "档位": "1天"}]
    table = md.render_table(columns, rows)
    check("markdown 表格 round-trip", md.parse_table(table) == rows)

    doc = "# T\n\n## A\n\n内容 A\n\n## B\n\n内容 B\n"
    check("find_section 取正文", md.find_section(doc, "A").strip() == "内容 A")
    updated = md.replace_section(doc, "A", "新内容")
    check(
        "replace_section 只改目标区块",
        md.find_section(updated, "A").strip() == "新内容"
        and md.find_section(updated, "B").strip() == "内容 B",
    )

    try:
        md.parse_table("| a | b |\n| 1 | 2 |")
        check("缺分隔行应报错", False, "没有抛 StateFormatError")
    except md.StateFormatError:
        check("缺分隔行应报错", True)

    try:
        md.parse_table("| a | b |\n| --- | --- |\n| 1 |")
        check("列数不匹配应报错", False, "没有抛 StateFormatError")
    except md.StateFormatError:
        check("列数不匹配应报错", True)


def test_ingest_gate(root: Path) -> None:
    incomplete = make_workspace(root / "incomplete", with_notes=False)
    result = ws.check_ingest(incomplete)
    check(
        "notes/ 为空时阶段一判据不通过",
        not result.ok and any("notes/" in m for m in result.missing),
        str(result.missing),
    )

    payload = run_router(
        "init", "--workspace", str(incomplete), "--book", "合成书", expect_code=3
    )
    check(
        "init 在阶段一未完成时退出码 3（与 argparse 的 2 区分）",
        payload.get("ok") is False and "阶段一" in payload.get("reason", ""),
        json.dumps(payload, ensure_ascii=False),
    )

    complete = make_workspace(root / "complete")
    ok_result = ws.check_ingest(complete)
    check(
        "完整工作区判据通过",
        ok_result.ok and ok_result.chapters_count == 3 and ok_result.notes_count == 3,
        str(ok_result.as_dict()),
    )


def test_full_flow(workspace: Path) -> None:
    payload = run_router("init", "--workspace", str(workspace), "--book", "合成书")
    check(
        "init 建立三个状态文件",
        payload["ok"] and set(payload["created"]) == {"progress.md", "learner.md", "review.md"},
        json.dumps(payload, ensure_ascii=False),
    )
    companion = workspace / "companion"
    check(
        "init 建立 briefs/ 与 sessions/",
        (companion / "briefs").is_dir() and (companion / "sessions").is_dir(),
    )
    check("init 无缺笔记告警", "warning" not in payload, payload.get("warning", ""))

    payload = run_router("init", "--workspace", str(workspace), "--book", "合成书")
    check(
        "init 幂等（已存在不覆盖）",
        payload["created"] == [] and len(payload["skipped"]) == 3,
        json.dumps(payload, ensure_ascii=False),
    )

    payload = run_router("where", "--workspace", str(workspace))
    check(
        "where 指向 ch01",
        payload["next_chapter"]["id"] == "ch01"
        and payload["counts"]["pending"] == 3
        and payload["finished"] is False,
        json.dumps(payload["next_chapter"], ensure_ascii=False),
    )

    payload = run_router("next", "--workspace", str(workspace))
    check(
        "next 给出笔记与页码",
        payload["chapter"]["id"] == "ch01"
        and payload["chapter"]["pages"] == [1, 10]
        and payload["note_file"] is not None
        and payload["brief_exists"] is False,
        json.dumps(payload["chapter"], ensure_ascii=False),
    )

    for state in ("briefed", "taught", "checked"):
        run_router(
            "mark", "--workspace", str(workspace), "--chapter", "ch01", "--state", state
        )
    payload = run_router(
        "mark",
        "--workspace",
        str(workspace),
        "--chapter",
        "ch01",
        "--state",
        "passed",
        "--feynman",
        "已做",
        "--first-try",
        "4/5",
    )
    check(
        "mark 推进到 passed 并记录费曼",
        payload["to"] == "passed" and payload["row"]["费曼"] == "已做",
        json.dumps(payload["row"], ensure_ascii=False),
    )

    payload = run_router(
        "mark",
        "--workspace",
        str(workspace),
        "--chapter",
        "ch01",
        "--state",
        "taught",
        expect_code=1,
    )
    check(
        "状态回退需 --allow-regress",
        payload["ok"] is False and "allow-regress" in payload["reason"],
        payload.get("reason", ""),
    )

    payload = run_router(
        "mark",
        "--workspace",
        str(workspace),
        "--chapter",
        "ch01",
        "--state",
        "taught",
        "--allow-regress",
    )
    check("显式允许后可回退", payload["to"] == "taught")
    run_router(
        "mark", "--workspace", str(workspace), "--chapter", "ch01", "--state", "passed"
    )

    payload = run_router("where", "--workspace", str(workspace))
    check(
        "ch01 达标后 where 指向 ch02",
        payload["next_chapter"]["id"] == "ch02" and payload["counts"]["passed"] == 1,
        json.dumps(payload["next_chapter"], ensure_ascii=False),
    )

    payload = run_router(
        "mark",
        "--workspace",
        str(workspace),
        "--chapter",
        "ch02",
        "--state",
        "checked",
        "--stuck",
        "检视阅读与略读的区别 (p. 41) — 两次提示后仍答偏",
    )
    progress_text = (workspace / "companion" / "progress.md").read_text(encoding="utf-8")
    check(
        "卡壳摘要写盘",
        "检视阅读与略读的区别" in md.find_section(progress_text, "卡壳摘要"),
    )

    # 回归护栏：checked 不得阻塞推进。
    # 早期实现把 checked 也算作"下一个该做的"，一旦某章未达标，
    # next/where 就永久停在那一章，读者再也走不到下一章。
    payload = run_router("where", "--workspace", str(workspace))
    check(
        "checked 章节不阻塞推进（where 跳过它指向下一个待讲章）",
        payload["next_chapter"] is not None and payload["next_chapter"]["id"] == "ch03",
        json.dumps(payload["next_chapter"], ensure_ascii=False),
    )
    check(
        "checked 章节仍出现在 awaiting_recheck 里不被丢失",
        [r["id"] for r in payload["awaiting_recheck"]] == ["ch02"],
        json.dumps(payload["awaiting_recheck"], ensure_ascii=False),
    )
    payload = run_router("next", "--workspace", str(workspace))
    check(
        "next 同样跳过 checked",
        payload["chapter"]["id"] == "ch03",
        json.dumps(payload["chapter"], ensure_ascii=False),
    )

    payload = run_router("status", "--workspace", str(workspace))
    check(
        "status 覆盖度与未达标清单",
        payload["coverage"] == "1/3"
        and {c["id"] for c in payload["not_passed"]} == {"ch02", "ch03"}
        and "ch02" in payload["missing_feynman"],
        json.dumps(payload, ensure_ascii=False),
    )
    # 覆盖度分母必须排除无笔记章节，否则 honest_line 会给出误导性数字。
    # 合成工作区的 ch00-ch03 都有笔记，这里临时移走一份制造 no_notes 场景。
    note = next((workspace / "notes").glob("ch03-*.md"))
    stashed = note.with_suffix(".md.stashed")
    note.rename(stashed)
    payload = run_router("status", "--workspace", str(workspace))
    check(
        "status 分母排除无笔记章节",
        payload["coverage"] == "1/2"
        and payload["no_notes_count"] == 1
        and payload["no_notes"] == ["ch03"]
        and payload["total_chapters"] == 3,
        json.dumps(
            {k: payload[k] for k in ("coverage", "no_notes", "total_chapters")},
            ensure_ascii=False,
        ),
    )
    check(
        "honest_line 区分可讲授与无笔记",
        "无笔记" in payload["honest_line"] and "可讲授" in payload["honest_line"],
        payload["honest_line"],
    )
    stashed.rename(note)


def test_review_queue(workspace: Path) -> None:
    point = "检视阅读与略读的区别"
    payload = run_router(
        "review", "add", "--workspace", str(workspace),
        "--point", point, "--chapter", "ch02", "--page", "p. 41",
    )
    check(
        "入队首档为 1天",
        payload["row"]["档位"] == INTERVAL_SEQ[0] and payload["row"]["连续答对"] == "0",
        json.dumps(payload["row"], ensure_ascii=False),
    )

    future = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    payload = run_router("review", "due", "--workspace", str(workspace))
    check("当天不到期", payload["count"] == 0, json.dumps(payload, ensure_ascii=False))
    payload = run_router("review", "due", "--workspace", str(workspace), "--on", future)
    check("次日之后到期", payload["count"] == 1 and payload["items"][0]["点"] == point)

    payload = run_router(
        "review", "grade", "--workspace", str(workspace), "--point", point, "--correct"
    )
    check(
        "答对升档到 3天",
        payload["row"]["档位"] == "3天" and payload["row"]["连续答对"] == "1",
        json.dumps(payload["row"], ensure_ascii=False),
    )

    payload = run_router(
        "review", "grade", "--workspace", str(workspace), "--point", point, "--wrong"
    )
    check(
        "答错退档并把连续答对归零",
        payload["row"]["档位"] == "1天" and payload["row"]["连续答对"] == "0",
        json.dumps(payload["row"], ensure_ascii=False),
    )

    review = Review.load(workspace)
    for tier in INTERVAL_SEQ[1:]:
        review.grade(point, correct=True)
        assert review.pending[0]["档位"] == tier, (tier, review.pending)
    graduated = review.grade(point, correct=True)
    review.save()
    check(
        "走完 21天档后毕业",
        graduated["点"] == point
        and not review.pending
        and review.graduated[0]["点"] == point,
        json.dumps(graduated, ensure_ascii=False),
    )

    payload = run_router(
        "review", "grade", "--workspace", str(workspace),
        "--point", "不存在的点", "--correct",
        expect_code=1,
    )
    check(
        "给不存在的点评分应报错",
        payload["ok"] is False and "不存在的点" in payload["reason"],
        payload.get("reason", ""),
    )

    payload = run_router(
        "review", "add", "--workspace", str(workspace),
        "--point", "甲", "--chapter", "ch03", "--page", "p. 50",
    )
    payload = run_router(
        "review", "add", "--workspace", str(workspace),
        "--point", "甲", "--chapter", "ch03", "--page", "p. 50",
    )
    check(
        "重复入队等于退档处理，不产生重复行",
        len(Review.load(workspace).pending) == 1,
        json.dumps(payload, ensure_ascii=False),
    )


def test_corruption_detected(workspace: Path) -> None:
    path = workspace / "companion" / "progress.md"
    backup = path.read_text(encoding="utf-8")

    path.write_text(backup.replace("| passed |", "| 完事了 |"), encoding="utf-8")
    payload = run_router("where", "--workspace", str(workspace), expect_code=1)
    check(
        "非法章节状态被拒绝而非静默跳过",
        payload["ok"] is False and "非法" in payload["reason"],
        payload.get("reason", ""),
    )

    path.write_text("# 进度\n\n没有任何区块\n", encoding="utf-8")
    payload = run_router("where", "--workspace", str(workspace), expect_code=1)
    check("缺失区块被拒绝", payload["ok"] is False, payload.get("reason", ""))

    path.write_text(backup, encoding="utf-8")
    payload = run_router("where", "--workspace", str(workspace))
    check("恢复后可正常读取", payload["ok"] is True)


def test_templates_present() -> None:
    expected = {
        "progress.md",
        "learner.md",
        "review.md",
        "chapter-brief.md",
        "session.md",
    }
    found = {p.name for p in (SKILL_DIR / "templates").glob("*.md")}
    check("模板齐全", expected <= found, f"缺少 {expected - found}")

    progress_tpl = (SKILL_DIR / "templates" / "progress.md").read_text(encoding="utf-8")
    check(
        "progress 模板含脚本依赖的三个区块",
        all(md.has_section(progress_tpl, s) for s in ("章节状态", "当前位置", "卡壳摘要")),
    )
    review_tpl = (SKILL_DIR / "templates" / "review.md").read_text(encoding="utf-8")
    check(
        "review 模板含脚本依赖的两个区块",
        md.has_section(review_tpl, "待复习") and md.has_section(review_tpl, "已毕业"),
    )


def test_references_present() -> None:
    expected = {
        "ingest.md",
        "teaching-loop.md",
        "question-design.md",
        "state-schema.md",
        "anti-patterns.md",
    }
    found = {p.name for p in (SKILL_DIR / "references").glob("*.md")}
    check("references 齐全", expected <= found, f"缺少 {expected - found}")

    skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    broken = [name for name in expected if f"references/{name}" not in skill_md]
    check("SKILL.md 引用了全部 references", not broken, f"未被引用 {broken}")

    # 两条设计规则只存在于文档里，没有代码可测。用文本断言锚定，
    # 防止重构或改写时被悄悄删掉——它们是实测教训换来的。
    loop = (SKILL_DIR / "references" / "teaching-loop.md").read_text(encoding="utf-8")
    check(
        "teaching-loop 含会话密度上限规则",
        "会话边界" in loop and "最多讲 3 个论证单元" in loop,
    )
    check(
        "teaching-loop 含回答规则声明要求",
        "回答规则" in loop and "第一个冒出来的东西" in loop,
    )
    check(
        "SKILL.md 硬规则同步了这两条",
        "单次会话最多讲 3 个论证单元" in skill_md
        and "答第一反应" in skill_md,
    )
    brief_tpl = (SKILL_DIR / "templates" / "chapter-brief.md").read_text(encoding="utf-8")
    check(
        "导读稿模板提示拆章判断与场景题比例",
        "4 个以上必须拆" in brief_tpl and "场景题比例" in brief_tpl,
    )

    # 「最后动作」的语义曾长期未定义，被误读成会话日。定义落在 state-schema.md，
    # 同样无代码可测，用文本断言锚定。
    schema = (SKILL_DIR / "references" / "state-schema.md").read_text(encoding="utf-8")
    check(
        "state-schema 定义了「最后动作」语义",
        "### 最后动作" in schema and "不是会话日" in schema,
    )


def test_manifest() -> None:
    """manifest.json 是对外的元数据，容易与代码漂移而没人发现。"""
    path = SKILL_DIR / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        check("manifest.json 是合法 JSON", False, str(exc))
        return
    check("manifest.json 是合法 JSON", True)

    missing = [k for k in ("license", "author", "repository") if not manifest.get(k)]
    check("manifest 声明了许可与归属", not missing, f"缺少 {missing}")

    # vendor 的归属不能丢——这是 MIT 的要求，不只是礼貌。
    dep = manifest.get("depends_on", {}).get("deep-reader", {})
    check(
        "manifest 保留 deep-reader 的来源与许可",
        dep.get("source") and dep.get("license"),
        json.dumps(dep, ensure_ascii=False),
    )

    # 以下两项防漂移：manifest 对外宣称的命令集与状态机，必须等于代码里的实际值。
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import companion_router as router

    # 取子命令只能走 argparse 的私有结构。拿不到就 SKIP——
    # 这条用例的价值不值得让整个回归因 argparse 内部变动而崩掉。
    actual: set[str] | None = None
    try:
        for action in router.build_parser()._subparsers._group_actions:  # noqa: SLF001
            if getattr(action, "choices", None):
                actual = set(action.choices)
                break
    except (AttributeError, TypeError):
        actual = None

    declared = set(manifest.get("commands", []))
    if actual is None:
        record("SKIP", "manifest 的 commands 与 router 子命令一致", "argparse 内部结构取不到子命令")
    else:
        check(
            "manifest 的 commands 与 router 子命令一致",
            declared == actual,
            f"manifest={sorted(declared)} router={sorted(actual)}",
        )
    check(
        "manifest 的 chapter_states 与代码一致",
        tuple(manifest.get("chapter_states", ())) == tuple(ws.CHAPTER_STATES),
        f"manifest={manifest.get('chapter_states')} code={list(ws.CHAPTER_STATES)}",
    )


def test_licensing() -> None:
    """许可文件。LICENSE 必须保持纯净，归属信息走 NOTICE。

    首次发布时第三方说明被附在 MIT 正文后面，GitHub 的 licensee 检测器
    对改动过的许可文本直接判 NOASSERTION，仓库页不显示 MIT 徽标。
    归属一个字都不能少，但不能放在 LICENSE 里。
    """
    root = SKILL_DIR.parent.parent
    lic_path = root / "LICENSE"
    notice_path = root / "NOTICE"

    check("根目录有 LICENSE", lic_path.is_file())
    check("根目录有 NOTICE", notice_path.is_file())
    if not (lic_path.is_file() and notice_path.is_file()):
        return

    lic = lic_path.read_text(encoding="utf-8")
    notice = notice_path.read_text(encoding="utf-8")

    check(
        "LICENSE 是 MIT 正文",
        "MIT License" in lic and "WITHOUT WARRANTY OF ANY KIND" in lic,
    )
    # 这条是关键护栏：任何附加节都会让 GitHub 放弃识别许可。
    contaminants = [
        marker
        for marker in ("Third-party", "##", "---", "deep-reader")
        if marker in lic
    ]
    check(
        "LICENSE 不含附加内容（否则 GitHub 判 NOASSERTION）",
        not contaminants,
        f"发现 {contaminants}，应移到 NOTICE",
    )
    check(
        "NOTICE 保留 vendor 归属",
        "Hieu T. Luu" in notice and "tronghieu/agent-skills" in notice,
    )
    check(
        "NOTICE 保留设计借鉴归属",
        "hammer" in notice and "deep-study-skill" in notice,
    )


def test_vendored_deep_reader() -> None:
    vendor = SKILL_DIR.parent / "deep-reader"
    # 说明里只放相对路径——regression_results.md 会入版本库，
    # 绝对路径会把开发者的home目录结构提交上去。
    check("deep-reader 已 vendor", vendor.is_dir(), "skills/deep-reader")
    check("deep-reader LICENSE 保留", (vendor / "LICENSE").is_file())
    scripts = ["prepare-text.sh", "read-pages.sh", "verify-quotes.sh", "self-test.sh"]
    missing = [s for s in scripts if not (vendor / "scripts" / s).is_file()]
    check("deep-reader 关键脚本齐全", not missing, f"缺少 {missing}")
    not_exec = [
        s for s in scripts
        if (vendor / "scripts" / s).is_file() and not (vendor / "scripts" / s).stat().st_mode & 0o111
    ]
    check("deep-reader 脚本可执行", not not_exec, f"不可执行 {not_exec}")


def test_cjk_pagination(root: Path) -> None:
    """CJK 感知分页。这是对 deep-reader 按空白分词的修正，必须有回归护栏。"""
    import prepare_source as ps

    cjk, latin = ps.measure("这是中文。")
    check("measure 计中文字符", cjk == 5 and latin == 0, f"cjk={cjk} latin={latin}")
    cjk, latin = ps.measure("hello world foo")
    check("measure 计拉丁词", cjk == 0 and latin == 3, f"cjk={cjk} latin={latin}")
    cjk, latin = ps.measure("混排 mixed 文本")
    check("measure 处理中英混排", cjk == 4 and latin == 1, f"cjk={cjk} latin={latin}")

    # 核心缺陷回归：同一段中文，awk 的 NF 视角 vs CJK 感知视角
    para = "这是一段没有任何空格的中文正文。" * 40  # 640 字
    nf_view = len(para.split())  # awk NF 的等价物
    check(
        "锚定上游缺陷：中文段落按空白分词只算 1 词",
        nf_view == 1,
        f"NF={nf_view}",
    )
    check(
        "CJK 感知计量还原真实体量",
        ps.unit_weight(para) == 640,
        f"units={ps.unit_weight(para)}",
    )

    paragraphs = [f"第{i}段。" + "中文正文内容测试分页逻辑。" * 20 for i in range(1, 11)]
    pages = ps.paginate(paragraphs, 500)
    check("中文分出多页而非 1 页", len(pages) > 1, f"pages={len(pages)}")

    rendered = ps.render(pages)
    marker_re = re.compile(r"^\[\[page \d+\]\]$")
    markers = [ln for ln in rendered.splitlines() if ln.startswith("[[page ")]
    check(
        "页标记格式匹配 deep-reader 的正则",
        all(marker_re.fullmatch(m) for m in markers) and len(markers) == len(pages),
        f"markers={len(markers)} pages={len(pages)}",
    )
    num_re = re.compile(r"^\[\[page (\d+)\]\]$")
    numbers = [int(num_re.match(m).group(1)) for m in markers]
    check(
        "页码从 1 连续编号",
        numbers == list(range(1, len(pages) + 1)),
        f"首尾 {numbers[:3]}...{numbers[-3:]}",
    )

    squash = lambda s: "".join(c for c in s if not c.isspace())
    body = "\n".join(ln for ln in rendered.splitlines() if not marker_re.fullmatch(ln))
    check(
        "分页不改动任何原文字符",
        squash(body) == squash("\n".join(paragraphs)),
        f"原 {len(squash(chr(10).join(paragraphs)))} vs 后 {len(squash(body))}",
    )

    # 超长单段落必须被内部切开
    huge = "超长段落无换行。" * 300  # 2400 字
    huge_pages = ps.paginate([huge], 500)
    check("超长单段落被内部切分", len(huge_pages) >= 4, f"pages={len(huge_pages)}")
    huge_body = "".join(
        ln for page in huge_pages for ln in page
    )
    check(
        "超长段落切分后字符无损",
        squash(huge_body) == squash(huge),
        f"原 {len(squash(huge))} vs 后 {len(squash(huge_body))}",
    )

    # 端到端：txt 路径不依赖 pandoc
    book_dir = root / "cjk-book"
    book_dir.mkdir(parents=True, exist_ok=True)
    book = book_dir / "中文测试书.txt"
    book.write_text("\n\n".join(paragraphs), encoding="utf-8")

    payload = ps.prepare(book, None, 500, False)
    check(
        "prepare 端到端产出多页与 CJK 统计",
        payload["pages"] > 1
        and payload["cjk_ratio"] > 0.9
        and payload["synthetic_pages"] is True
        and payload["pager"].startswith("book-companion"),
        json.dumps(
            {k: payload[k] for k in ("pages", "cjk_ratio", "units", "pager")},
            ensure_ascii=False,
        ),
    )
    check(
        "工作区命名与 deep-reader 一致（<书名>-notes）",
        Path(payload["workspace"]).name == "中文测试书-notes",
        Path(payload["workspace"]).name,
    )

    again = ps.prepare(book, None, 500, False)
    check("prepare 幂等（不重复转换）", again["existing"] is True)

    coarse = ps.prepare(book, book_dir / "ws-900", 900, False)
    check(
        "units-per-page 可调且生效",
        coarse["pages"] < payload["pages"],
        f"upp=900 -> {coarse['pages']} 页；upp=500 -> {payload['pages']} 页",
    )

    try:
        ps.prepare(book_dir / "x.rtf", None, 500, False)
        check("不支持的格式应报错", False, "没有抛 PrepareError")
    except ps.PrepareError as exc:
        check("不支持的格式应报错", "找不到输入文件" in str(exc) or "不支持" in str(exc))

    if shutil.which("pandoc"):
        epub_src = book_dir / "src.md"
        epub_src.write_text("# 第1章 测试\n\n" + "\n\n".join(paragraphs), encoding="utf-8")
        epub = book_dir / "中文测试书.epub"
        rc = subprocess.run(
            ["pandoc", "-o", str(epub), str(epub_src)], capture_output=True, text=True
        )
        if rc.returncode == 0:
            ep = ps.prepare(epub, book_dir / "ws-epub", 500, False)
            check(
                "EPUB 经 pandoc 后同样多页",
                ep["pages"] > 1 and ep["format"] == "epub",
                json.dumps({k: ep[k] for k in ("pages", "format")}, ensure_ascii=False),
            )
        else:
            record("SKIP", "EPUB 端到端", f"pandoc 生成 epub 失败: {rc.stderr.strip()[:60]}")
    else:
        record("SKIP", "EPUB 端到端", "pandoc 未安装")

    pdf_delegated = "pdf" in ps.DELEGATED
    check("PDF 仍委托给 deep-reader（真实分页不能被覆盖）", pdf_delegated)


def report_environment() -> None:
    print("== 环境 ==")
    print(f"  python  {sys.version.split()[0]}")
    for tool in ("pdftotext", "pandoc"):
        path = shutil.which(tool)
        print(f"  {tool:<10} {path or '未安装（阶段一转换会受限，见 references/ingest.md）'}")
    print()


def _scrub(text: str) -> str:
    """去掉绝对路径。本报告入版本库，不该带开发者的目录结构。"""
    repo = str(SKILL_DIR.parent.parent)
    home = str(Path.home())
    return text.replace(repo + "/", "").replace(repo, "").replace(home, "~")


def write_report(path: Path) -> None:
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    lines = [
        "# book-companion 回归结果",
        "",
        "> 本文件由 `tests/run_regression.py` **每次运行自动重写**，不要手改。",
        "",
        f"- 运行时间: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- 通过: {passed}",
        f"- 失败: {failed}",
        f"- 跳过: {skipped}",
        "",
        "| 结果 | 用例 | 说明 |",
        "| --- | --- | --- |",
    ]
    for status, name, detail in RESULTS:
        lines.append(f"| {status} | {name} | {_scrub(detail) or '—'} |")
    path.write_text(_scrub("\n".join(lines)) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=None, help="把结果写成 markdown 报告")
    args = parser.parse_args()

    report_environment()

    with tempfile.TemporaryDirectory(prefix="book-companion-test-") as tmp:
        root = Path(tmp)
        print("== 用例 ==")
        test_markdown_roundtrip()
        test_templates_present()
        test_references_present()
        test_manifest()
        test_licensing()
        test_vendored_deep_reader()
        test_cjk_pagination(root)
        test_ingest_gate(root)

        workspace = make_workspace(root / "flow")
        test_full_flow(workspace)
        test_review_queue(workspace)
        test_corruption_detected(workspace)

    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
    print(f"\n== 汇总 ==\n  PASS {passed}\n  FAIL {failed}\n  SKIP {skipped}")

    # 结果快照默认自动重写。先前它是手写的，于是代码加了 7 个用例之后
    # 快照还停在旧数字（记 58，实跑 65），冷读项目的人会被误导。
    # 手写快照必然腐烂，所以改为每次运行都重生成。
    write_report(Path(args.report) if args.report else SKILL_DIR / "tests" / "regression_results.md")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
