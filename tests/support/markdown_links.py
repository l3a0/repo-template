"""Check that every relative link in the repo's Markdown reaches its target.

A link to a file that moved, or to a heading that was renamed, renders as an
ordinary link and fails only when a reader clicks it. The architecture pages
are split by section and link across each other hundreds of times, so a
heading renamed on one page can break a sentence on another with nothing
red anywhere. This check reads every relative link and asks two things:
does the file exist, and, when the link names an anchor, does that file have
a heading whose anchor matches.

An anchor follows GitHub's rule for headings: lowercase the heading's text,
drop every character that is not a letter, a digit, an underscore, a hyphen
or a space, and turn each space into a hyphen. A second heading with the same
anchor gets `-1`, a third `-2`, and so on.

Links inside a fenced block or a backtick span are not links, so they are
skipped, the same way the prose sweeps skip them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.support.markdown_sweep import blank_code

_HEADING = re.compile(r"^ {0,3}(#{1,6}) +(.*?) *#* *$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


@dataclass(frozen=True)
class BrokenLink:
    """One link that does not reach its target, named so a reader can open it."""

    path: Path
    line_number: int
    target: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}: {self.target}: {self.reason}"


def anchor(heading: str) -> str:
    """The anchor GitHub gives a heading with this text.

    GitHub builds it from the heading as rendered, so inline markup goes
    first: a code span keeps its words, a link keeps its text, and raw HTML
    tags and emphasis markers drop out.
    """
    parts = re.split(r"(`[^`]*`)", heading)
    rendered = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            rendered.append(part[1:-1])
            continue
        part = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", part)
        part = re.sub(r"<[^>]+>", "", part)
        part = re.sub(r"(\*\*|__|\*|(?<!\w)_|_(?!\w))", "", part)
        rendered.append(part)
    text = "".join(rendered).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every anchor a document's headings produce, fenced blocks excepted."""
    found: set[str] = set()
    seen: dict[str, int] = {}
    fence: str | None = None
    for line in text.split("\n"):
        opening = _FENCE.match(line)
        if opening:
            run = opening.group(1)
            if fence is None:
                fence = run[0] * len(run)
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        heading = _HEADING.match(line)
        if heading:
            base = anchor(heading.group(2))
            slug = base
            while slug in found:
                seen[base] = seen.get(base, 0) + 1
                slug = f"{base}-{seen[base]}"
            found.add(slug)
    return found


def broken_links(path: Path, root: Path) -> list[BrokenLink]:
    """Every relative link in one file that misses its file or its anchor."""
    text = path.read_text(encoding="utf-8")
    prose = blank_code(text)
    cache: dict[Path, set[str]] = {}
    broken: list[BrokenLink] = []
    for number, line in enumerate(prose.split("\n"), start=1):
        for match in _LINK.finditer(line):
            target = match.group(1)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):
                continue
            file_part, _, fragment = target.partition("#")
            dest = path if not file_part else (path.parent / file_part).resolve()
            if file_part and not dest.exists():
                broken.append(BrokenLink(path, number, target, "no such file"))
                continue
            if not fragment or dest.suffix != ".md":
                continue
            if dest not in cache:
                cache[dest] = anchors(dest.read_text(encoding="utf-8"))
            if fragment not in cache[dest]:
                where = dest.relative_to(root) if dest.is_relative_to(root) else dest
                broken.append(
                    BrokenLink(path, number, target, f"no heading with that anchor in {where}")
                )
    return broken
