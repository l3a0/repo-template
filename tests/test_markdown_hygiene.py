"""The prose sweeps CLAUDE.md names, run as tests rather than from memory.

Two layers. The first pins the sweep's own behavior on small documents, which
is what keeps the code-fence exemption honest. The second runs the sweep over
every Markdown file in the repo, so a slip fails the suite locally and in CI
rather than waiting for someone to remember the command.

`TestIssueReferencesAreLinked` holds CLAUDE.md's rule that every issue and
pull request number in a Markdown file is a link. It carries both layers
itself. Small documents pin each exemption, and its last test runs the check
over every Markdown file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support.markdown_sweep import (
    Finding,
    blank_code,
    markdown_files,
    sweep_file,
    sweep_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _rules(findings: list[Finding]) -> list[str]:
    return [finding.rule for finding in findings]


def test_a_tilde_glued_to_punctuation_is_flagged() -> None:
    findings = sweep_text("The floor sits near (~30) on a slow day.\n", Path("x.md"))
    assert _rules(findings) == ["unescaped tilde, write it as \\~"]


def test_a_tilde_glued_to_a_letter_is_flagged() -> None:
    findings = sweep_text("It ran word~30 times.\n", Path("x.md"))
    assert _rules(findings) == ["unescaped tilde, write it as \\~"]


def test_a_tilde_after_whitespace_is_left_alone() -> None:
    # One after whitespace can only open a pair, never close one, so it cannot
    # strike out the text behind it.
    assert sweep_text("It retained ~90% of the return.\n", Path("x.md")) == []


def test_an_escaped_tilde_is_left_alone() -> None:
    assert sweep_text("It retained \\~90% of the return.\n", Path("x.md")) == []


def test_a_tilde_inside_a_backtick_span_is_left_alone() -> None:
    assert sweep_text("Run `rg -n '(?<!x)~'` before finalizing.\n", Path("x.md")) == []


def test_a_tilde_inside_a_fenced_block_is_left_alone() -> None:
    document = "Before.\n\n```bash\nrg -n '(?<!x)~' *.md\n```\n\nAfter.\n"
    assert sweep_text(document, Path("x.md")) == []


def test_a_tilde_after_a_fenced_block_closes_is_flagged_again() -> None:
    document = "```bash\necho (~30)\n```\n\nThe floor sits near (~30).\n"
    findings = sweep_text(document, Path("x.md"))
    assert _rules(findings) == ["unescaped tilde, write it as \\~"]
    assert [finding.line_number for finding in findings] == [5]


def test_a_tilde_fenced_block_does_not_flag_its_own_fence() -> None:
    # A fence may be written with tildes. Its own delimiter must not read as
    # prose, or every tilde-fenced block reports two findings.
    assert sweep_text("~~~python\nx = 1\n~~~\n", Path("x.md")) == []


def test_a_tight_delimiter_row_is_flagged() -> None:
    document = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    findings = sweep_text(document, Path("x.md"))
    assert _rules(findings) == ["tight table delimiter row, pad it as | --- |"]
    assert [finding.line_number for finding in findings] == [2]


def test_a_padded_delimiter_row_is_left_alone() -> None:
    assert sweep_text("| a | b |\n| --- | --- |\n| 1 | 2 |\n", Path("x.md")) == []


def test_blanking_keeps_line_numbers_and_lengths() -> None:
    document = "one\n```\ntwo\n```\nthree\n"
    blanked = blank_code(document)
    assert [len(line) for line in blanked.split("\n")] == [
        len(line) for line in document.split("\n")
    ]


def test_an_unmatched_backtick_run_stays_prose() -> None:
    # A lone backtick opens nothing, so the tilde after it is still prose and
    # still capable of closing a strikethrough pair.
    findings = sweep_text("A stray ` and then word~30.\n", Path("x.md"))
    assert _rules(findings) == ["unescaped tilde, write it as \\~"]


def test_discovery_keeps_untracked_files_and_drops_ignored_ones(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("cache/\n", encoding="utf-8")
    (tmp_path / "tracked.md").write_text("tracked\n", encoding="utf-8")
    (tmp_path / "untracked.md").write_text("written but not added\n", encoding="utf-8")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "README.md").write_text("a tool wrote this\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.md"], cwd=tmp_path, check=True)

    found = [path.relative_to(tmp_path).as_posix() for path in markdown_files(tmp_path)]

    assert found == ["tracked.md", "untracked.md"]


def test_discovery_skips_a_file_deleted_but_still_in_the_index(tmp_path: Path) -> None:
    # git lists an index entry whose file is gone, and reading it raises
    # FileNotFoundError, which reports a pending deletion as a prose failure.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kept.md").write_text("kept\n", encoding="utf-8")
    (tmp_path / "removed.md").write_text("about to go\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    (tmp_path / "removed.md").unlink()

    found = [path.relative_to(tmp_path).as_posix() for path in markdown_files(tmp_path)]

    assert found == ["kept.md"]


def test_discovery_fails_loudly_outside_a_repository(tmp_path: Path) -> None:
    # A silent empty list would turn the sweep below into a vacuous pass.
    with pytest.raises(RuntimeError):
        markdown_files(tmp_path)


def test_the_repo_has_markdown_to_sweep() -> None:
    # Without this, a discovery bug turns the sweep below into a vacuous pass.
    assert len(markdown_files(REPO_ROOT)) >= 3


# --- The fence-closing decision ----------------------------------------------
# Every clause of the closing test below was deletable with no test noticing.


def test_a_backtick_fence_is_not_closed_by_a_tilde_line() -> None:
    document = "```bash\n~~~\necho (~30)\n```\n"
    assert sweep_text(document, Path("x.md")) == []


def test_a_longer_run_closes_a_fence() -> None:
    # The closing run may exceed the opening one, so prose after it is prose.
    document = "```\nx\n````\n\nword~30\n"
    findings = sweep_text(document, Path("x.md"))
    assert [finding.line_number for finding in findings] == [5]


def test_a_shorter_run_does_not_close_a_fence() -> None:
    document = "````\n```\nword~30\n````\n"
    assert sweep_text(document, Path("x.md")) == []


def test_a_fence_line_carrying_an_info_string_does_not_close() -> None:
    # Only a bare delimiter closes. A line with an info string opens.
    document = "```\n```python\nword~30\n```\n"
    assert sweep_text(document, Path("x.md")) == []


def test_a_fenced_block_stays_exempt_past_its_second_line() -> None:
    # Clearing the fence unconditionally would end the block after one body
    # line, leaking every longer example in the repo's own docs into prose.
    document = "```bash\nword~30\nword~30\nword~30\n```\n"
    assert sweep_text(document, Path("x.md")) == []


def test_an_indented_fence_is_still_a_fence() -> None:
    document = "  ```\n  word~30\n  ```\n"
    assert sweep_text(document, Path("x.md")) == []


def test_four_spaces_of_indent_is_not_a_fence() -> None:
    # Four spaces is an indented code block, which this sweep does not model,
    # so the delimiter is prose and the line after it is scanned.
    document = "    ```\nword~30\n"
    findings = sweep_text(document, Path("x.md"))
    assert [finding.line_number for finding in findings] == [2]


def test_a_two_character_run_is_not_a_fence() -> None:
    document = "``\nword~30\n``\n"
    findings = sweep_text(document, Path("x.md"))
    assert [finding.line_number for finding in findings] == [2]


def test_a_four_backtick_fence_opens_and_closes() -> None:
    document = "````\nx\n````\n\nword~30\n"
    findings = sweep_text(document, Path("x.md"))
    assert [finding.line_number for finding in findings] == [5]


# --- Backtick spans -----------------------------------------------------------


def test_a_longer_run_does_not_close_a_shorter_span() -> None:
    # The double run does not close the single one, so nothing on the line is
    # a span at all and the tilde is scanned as the prose it is.
    findings = sweep_text("A `word~30 and ``x`` later.\n", Path("x.md"))
    assert _rules(findings) == ["unescaped tilde, write it as \\~"]


def test_a_double_backtick_span_is_not_closed_by_a_single_backtick() -> None:
    # Only a run of exactly two closes it. Anything looser walks off the end
    # of the line, which is a crash rather than a finding.
    assert sweep_text("The span ``a b`\n", Path("x.md")) == []


def test_an_unmatched_run_does_not_swallow_a_later_span() -> None:
    assert sweep_text("A run ``` of three and `x~y` after.\n", Path("x.md")) == []


def test_an_unmatched_run_does_not_stop_the_scan() -> None:
    assert sweep_text("A stray ` and ``x~30`` later.\n", Path("x.md")) == []


def test_a_tilde_after_a_span_closing_backtick_is_left_alone() -> None:
    # The closing backtick is blanked, so the tilde follows whitespace and can
    # only open a pair. Leaving the backtick unblanked would flag this.
    assert sweep_text("Set `flag`~30 percent.\n", Path("x.md")) == []


# --- The two patterns ---------------------------------------------------------


def test_a_tilde_preceded_by_a_tilde_is_left_alone() -> None:
    # A deliberate strikethrough opener is not a slip.
    assert sweep_text("Roughly ~~30 people showed.\n", Path("x.md")) == []


def test_a_tilde_preceded_by_an_angle_bracket_is_left_alone() -> None:
    assert sweep_text("An element a<~b here.\n", Path("x.md")) == []


def test_a_tilde_preceded_by_a_tab_is_left_alone() -> None:
    # The class is whitespace, not a literal space.
    assert sweep_text("A tab\t~30 percent.\n", Path("x.md")) == []


def test_a_one_dash_tight_row_is_flagged() -> None:
    findings = sweep_text("| a |\n|-|\n", Path("x.md"))
    assert _rules(findings) == ["tight table delimiter row, pad it as | --- |"]


def test_a_row_padded_on_one_side_only_is_left_alone() -> None:
    # MD060 is about mixed padding across rows. A half-padded delimiter is not
    # the tight form this sweep exists to catch.
    assert sweep_text("| a |\n|--- |\n", Path("x.md")) == []
    assert sweep_text("| a |\n| ---|\n", Path("x.md")) == []


def test_an_empty_cell_is_not_a_delimiter_row() -> None:
    assert sweep_text("| a | b |\n||\n", Path("x.md")) == []


# --- What a finding reports ---------------------------------------------------


def test_a_finding_quotes_the_source_line_not_the_blanked_one() -> None:
    # The reader opens the file at this line, so the message has to match what
    # they will see there rather than the blanked copy the scan read.
    findings = sweep_text("A `code` and word~30.\n", Path("x.md"))
    assert [finding.line for finding in findings] == ["A `code` and word~30."]


# --- Discovery ----------------------------------------------------------------


def test_discovery_skips_a_markdown_path_that_is_not_a_regular_file(
    tmp_path: Path,
) -> None:
    # A directory named like a document satisfies an existence check and then
    # raises IsADirectoryError from the read.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kept.md").write_text("kept\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("about to become a directory\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    (tmp_path / "notes.md").unlink()
    (tmp_path / "notes.md").mkdir()

    found = [path.relative_to(tmp_path).as_posix() for path in markdown_files(tmp_path)]

    assert found == ["kept.md"]


@pytest.mark.parametrize(
    "path", markdown_files(REPO_ROOT), ids=lambda path: str(path.relative_to(REPO_ROOT))
)
def test_every_markdown_file_passes_the_prose_sweeps(path: Path) -> None:
    findings = sweep_file(path)
    assert not findings, "\n".join(str(finding) for finding in findings)


# --- Issue and pull request references ----------------------------------------
#
# Where this came from. The helper and the test class below are copied from
# tests/test_markdown_hygiene.py in l3a0/quantitative-trading, at commit
# 11e7a63, the last commit to change them there. They landed here in pull
# request PRNUM. A squash merge creates its commit only when it merges, so the
# pull request is the name this comment can carry, and it resolves to one
# commit on main. Nothing in them changed on the way over. This file already
# imported blank_code and markdown_files and defined REPO_ROOT the same way.
# The blank_code here is written differently from the sibling's, but it blanks
# the same characters and keeps every newline and line length, which the
# helper needs so a finding names its own line. Pull requests 193 and 197
# there explain each exemption and each gap left open on purpose.


def _unlinked_references(document: str) -> list[int]:
    """The line of every issue or pull request number left as plain text.

    CLAUDE.md's writing rules ask for every such number in a Markdown file to
    be a link, because GitHub renders a bare `#NN` in a repository file as
    plain text. Code spans, fences, HTML comments and quotations are exempt,
    since a link inside code breaks it and a quotation stays as written. A
    quotation is a straight or curly double-quoted span on one line. A
    blockquote is not exempt, because nothing marks one as a quotation rather
    than a note or a GitHub alert.

    A reference written out in words is held too, and so is every number in a
    run of them. "issues [4](...), 43 and 47" leaves two numbers bare, which is
    the half-linked list the rule names as failing. A run may wrap onto the
    next line at any point but never across a blank one. "issues 3-5" is a
    range of two numbers, while a number opening a date such as 2026-09-18 is
    not an issue at all.

    Everything blanked keeps its newlines, so the line a finding reports is the
    line the reference is on. The first version of this check blanked a
    wrapped link's newline away and reported every later finding one line
    early.
    """
    import re

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = blank_code(document)
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.DOTALL)
    text = re.sub(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d', blank, text)

    word = r"(?:issues?|PRs?|pull requests?)"
    gap = r"[ \t]*(?:\n[ \t]*)?"
    space = r"(?:[ \t]+(?:\n[ \t]*)?|[ \t]*\n[ \t]*)"
    target = r"(?:\([^)\n]*\)|\[[^\]\n]*\])"
    linked_number = rf"\[\d+\]{target}"
    number = rf"(?:{linked_number}|\d+(?!\d|-\d\d-\d\d))"
    join = (
        rf"(?:[ \t]*,{gap}(?:(?:and|or){space})?"
        rf"|{space}(?:and|or|through|to){space}|[ \t]*[-\u2013][ \t]*)"
    )
    link = re.compile(rf"\[(?:[^\]\n]|\n(?![ \t]*\n))*\]{target}")
    run = re.compile(
        rf"(?:\[{word}{gap}\d+\]{target}|\b{word}{gap}{number})(?:{join}{number})*",
        re.IGNORECASE,
    )
    bare_hash = re.compile(r"(?<![\w/&])(?:PR[ \t]?)?#\d+\b|\b(?:PR|issue)#\d+\b", re.IGNORECASE)

    spans = [m.span() for m in link.finditer(text)]

    def linked(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    hits = [m.start() for m in bare_hash.finditer(text) if not linked(m.start())]
    for m in run.finditer(text):
        for token in re.finditer(rf"{linked_number}|(\d+)", m.group(0)):
            pos = m.start() + token.start(1)
            if token.group(1) and not linked(pos):
                hits.append(pos)
    return sorted(text.count("\n", 0, pos) + 1 for pos in hits)


class TestIssueReferencesAreLinked:
    def test_a_bare_number_is_flagged(self) -> None:
        assert _unlinked_references("Closed by #12 last week.\n") == [1]

    def test_a_bare_pull_request_is_flagged(self) -> None:
        assert _unlinked_references("See PR #34.\n") == [1]

    def test_a_pull_request_glued_to_its_number_is_flagged(self) -> None:
        assert _unlinked_references("See PR#34 and issue#12.\n") == [1, 1]

    def test_a_number_in_words_is_flagged(self) -> None:
        assert _unlinked_references("This belongs to issue 10.\n") == [1]

    def test_a_number_wrapped_onto_the_next_line_is_flagged(self) -> None:
        assert _unlinked_references("the page put it ahead of issue\n41 in one place\n") == [2]

    def test_every_number_in_a_run_is_flagged(self) -> None:
        assert _unlinked_references("Pull requests 91 and 92 opened.\n") == [1, 1]

    def test_a_number_after_a_linked_one_in_a_run_is_flagged(self) -> None:
        assert _unlinked_references("issues [4](https://x/4), 43 and 47\n") == [1, 1]

    def test_a_range_after_a_linked_phrase_is_flagged(self) -> None:
        assert _unlinked_references("[issues 14](https://x/14) through 18\n") == [1]

    def test_a_fully_linked_run_is_left_alone(self) -> None:
        document = "issues [4](https://x/4), [43](https://x/43) and [47](https://x/47)\n"
        assert _unlinked_references(document) == []

    def test_a_linked_number_is_left_alone(self) -> None:
        document = (
            "[#12](https://github.com/o/r/issues/12) and "
            "[issue\n52](https://github.com/o/r/issues/52)\n"
        )
        assert _unlinked_references(document) == []

    def test_a_reference_style_link_is_left_alone(self) -> None:
        assert _unlinked_references("See [issue 4][i4].\n\n[i4]: https://x/4\n") == []

    def test_a_finding_after_a_wrapped_link_names_its_own_line(self) -> None:
        assert _unlinked_references("[issue\n52](https://x/52)\nsee issue 4\n") == [3]

    def test_an_unclosed_bracket_does_not_hide_what_follows(self) -> None:
        assert _unlinked_references("a [draft note\n\nsee issue 4 here\n\n[x](y)\n") == [3]

    def test_a_run_wrapped_after_its_first_number_is_still_read(self) -> None:
        assert _unlinked_references("issues [4](https://x/4), 43\nand 47\n") == [1, 2]

    def test_a_range_wrapped_before_its_end_is_still_read(self) -> None:
        assert _unlinked_references("[issues 14](https://x/14) through\n18\n") == [2]

    def test_a_hyphenated_range_flags_both_ends(self) -> None:
        assert _unlinked_references("issues 3-5\n") == [1, 1]

    def test_a_run_joined_by_or_flags_each_number(self) -> None:
        assert _unlinked_references("issues 3 or 4\n") == [1, 1]

    def test_a_comma_then_or_flags_each_number(self) -> None:
        assert _unlinked_references("issues 3, or 4\n") == [1, 1]

    def test_a_comma_list_with_a_final_and_flags_each_number(self) -> None:
        assert _unlinked_references("issues 3, 4, and 5\n") == [1, 1, 1]

    def test_a_finding_after_a_multiline_comment_names_its_own_line(self) -> None:
        assert _unlinked_references("<!-- a\nb -->\nissue 4\n") == [3]

    def test_a_link_with_a_title_is_left_alone(self) -> None:
        assert _unlinked_references('[issue 4](https://x/4 "the title")\n') == []

    def test_a_number_right_after_a_link_is_flagged(self) -> None:
        assert _unlinked_references("[x](https://x)#4\n") == [1]

    def test_findings_come_back_in_line_order(self) -> None:
        assert _unlinked_references("issue 4\nsee #5\n") == [1, 2]

    def test_a_word_ending_in_issue_is_not_a_reference(self) -> None:
        assert _unlinked_references("tissue 4 and https://x/#12\n") == []

    def test_a_run_does_not_bridge_a_blank_line(self) -> None:
        assert _unlinked_references("## Open issues\n\n1. First\n") == []

    def test_a_date_is_not_an_issue(self) -> None:
        assert _unlinked_references("the issue 2026-09-18 raised\n") == []

    def test_a_code_span_and_a_fence_are_left_alone(self) -> None:
        assert _unlinked_references("Write `Part of #NN` here.\n\n```\nCloses #7\n```\n") == []

    def test_a_quotation_is_left_alone(self) -> None:
        assert _unlinked_references('One card read "#27 is planned too" once.\n') == []

    def test_a_curly_quotation_is_left_alone(self) -> None:
        assert _unlinked_references("He wrote \u201csee issue 12\u201d once.\n") == []

    def test_a_blockquote_is_not_a_quotation(self) -> None:
        assert _unlinked_references("> **Note:** issue 4 is open.\n") == [1]

    def test_an_html_comment_is_left_alone(self) -> None:
        assert _unlinked_references("<!-- see issue 4 -->\n") == []

    def test_an_anchor_and_an_html_entity_are_left_alone(self) -> None:
        assert _unlinked_references("Jump to x#2 or use &#38; here.\n") == []

    def test_every_markdown_file_links_its_issue_references(self) -> None:
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{n}"
            for path in markdown_files(REPO_ROOT)
            for n in _unlinked_references(path.read_text("utf-8"))
        ]
        assert not offenders, "unlinked issue or pull request numbers: " + ", ".join(offenders)
