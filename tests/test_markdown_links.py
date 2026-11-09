"""Every relative link in the repo's Markdown reaches its file and its heading.

Two layers, as in `test_markdown_hygiene.py`. Small documents pin how an
anchor is formed and which links are skipped, and the last test runs the
check over every Markdown file the repository owns.
"""

from __future__ import annotations

from pathlib import Path

from tests.support.markdown_links import anchor, anchors, broken_links
from tests.support.markdown_sweep import markdown_files

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_an_anchor_drops_punctuation_and_joins_words_with_hyphens() -> None:
    assert anchor("Rule 11: an environment scales out") == "rule-11-an-environment-scales-out"
    assert anchor("The runtime's credential") == "the-runtimes-credential"


def test_an_anchor_keeps_the_words_of_a_code_span() -> None:
    assert anchor("`ithildin switch pull --account <a>`") == "ithildin-switch-pull---account-a"


def test_a_repeated_heading_gets_a_numbered_anchor() -> None:
    assert anchors("## Price\n\n## Price\n\n## Price\n") == {"price", "price-1", "price-2"}


def test_an_anchor_drops_html_links_and_emphasis_markers() -> None:
    assert anchor('<a id="x"></a>Tag') == "tag"
    assert anchor("[A link](x.md) here") == "a-link-here"
    assert anchor("_under_ and **bold**") == "under-and-bold"
    assert anchor("snake_case stays") == "snake_case-stays"


def test_a_repeated_heading_skips_a_number_already_taken() -> None:
    assert anchors("## Foo 1\n\n## Foo\n\n## Foo\n") == {"foo-1", "foo", "foo-2"}


def test_a_heading_inside_a_fence_makes_no_anchor() -> None:
    assert anchors("```\n## Not a heading\n```\n\n## Real\n") == {"real"}


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_link_to_a_missing_file_is_broken(tmp_path: Path) -> None:
    doc = _write(tmp_path, "a.md", "See [b](b.md).\n")
    assert [b.reason for b in broken_links(doc, tmp_path)] == ["no such file"]


def test_a_link_to_a_missing_heading_is_broken(tmp_path: Path) -> None:
    _write(tmp_path, "b.md", "# B\n\n## Here\n")
    doc = _write(tmp_path, "a.md", "See [b](b.md#gone) and [b](b.md#here).\n")
    broken = broken_links(doc, tmp_path)
    assert [b.target for b in broken] == ["b.md#gone"]


def test_a_link_within_the_same_file_is_checked(tmp_path: Path) -> None:
    doc = _write(tmp_path, "a.md", "## Here\n\n[up](#here) and [gone](#gone)\n")
    assert [b.target for b in broken_links(doc, tmp_path)] == ["#gone"]


def test_a_link_into_a_subfolder_and_back_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "docs/design.md", "## Why\n")
    page = _write(tmp_path, "docs/architecture/07.md", "[why](../design.md#why)\n")
    assert broken_links(page, tmp_path) == []


def test_links_in_code_and_external_links_are_skipped(tmp_path: Path) -> None:
    doc = _write(
        tmp_path,
        "a.md",
        "`[x](missing.md)` and [web](https://example.com/x#y)\n\n```\n[x](missing.md)\n```\n",
    )
    assert broken_links(doc, tmp_path) == []


def test_every_relative_link_in_the_repo_reaches_its_target() -> None:
    broken = [b for path in markdown_files(REPO_ROOT) for b in broken_links(path, REPO_ROOT)]
    assert not broken, "\n".join(str(b) for b in broken)
