"""deep-reader 工作区的定位与校验。

阶段二依赖阶段一的产物。这里把「阶段一是否真的完成」做成机械判据，
避免在 notes/ 还是空的时候就开始讲——那种情况下 agent 只能靠模型先验编，
正是 SKILL.md 的第一条硬规则要禁止的事。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

COMPANION_DIRNAME = "companion"

CHAPTER_STATES = (
    "pending",
    "briefed",
    "taught",
    "checked",
    "passed",
    "skipped",
)

# 推进顺序。skipped 不在序列里，它是旁路。
STATE_ORDER = ("pending", "briefed", "taught", "checked", "passed")


class WorkspaceError(RuntimeError):
    """工作区不存在、结构不完整，或阶段一未完成。"""


@dataclass(frozen=True)
class Chapter:
    id: str
    page_from: int
    page_to: int
    title: str


@dataclass
class IngestCheck:
    """阶段一完成判据的检查结果。"""

    ok: bool
    missing: list[str] = field(default_factory=list)
    notes_count: int = 0
    chapters_count: int = 0

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "missing": self.missing,
            "notes_count": self.notes_count,
            "chapters_count": self.chapters_count,
        }


def resolve(workspace: str | Path) -> Path:
    path = Path(workspace).expanduser().resolve()
    if not path.is_dir():
        raise WorkspaceError(f"工作区目录不存在: {path}")
    return path


def companion_dir(workspace: Path) -> Path:
    return workspace / COMPANION_DIRNAME


def read_chapters(workspace: Path) -> list[Chapter]:
    """读 chapters.tsv。这是推进顺序的唯一依据。"""
    tsv = workspace / "chapters.tsv"
    if not tsv.is_file():
        raise WorkspaceError(
            f"找不到 {tsv}。阶段一的检视阅读还没确认章节结构，"
            "不能开始导读——先完成 deep-reader 的 Step 2。"
        )

    chapters: list[Chapter] = []
    for lineno, raw in enumerate(tsv.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split("\t")
        if len(parts) < 4:
            raise WorkspaceError(
                f"{tsv}:{lineno} 格式应为 id<TAB>from<TAB>to<TAB>title，实际: {raw!r}"
            )
        cid, page_from, page_to, title = parts[0], parts[1], parts[2], "\t".join(parts[3:])
        try:
            chapters.append(
                Chapter(
                    id=cid.strip(),
                    page_from=int(page_from.strip()),
                    page_to=int(page_to.strip()),
                    title=title.strip(),
                )
            )
        except ValueError as exc:
            raise WorkspaceError(f"{tsv}:{lineno} 页码不是整数: {raw!r}") from exc

    if not chapters:
        raise WorkspaceError(f"{tsv} 是空的")
    return chapters


def check_ingest(workspace: Path) -> IngestCheck:
    """机械校验阶段一完成判据，对应 SKILL.md「阶段一完成判据」。"""
    missing: list[str] = []

    source = workspace / "source.txt"
    if not source.is_file():
        missing.append("source.txt 不存在")
    elif "[[page " not in source.read_text(encoding="utf-8", errors="replace")[:20000]:
        missing.append("source.txt 缺少 [[page N]] 页码标记")

    chapters_count = 0
    if not (workspace / "chapters.tsv").is_file():
        missing.append("chapters.tsv 不存在（章节结构未确认）")
    else:
        try:
            chapters_count = len(read_chapters(workspace))
        except WorkspaceError as exc:
            missing.append(str(exc))

    notes_dir = workspace / "notes"
    notes_count = len(sorted(notes_dir.glob("*.md"))) if notes_dir.is_dir() else 0
    if notes_count == 0:
        missing.append("notes/ 下没有逐章笔记")

    if not (workspace / "synthesis.md").is_file():
        missing.append("synthesis.md 不存在")

    return IngestCheck(
        ok=not missing,
        missing=missing,
        notes_count=notes_count,
        chapters_count=chapters_count,
    )


def note_path(workspace: Path, chapter_id: str) -> Path | None:
    """找某一章的笔记文件。deep-reader 的命名是 chNN-<slug>.md。"""
    notes_dir = workspace / "notes"
    if not notes_dir.is_dir():
        return None
    for candidate in sorted(notes_dir.glob(f"{chapter_id}-*.md")):
        return candidate
    exact = notes_dir / f"{chapter_id}.md"
    return exact if exact.is_file() else None


def brief_path(workspace: Path, chapter_id: str) -> Path:
    return companion_dir(workspace) / "briefs" / f"{chapter_id}-brief.md"


def state_rank(state: str) -> int:
    """状态在推进序列里的位置。skipped 归为 -1，不参与比较。"""
    if state == "skipped":
        return -1
    try:
        return STATE_ORDER.index(state)
    except ValueError as exc:
        raise WorkspaceError(
            f"未知章节状态 {state!r}，合法取值: {', '.join(CHAPTER_STATES)}"
        ) from exc
