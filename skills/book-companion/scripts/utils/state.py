"""companion/ 状态文件的读写。

字段定义见 references/state-schema.md，那份文档是规格，这里是实现。
两者不一致时以文档为准，改代码。

脚本只负责它拥有的区块（表格和元信息）。agent 写的叙述性内容
（learner.md 的背景、sessions/ 的判断）脚本一律不重排、不改写。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from . import markdown as md
from .workspace import CHAPTER_STATES, Chapter, companion_dir

PROGRESS_FILE = "progress.md"
LEARNER_FILE = "learner.md"
REVIEW_FILE = "review.md"

PROGRESS_COLUMNS = ["章节", "标题", "状态", "费曼", "首答正确率", "最后动作"]
REVIEW_COLUMNS = ["点", "章节", "页码", "档位", "下次到期", "连续答对"]
GRADUATED_COLUMNS = ["点", "章节", "毕业时间"]

SEC_CHAPTERS = "章节状态"
SEC_CURRENT = "当前位置"
SEC_STUCK = "卡壳摘要"

# 模板里的占位文本。追加真实条目时要先把它们清掉，
# 否则"暂无。"会和真实的卡壳点并列，让人误读。
PLACEHOLDER_LINES = {"暂无。", "暂无", "无", "—", "-"}
SEC_REVIEW_DUE = "待复习"
SEC_REVIEW_DONE = "已毕业"

# 间隔序列固定。走完 21 天档且答对即毕业。
INTERVAL_SEQ = ["1天", "3天", "7天", "21天"]
INTERVAL_DAYS = {"1天": 1, "3天": 3, "7天": 7, "21天": 21}


def today() -> str:
    return _dt.date.today().isoformat()


def _shift(days: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


class StateError(RuntimeError):
    """状态文件缺失或内容非法。"""


def _read(path: Path) -> str:
    if not path.is_file():
        raise StateError(
            f"找不到 {path.name}。先跑 `companion_router.py init` 初始化导读工作区。"
        )
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# progress.md
# --------------------------------------------------------------------------- #


@dataclass
class Progress:
    path: Path
    text: str
    chapters: list[dict[str, str]]

    @classmethod
    def load(cls, workspace: Path) -> "Progress":
        path = companion_dir(workspace) / PROGRESS_FILE
        text = _read(path)
        rows = md.parse_table(md.find_section(text, SEC_CHAPTERS))
        for row in rows:
            state = row.get("状态", "")
            if state not in CHAPTER_STATES:
                raise StateError(
                    f"{path.name} 中 {row.get('章节')} 的状态 {state!r} 非法，"
                    f"合法取值: {', '.join(CHAPTER_STATES)}"
                )
        return cls(path=path, text=text, chapters=rows)

    @property
    def meta(self) -> dict[str, str]:
        head = self.text.split("\n##", 1)[0]
        return md.parse_bullets(head)

    def row(self, chapter_id: str) -> dict[str, str]:
        for row in self.chapters:
            if row.get("章节") == chapter_id:
                return row
        raise StateError(f"progress.md 里没有章节 {chapter_id}")

    def next_pending(self) -> dict[str, str] | None:
        """下一个**该讲**的章节。

        跳过三种状态：
        - passed / skipped —— 已完成
        - **checked** —— 讲完且考过但未达标。它的重来由**复习队列**驱动
          （到期后换题型重问），不由章节推进驱动。

        最后一条很关键：早期实现把 checked 也算作"下一个该做的"，
        结果一旦某章未达标，next 就永久停在那一章，读者再也无法往下走。
        未达标不等于要立刻重讲——它等的是间隔复习的时机。
        """
        for row in self.chapters:
            if row.get("状态") not in ("passed", "skipped", "checked"):
                return row
        return None

    def awaiting_recheck(self) -> list[dict[str, str]]:
        """讲完考过但未达标、等待复习驱动重考的章节。"""
        return [r for r in self.chapters if r.get("状态") == "checked"]

    def counts(self) -> dict[str, int]:
        out = {state: 0 for state in CHAPTER_STATES}
        for row in self.chapters:
            out[row["状态"]] += 1
        return out

    def set_state(
        self,
        chapter_id: str,
        state: str,
        *,
        feynman: str | None = None,
        first_try: str | None = None,
    ) -> dict[str, str]:
        if state not in CHAPTER_STATES:
            raise StateError(
                f"状态 {state!r} 非法，合法取值: {', '.join(CHAPTER_STATES)}"
            )
        row = self.row(chapter_id)
        row["状态"] = state
        if feynman is not None:
            row["费曼"] = feynman
        if first_try is not None:
            row["首答正确率"] = first_try
        row["最后动作"] = today()
        return row

    def set_current(self, body: str) -> None:
        self.text = md.replace_section(self.text, SEC_CURRENT, body)

    def append_stuck(self, line: str) -> None:
        current = md.find_section(self.text, SEC_STUCK).strip()
        kept = [
            ln
            for ln in current.splitlines()
            if ln.strip() and ln.strip() not in PLACEHOLDER_LINES
        ]
        kept.append(f"- {line}")
        self.text = md.replace_section(self.text, SEC_STUCK, "\n".join(kept))

    def save(self) -> None:
        body = md.render_table(PROGRESS_COLUMNS, self.chapters)
        text = md.replace_section(self.text, SEC_CHAPTERS, body)
        head, sep, rest = text.partition("\n##")
        meta = md.parse_bullets(head)
        if "最后更新" in meta:
            meta["最后更新"] = today()
            title = head.splitlines()[0]
            head = title + "\n\n" + md.render_bullets(meta) + "\n"
            text = head + sep + rest
        self.text = text
        self.path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# review.md
# --------------------------------------------------------------------------- #


@dataclass
class Review:
    path: Path
    text: str
    pending: list[dict[str, str]]
    graduated: list[dict[str, str]]

    @classmethod
    def load(cls, workspace: Path) -> "Review":
        path = companion_dir(workspace) / REVIEW_FILE
        text = _read(path)
        pending = md.parse_table(md.find_section(text, SEC_REVIEW_DUE))
        graduated = md.parse_table(md.find_section(text, SEC_REVIEW_DONE))
        for row in pending:
            tier = row.get("档位", "")
            if tier not in INTERVAL_DAYS:
                raise StateError(
                    f"{path.name} 中档位 {tier!r} 非法，合法取值: {', '.join(INTERVAL_SEQ)}"
                )
        return cls(path=path, text=text, pending=pending, graduated=graduated)

    def due(self, on: str | None = None) -> list[dict[str, str]]:
        """到期项。按日期比较，同一天内重复复习无意义。"""
        cutoff = on or today()
        return [r for r in self.pending if r.get("下次到期", "9999-12-31") <= cutoff]

    def add(self, point: str, chapter: str, page: str) -> dict[str, str]:
        for row in self.pending:
            if row.get("点") == point and row.get("章节") == chapter:
                # 已在队列里再次卡壳：退档处理
                return self.grade(point, correct=False)
        row = {
            "点": point,
            "章节": chapter,
            "页码": page or md.PLACEHOLDER,
            "档位": INTERVAL_SEQ[0],
            "下次到期": _shift(INTERVAL_DAYS[INTERVAL_SEQ[0]]),
            "连续答对": "0",
        }
        self.pending.append(row)
        return row

    def grade(self, point: str, *, correct: bool) -> dict[str, str]:
        """答对升档，答错退回上一档并把连续答对归零。"""
        for index, row in enumerate(self.pending):
            if row.get("点") != point:
                continue
            tier_index = INTERVAL_SEQ.index(row["档位"])
            if correct:
                streak = int(row.get("连续答对", "0") or 0) + 1
                if tier_index == len(INTERVAL_SEQ) - 1:
                    self.pending.pop(index)
                    done = {
                        "点": row["点"],
                        "章节": row["章节"],
                        "毕业时间": today(),
                    }
                    self.graduated.append(done)
                    return done
                row["档位"] = INTERVAL_SEQ[tier_index + 1]
                row["连续答对"] = str(streak)
            else:
                row["档位"] = INTERVAL_SEQ[max(0, tier_index - 1)]
                row["连续答对"] = "0"
            row["下次到期"] = _shift(INTERVAL_DAYS[row["档位"]])
            return row
        raise StateError(f"复习队列里没有 {point!r}")

    def save(self) -> None:
        text = md.replace_section(
            self.text, SEC_REVIEW_DUE, md.render_table(REVIEW_COLUMNS, self.pending)
        )
        text = md.replace_section(
            text, SEC_REVIEW_DONE, md.render_table(GRADUATED_COLUMNS, self.graduated)
        )
        self.text = text
        self.path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _template(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise StateError(f"模板缺失: {path}")
    return path.read_text(encoding="utf-8")


def _fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def init_companion(
    workspace: Path, book: str, chapters: list[Chapter], *, force: bool = False
) -> dict:
    """建立 companion/ 及三个状态文件。已存在则不覆盖，除非 force。"""
    root = companion_dir(workspace)
    (root / "briefs").mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []

    values = {
        "book": book,
        "workspace": str(workspace),
        "date": today(),
        "total": str(len(chapters)),
        "first_chapter": chapters[0].id if chapters else md.PLACEHOLDER,
    }

    progress_path = root / PROGRESS_FILE
    if progress_path.is_file() and not force:
        skipped.append(PROGRESS_FILE)
    else:
        rows = [
            {
                "章节": ch.id,
                "标题": ch.title,
                "状态": "pending",
                "费曼": md.PLACEHOLDER,
                "首答正确率": md.PLACEHOLDER,
                "最后动作": md.PLACEHOLDER,
            }
            for ch in chapters
        ]
        text = _fill(_template(PROGRESS_FILE), values)
        text = md.replace_section(
            text, SEC_CHAPTERS, md.render_table(PROGRESS_COLUMNS, rows)
        )
        progress_path.write_text(text, encoding="utf-8")
        created.append(PROGRESS_FILE)

    for name in (LEARNER_FILE, REVIEW_FILE):
        path = root / name
        if path.is_file() and not force:
            skipped.append(name)
            continue
        path.write_text(_fill(_template(name), values), encoding="utf-8")
        created.append(name)

    return {
        "companion_dir": str(root),
        "created": created,
        "skipped": skipped,
        "chapters": len(chapters),
    }
