"""Markdown 区块与表格的读写。

状态文件以人可读为先，所以解析对空格和对齐要宽容；
但结构损坏时必须报错退出——损坏的状态文件比缺失的状态文件危险，
静默跳过会让进度悄悄丢失。
"""

from __future__ import annotations

PLACEHOLDER = "—"


class StateFormatError(RuntimeError):
    """状态文件结构不符合 references/state-schema.md 的约定。"""


def _marker(level: int) -> str:
    return "#" * level + " "


def find_section(text: str, heading: str, level: int = 2) -> str:
    """取出某个标题下的正文（不含标题行本身）。"""
    marker = _marker(level)
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(marker) and line[len(marker) :].strip() == heading:
            start = i
            break
    if start is None:
        raise StateFormatError(f"找不到区块「{heading}」")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(marker):
            end = j
            break
    return "\n".join(lines[start + 1 : end]).strip("\n")


def has_section(text: str, heading: str, level: int = 2) -> bool:
    try:
        find_section(text, heading, level)
    except StateFormatError:
        return False
    return True


def replace_section(text: str, heading: str, body: str, level: int = 2) -> str:
    """整体替换某个标题下的正文，保留标题行与文件其余部分。"""
    marker = _marker(level)
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(marker) and line[len(marker) :].strip() == heading:
            start = i
            break
    if start is None:
        raise StateFormatError(f"找不到区块「{heading}」，无法写入")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(marker):
            end = j
            break
    rebuilt = lines[: start + 1] + [""] + body.strip("\n").splitlines() + [""]
    return "\n".join(rebuilt + lines[end:])


def parse_table(block: str) -> list[dict[str, str]]:
    """解析 markdown 表格为字典列表。无表格返回空列表。"""
    rows = [ln.strip() for ln in block.splitlines() if ln.strip().startswith("|")]
    if not rows:
        return []
    if len(rows) < 2:
        raise StateFormatError("表格缺少分隔行")

    header = [c.strip() for c in rows[0].strip("|").split("|")]
    sep_chars = set(rows[1].replace("|", "").replace(" ", ""))
    if not sep_chars or not sep_chars <= set("-:"):
        raise StateFormatError(f"表格第二行不是分隔行: {rows[1]!r}")

    out: list[dict[str, str]] = []
    for line in rows[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            raise StateFormatError(
                f"表格行列数不匹配（表头 {len(header)} 列，该行 {len(cells)} 列）: {line!r}"
            )
        out.append(dict(zip(header, cells)))
    return out


def render_table(columns: list[str], rows: list[dict[str, str]]) -> str:
    """渲染 markdown 表格。缺失字段填占位符，不填空字符串。"""
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = [str(row.get(col, PLACEHOLDER) or PLACEHOLDER) for col in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def parse_bullets(block: str) -> dict[str, str]:
    """解析 `- key: value` 形式的元信息列表。"""
    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, _, value = line[2:].partition(":")
        out[key.strip()] = value.strip()
    return out


def render_bullets(pairs: dict[str, str]) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in pairs.items())
