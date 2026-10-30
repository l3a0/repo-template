"""The generator behind the build board on GitHub Pages, run on canned GitHub.

``scripts/build_board.py`` reads GitHub through GraphQL and writes the six
sections the board's page draws. Two failures matter more than any other here.

1. A board the page refuses. The page refuses a whole section when one item
   lacks a field it reads, so one pull request linking no issue, or one issue
   with no milestone, would blank the board.
2. A board that reads as correct and is not. A failing check passed through in
   GitHub's spelling read as green, a stranger's review comment would move a
   pull request into the owner's queue, and an error read as an empty list
   would publish a board with no pull requests.

Each test feeds the generator a fake GitHub that answers its queries from
fixtures, so no test of the generator touches the network. The last tests run
the page on what the generator wrote, and check the workflows and the setup
script that publish it. The tests that read the update-build-board and
sync-prune-next skills, which live in the ``l3a0`` Claude Code plugin rather
than here, fetch them from GitHub at the plugin commit ``PLUGIN_COMMIT`` names.

Provenance: ported from ``tests/test_build_board_generator.py`` in
l3a0/quantitative-trading at commit ``6da0ee3``, landed here by the pull
request that closes l3a0/repo-template#24. On the way the fake repository
became ``octo-org/octo-repo``, the ``blocked-on-data`` cases went with that
kind, the workflow tests split between the caller and the reusable workflow
and gained the pinned checkout of the template, tests were added for the
board's repository and title, the label file and the github-pages
environment, and docstrings citing that repository's history were restated as
the rules they protect. The pull request that closes l3a0/repo-template#40
brought the ``blocked-on-data`` cases back, read through ``--data-label``, from
the same file at l3a0/quantitative-trading commit ``4755ac62``. The pull
request that closes l3a0/repo-template#45 added the ``--milestone-default``
cases, porting the default cases of ``tests/component/test_board_page.py`` in
l3a0/marketlake at commit ``cc9d3432`` from the page to ``default_milestone``.
The pull request that closes l3a0/repo-template#46 added the ``--ranking``
cases, from ``tests/unit/test_board_generator.py`` in l3a0/marketlake at the
same commit, with a ``board.json`` and the page's drawing of it that the
generator and page at l3a0/repo-template commit ``cf2959a3`` wrote.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_build_board import (
    PAGE,
    SKILL_DIR,
    assert_no_board_data,
    cards,
    run_fetch_page,
    served,
    text,
)
from tests.test_build_board import draw as draw_page

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_board.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "board.yml"
CALLED = REPO_ROOT / ".github" / "workflows" / "build-board.yml"
SETUP = REPO_ROOT / "scripts" / "setup-repo.sh"
REPO = "octo-org/octo-repo"
# The data label a repository passes as the reusable workflow's ``data-label``
# input. The one repository that marks such issues uses this name.
DATA_LABEL = "blocked-on-data"
NOW = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)
# The commit the fake repository's default branch stands at.
HEAD = "0a1b2c3d4e5f60718293a4b5c6d7e8f901234567"

# The update-build-board skill shares formats with the generator and the
# workflows here, and it lives in l3a0/claude-plugins. The tests read it at
# this commit, the head of the l3a0/claude-plugins pull request that releases
# 0.6.3, which merges together with the pull request that set this pin.
# GitHub keeps a pull request's head fetchable after it merges, and a later
# pull request moves the pin to the release's merge commit. A change here to a
# marker, a label or a string these tests compare with the skill fails them
# until the plugin releases a skill that matches and this pin moves to it. Any
# other format change rests on the plugin's own rule that a generator's format
# change ships with a plugin release in the same step.
PLUGIN_COMMIT = "7f392da18a227df8ce6c1f34b2bc57ade278d8aa"
PLUGIN_SKILLS = f"https://raw.githubusercontent.com/l3a0/claude-plugins/{PLUGIN_COMMIT}/skills/"

# The skill lists the strings these tests pin, so that a release keeps them.
# That list alone would satisfy most of the assertions, so the tests read the
# skill with it removed. The removal runs to the next heading, so the text it
# removes has to be the opener and the numbered items alone, with paragraphs
# indented under them, or a sentence added after the list would go unread.
# Removing it can only hide text, so the checks that text must never appear
# read the whole file instead.
PINNED_OPENER = "One repository has tests that read this skill's text."
PINNED_LIST = re.compile(rf"\n{re.escape(PINNED_OPENER)}.*?\n(?=## )", re.S)


@functools.cache
def _fetch(path: str) -> tuple[str, OSError | None]:
    """One file under the plugin's ``skills/`` at ``PLUGIN_COMMIT``, or why it failed.

    The failure is cached with the text, so a network that drops packets
    costs one timeout per run rather than one per test.
    """
    return _fetch_url(PLUGIN_SKILLS + path)


@functools.cache
def _fetch_url(url: str) -> tuple[str, OSError | None]:
    """The text at ``url``, or why it failed, cached as ``_fetch`` says."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8"), None
    except OSError as error:
        return "", error


def _online(fetched: tuple[str, OSError | None], what: str) -> str:
    """A fetched text, or a skip on an offline local run.

    CI sets ``CI=true``, and there a failed fetch fails the test, so the check
    cannot vanish from the run that gates a merge. An answer from GitHub that
    is not the file, such as a 404 for a pin naming no such commit or path,
    fails everywhere.
    """
    text, error = fetched
    if error is None:
        return text
    if isinstance(error, urllib.error.HTTPError):
        raise error
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        raise error
    pytest.skip(f"cannot fetch {what}: {error}")


def _plugin(name: str, skill: str = "update-build-board") -> str:
    """One file of one of the plugin's skills, the whole file, as ``_online`` reads it."""
    return _online(_fetch(f"{skill}/{name}"), f"the plugin's {name}")


# The template's own files at a commit, as GitHub serves them.
TEMPLATE_RAW = "https://raw.githubusercontent.com/l3a0/repo-template/"


def _template_at(sha: str, path: str) -> str:
    """One file of l3a0/repo-template at ``sha``, as ``_online`` reads it."""
    return _online(_fetch_url(f"{TEMPLATE_RAW}{sha}/{path}"), f"{path} at {sha}")


def _pinned_list_problems(listed: str) -> list[str]:
    """Each line of the removed list that is neither its opener nor in a numbered item.

    A line in an item starts with its number, or is indented at least three
    spaces, as a continuation or a nested paragraph after a blank line is.
    """
    opener, _, items = listed.strip("\n").partition("\n\n")
    problems = []
    if not opener.startswith(PINNED_OPENER) or "\n" in opener:
        problems.append(f"the opener is not one paragraph: {opener[:80]!r}")
    lines = items.split("\n")
    if not re.match(r"1\. ", lines[0]):
        problems.append("the list does not start at item 1")
    for line in lines:
        if line.strip() and not re.match(r"\d+\. | {3,}\S", line):
            problems.append(f"text in the list that is no numbered item: {line[:80]!r}")
    return problems


def _skill() -> str:
    """The plugin's ``SKILL.md``, without its list of the strings pinned here."""
    text = _plugin("SKILL.md")
    found = PINNED_LIST.findall(text)
    assert len(found) == 1, "the skill's list of pinned strings moved, so it would match itself"
    assert _pinned_list_problems(found[0]) == [], "the removal would hide text after the list"
    return PINNED_LIST.sub("\n", text)


_spec = importlib.util.spec_from_file_location("build_board", SCRIPT)
bb = importlib.util.module_from_spec(_spec)
sys.modules["build_board"] = bb
_spec.loader.exec_module(bb)


def conn(nodes: list, *, more: bool = False, cursor: str = "c1") -> dict:
    """One page of a GraphQL connection."""
    return {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


def issue(
    n: int,
    *,
    title: str | None = None,
    milestone: str | None = "Slice 1",
    labels: tuple[str, ...] = ("enhancement",),
    closed_by: tuple[int | tuple[int, str], ...] = (),
    mentioned_by: tuple[int, ...] = (),
    body: str = "",
    blocked_by: tuple[tuple, ...] = (),
    sub_issues: int | tuple[int, int] = 0,
    comments: tuple[tuple[str, str], ...] = (),
    colors: dict[str, str] | None = None,
    association: str = "OWNER",
) -> dict:
    """One open issue as the issues query returns it.

    ``sub_issues`` is the count of sub-issues, all open, or a ``(total,
    completed)`` pair, the two fields ``subIssuesSummary`` carries. The issue
    carries ``subIssues`` too, which the query reads when no ranking is set. A label
    carries a ``color`` field only when ``colors`` names it. GitHub always
    returns one, so a fixture without ``colors`` is a label whose colour the
    generator never needs to read.
    """
    total, completed = sub_issues if isinstance(sub_issues, tuple) else (sub_issues, 0)
    colors = colors or {}
    return {
        "id": f"I{n}",
        "number": n,
        "title": title or f"Issue {n}",
        "body": body,
        "authorAssociation": association,
        "milestone": {"title": milestone} if milestone is not None else None,
        "labels": conn(
            [{"name": x} | ({"color": colors[x]} if x in colors else {}) for x in labels]
        ),
        "blockedBy": conn([blocker(*b) for b in blocked_by]),
        "subIssues": {"totalCount": total},
        "subIssuesSummary": {"total": total, "completed": completed},
        "issueComments": conn([{"authorAssociation": a, "body": b} for a, b in comments]),
        "closedByPullRequestsReferences": conn([ref(p) for p in closed_by]),
        "timelineItems": conn(
            [{"source": {"number": p, "repository": {"nameWithOwner": REPO}}} for p in mentioned_by]
        ),
    }


def ref(entry: int | tuple[int, str]) -> dict:
    """One closing link, to a number here or to a ``(number, repository)`` pair."""
    n, repo = entry if isinstance(entry, tuple) else (entry, REPO)
    return {"number": n, "repository": {"nameWithOwner": repo}}


def blocker(n: int, state: str, repo: str = REPO) -> dict:
    """One "blocked by" link, to an issue in ``repo``."""
    return {"number": n, "state": state, "repository": {"nameWithOwner": repo}}


def check(
    name: str, conclusion: str | None, status: str = "COMPLETED", *, workflow: str | None = None
) -> dict:
    """One check run, from the workflow file ``workflow`` names when it names one."""
    run = {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}
    if workflow is not None:
        run["checkSuite"] = {"workflowRun": {"file": {"path": workflow}}}
    return run


def status(context: str, state: str) -> dict:
    return {"__typename": "StatusContext", "context": context, "state": state}


def pull(
    n: int,
    *,
    state: str = "OPEN",
    body: str = "",
    closes: tuple[int | tuple[int, str], ...] = (),
    comments: tuple[tuple[str, ...], ...] = (),
    contexts: tuple[dict, ...] = (check("test", "SUCCESS"),),
    fork: bool = False,
    committed: str | None = None,
    reviews: tuple[tuple[str | None, ...], ...] | None = None,
) -> dict:
    """One pull request as the query returns it.

    A comment is ``(association, body)``, or ``(association, body, createdAt)``.
    ``committed`` is the head commit's ``committedDate``, and ``reviews`` lists
    ``(association, body, submittedAt)``, or the same with the oid of the
    commit the review names, which is the head's ``c<n>`` when left out. Each
    of the three is left out of the fixture unless the test names it, as every
    fixture written before the ``review-heading`` input left them out, and the
    head's oid comes with either of the last two.
    """
    pr = {
        "id": f"P{n}",
        "number": n,
        "state": state,
        "body": body,
        "isCrossRepository": fork,
        "closingIssuesReferences": conn([ref(i) for i in closes]),
        "comments": conn(
            [
                {"authorAssociation": a, "body": b, **({"createdAt": t[0]} if t else {})}
                for a, b, *t in comments
            ]
        ),
        "commits": {
            "nodes": [
                {"commit": {"statusCheckRollup": {"id": f"R{n}", "contexts": conn(list(contexts))}}}
            ]
        },
    }
    head = pr["commits"]["nodes"][0]["commit"]
    if committed is not None or reviews is not None:
        head["oid"] = f"c{n}"
    if committed is not None:
        head["committedDate"] = committed
    if reviews is not None:
        pr["reviews"] = conn(
            [
                {
                    "authorAssociation": a,
                    "body": b,
                    "submittedAt": t,
                    "commit": {"oid": rest[0] if rest else f"c{n}"},
                }
                for a, b, t, *rest in reviews
            ]
        )
    return pr


class FakeGitHub:
    """Answers the generator's queries from fixtures, and records each call.

    Open issues and open pull requests are served in pages of the size the
    real queries ask for. A pull request asked for by number comes from
    ``prs``, whatever its state. ``nested`` serves the further pages of a
    nested list, keyed by the node's id and the list's name. ``head`` is the
    commit the default branch stands at, and None answers as a repository
    with no default branch.
    """

    def __init__(
        self,
        issues: list[dict],
        prs: list[dict],
        nested: dict | None = None,
        head: str | None = HEAD,
    ):
        self.issues = issues
        self.prs = {p["number"]: p for p in prs}
        self.nested = nested or {}
        self.head = head
        self.calls: list[str] = []

    def _page(self, nodes: list[dict], size: int, after: str | None) -> dict:
        start = int(after) if after else 0
        chunk = nodes[start : start + size]
        end = start + size
        return {
            "totalCount": len(nodes),
            "nodes": chunk,
            "pageInfo": {"hasNextPage": end < len(nodes), "endCursor": str(end)},
        }

    def __call__(self, query: str, variables: dict) -> dict:
        self.calls.append(query)
        if "node(id:$id)" in query:
            # Keyed by the cursor too, so a read that asks for the first page
            # again finds nothing rather than looping on it.
            field = re.search(r"\{ (\w+): \w+\(", query.split("... on", 1)[1]).group(1)
            return {"node": {field: self.nested[(variables["id"], field, variables["after"])]}}
        if "issues(states:OPEN" in query:
            page = self._page(self.issues, 100, variables.get("after"))
            return {"rateLimit": {"cost": 1}, "repository": {"issues": page}}
        if "pullRequests(states:OPEN" in query:
            open_prs = [p for p in self.prs.values() if p["state"] == "OPEN"]
            page = self._page(open_prs, 50, variables.get("after"))
            return {"rateLimit": {"cost": 1}, "repository": {"pullRequests": page}}
        if "defaultBranchRef" in query:
            ref = {"target": {"oid": self.head}} if self.head else None
            return {"rateLimit": {"cost": 1}, "repository": {"defaultBranchRef": ref}}
        found = {
            f"p{n}": self.prs.get(int(n)) for n in re.findall(r"pullRequest\(number:(\d+)", query)
        }
        return {"rateLimit": {"cost": 1}, "repository": found}


def build(
    gh: FakeGitHub,
    data_label: str = "",
    label_colors: str = "",
    sort_labels: str = "",
    milestone_default: str = "",
    **inputs: str,
) -> tuple[dict, dict]:
    """The board and report for ``gh``, with any of the keyword-only inputs."""
    return bb.build(
        gh,
        REPO,
        30,
        NOW,
        data_label=data_label,
        label_colors=label_colors,
        sort_labels=sort_labels,
        milestone_default=milestone_default,
        **inputs,
    )


def prs_of(board: dict) -> list[dict]:
    return board["prs"]["items"]


# ---- What the page refuses ----


def test_a_pull_request_naming_no_open_issue_gets_no_item() -> None:
    """Protects the whole prs section from one branch with no card.

    A dependency bump closes no issue and carries no ``Part of`` line, and in
    one sample of 60 pull requests 8 named no issue. A null issue would make the
    page refuse every pull request, so such a branch gets no item and the job
    summary names it. A branch naming only a closed issue gets none either.
    """
    gh = FakeGitHub(
        [issue(10)],
        [pull(434, body="Bumps ruff."), pull(435, closes=(9,)), pull(436, closes=(10,))],
    )
    board, report = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == [(436, 10)]
    assert report["open_prs_left_out"] == [434, 435]


def test_a_pull_request_closing_two_issues_gets_an_item_for_each() -> None:
    """Protects the second card of a branch closing two issues.

    The page keys pull requests by issue, so one item would leave the other
    card with no branch.
    """
    gh = FakeGitHub([issue(431), issue(448)], [pull(473, closes=(431, 448))])
    board, _ = build(gh)
    assert [(p["pr"], p["issue"], p["linked"]) for p in prs_of(board)] == [
        (473, 431, True),
        (473, 448, True),
    ]
    assert all("partOf" not in p for p in prs_of(board))


@pytest.mark.parametrize(
    ("body", "credited"),
    [
        # Line start, as most bodies write it.
        ("Part of #482. The rest of the issue stays open.\n", True),
        # Mid-paragraph, as sessions often write it.
        ("This adds the reader. Part of #482. The writer follows it.\n", True),
        # Inside a code span that crosses a line, so the phrase opens a line.
        ("The form reads `a body writes\nPart of #482 on a line`, as shown.\n", False),
        # Inside a fenced code block. The blank line in it ends a paragraph, so
        # only the fence rule, and not the code span rule, keeps it out.
        ("The form reads:\n\n```text\nA body:\n\nPart of #482\n```\n", False),
        # A backtick inside a fence and one after it. Fences come out before
        # spans, so the two never pair and swallow the reference between them.
        ("~~~\na ` b\n~~~\nPart of #482 and a ` tick.\n", True),
        # A paragraph ahead of the reference. Paragraphs rejoin with a
        # separator, so the reference does not run into the word before it.
        ("First paragraph\n\nPart of #482", True),
        # A span on each side. Scanning resumes after a span's closing run, so
        # that run does not open a second span reaching the reference.
        ("`x` Part of #482 `y`", True),
    ],
    ids=[
        "line-start",
        "mid-paragraph",
        "code-span",
        "fence",
        "fence-then-tick",
        "paragraphs",
        "two-spans",
    ],
)
def test_a_part_of_reference_counts_anywhere_outside_code(body: str, credited: bool) -> None:
    """Protects the ``Part of`` rule, which reads the phrase as GitHub reads a keyword.

    A reference counts anywhere in a body outside a code span or a fenced code
    block, the way GitHub reads a closing keyword. A rule reading only a line
    opening with the phrase gives a branch that writes it mid-paragraph no
    item. The code span here crosses a line, and the fence holds
    the phrase on a line of its own, so the earlier rule would have credited
    both.
    """
    gh = FakeGitHub([issue(482)], [pull(481, body=body)])
    board, _ = build(gh)
    expected = [(481, 482, False, True)] if credited else []
    assert [(p["pr"], p["issue"], p["linked"], p.get("partOf")) for p in prs_of(board)] == expected


def test_a_part_of_reference_after_a_fence_counts_in_a_crlf_body() -> None:
    """Protects the ``Part of`` rule on a body saved from GitHub's web editor.

    That editor ends each line with ``\\r\\n``. Read as it comes, the closing
    fence never matches, so the fence runs on to the end of the body and takes
    the reference below it, and no blank line ends a paragraph either. The body
    here holds a fence ahead of a reference outside it, which must count.
    """
    body = "## What\r\n\r\n```\r\ncode\r\n```\r\n\r\nPart of #482\r\n"
    gh = FakeGitHub([issue(482)], [pull(481, body=body)])
    board, _ = build(gh)
    assert [(p["pr"], p["issue"], p.get("partOf")) for p in prs_of(board)] == [(481, 482, True)]


def test_a_crlf_inside_a_code_span_keeps_its_paragraph() -> None:
    """Protects a ``Part of`` quoted in a code span that crosses a CRLF line end.

    Each ``\\r\\n`` is one line end. Read as ``\\r`` and ``\\n`` apart, it
    would be a blank line, which ends the paragraph, so the span would never
    close and the quoted reference would count.
    """
    gh = FakeGitHub([issue(4)], [pull(20, body="`x\r\nPart of #4`")])
    assert prs_of(build(gh)[0]) == []


@pytest.mark.parametrize(
    ("body", "credited"),
    [
        # A run of one backtick closes only at a run of one, so the two runs of
        # two inside it are code and the reference with them.
        ("`a`` Part of #482 ``b`", False),
        # A run nothing closes is literal text.
        ("A stray ` backtick, then Part of #482.", True),
        # A code span ends with its paragraph, so a backtick in each of two
        # paragraphs opens no span between them.
        ("A stray ` here.\n\nPart of #482, and another ` there.\n", True),
        # A span removed leaves a separator, so the words either side of it do
        # not join into the phrase.
        ("Part `x`of #482", False),
        # The same with no space on either side. GitHub shows code between the
        # words, so the separator must not be the space the phrase needs.
        ("Part`x`of #482", False),
        # A run of two nothing closes. Scanning goes on past it, and not from
        # inside it, so the span after it still holds the reference.
        ("A `` stray pair, then `Part of #482`.", False),
        # A line of only spaces ends a paragraph as an empty line does.
        ("A stray ` here.\n \nPart of #482, and another ` there.\n", True),
    ],
    ids=["width", "unclosed", "paragraph", "joined", "no-space", "stray-pair", "spaces-line"],
)
def test_a_code_span_closes_only_on_a_run_of_its_own_width(body: str, credited: bool) -> None:
    """Protects the reference from a span read wider or narrower than GitHub reads it.

    CommonMark closes a code span at the next run of exactly as many backticks
    in the same paragraph, and leaves a run nothing closes as literal text.
    Reading any run as a closer, or a lone backtick as opening to the end of
    the body, would drop a reference GitHub shows as plain text.
    """
    gh = FakeGitHub([issue(482)], [pull(481, body=body)])
    board, _ = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == ([(481, 482)] if credited else [])


@pytest.mark.parametrize(
    "body",
    ["XPart of #482", "Part of #482abc", "Part of 482", "Part of # 482"],
    ids=["word-before", "word-after", "no-hash", "hash-space"],
)
def test_a_part_of_reference_is_the_whole_phrase_and_nothing_between(body: str) -> None:
    """Protects the ``Part of`` rule from text that only contains the phrase.

    The phrase starts and ends on a word boundary, and the number follows its
    ``#`` with nothing between. Text joining a word to either end, or dropping
    the ``#`` or spacing it from the number, is not the reference GitHub
    renders as a link.
    """
    gh = FakeGitHub([issue(482)], [pull(481, body=body)])
    board, _ = build(gh)
    assert prs_of(board) == []


def test_lowercase_prose_naming_an_issue_is_no_part_of_reference() -> None:
    """Protects the ``Part of`` rule from prose that names another issue.

    A body can name its issue with the phrase and other issues in sentences
    such as "merged in PR 488, part of 458". Lowercase prose is not a
    reference. A capitalised quotation of another pull request's line is one,
    and that is the price of the rule: a sentence mentioning the phrase counts
    unless a code span holds it.
    """
    body = (
        "- The earlier change merged in PR #488, part of #458.\n"
        "part of #458 was the earlier change.\n"
        'It merged in #478 as "Part of #459".\n'
        "It also merged in #479 as `Part of #460`.\n"
        "\n"
        "Part of #462. The rest is built from the merged file.\n"
    )
    gh = FakeGitHub([issue(458), issue(459), issue(460), issue(462)], [pull(491, body=body)])
    board, _ = build(gh)
    assert [p["issue"] for p in prs_of(board)] == [459, 462]
    assert prs_of(board)[1] == {
        "pr": 491,
        "issue": 462,
        "state": "open",
        "linked": False,
        "reviewed": False,
        "review": "no review posted",
        "rollup": [["test", "success"]],
        "partOf": True,
    }


def test_a_merged_part_of_pull_request_stays_on_its_open_issue() -> None:
    """Protects the line saying what landed on an issue left open on purpose.

    A merged ``Part of`` pull request closes nothing, so GitHub's closing
    links never find it. The generator finds it through the issue's
    cross-references. A merged pull request that only mentions the issue in
    prose gets no item, and neither does a closed one naming nothing.
    """
    gh = FakeGitHub(
        [issue(463, mentioned_by=(490, 491, 492))],
        [
            pull(490, state="MERGED", body="Part of #463"),
            pull(491, state="MERGED", body="Its twin, from PR #490, part of #463."),
            pull(492, state="CLOSED", body="Tried #463 another way."),
        ],
    )
    board, report = build(gh)
    assert [(p["pr"], p["state"], p.get("partOf")) for p in prs_of(board)] == [
        (490, "merged", True)
    ]
    assert report["other_prs_read"] == 3
    assert report["open_prs_left_out"] == []


def test_a_merged_pull_request_whose_issue_stayed_open_reads_as_merged() -> None:
    """Protects the card held for a close by hand.

    A pull request merged with a closing link whose issue is still open has
    landed, and the page holds its card as needing only closing by hand. The
    issue's closing references are what find it.
    """
    gh = FakeGitHub([issue(352, closed_by=(479,))], [pull(479, state="MERGED", closes=(352,))])
    board, _ = build(gh)
    assert [(p["pr"], p["state"], p["linked"]) for p in prs_of(board)] == [(479, "merged", True)]


def test_an_issue_with_no_milestone_gets_an_empty_string() -> None:
    """Protects the tracker from an issue a stranger filed with no milestone.

    The page refuses a tracker item whose ``ms`` is not a string, which would
    blank the whole board.
    """
    board, _ = build(FakeGitHub([issue(7, milestone=None, labels=())], []))
    assert board["tracker"]["items"] == [
        {"n": 7, "ms": "", "label": "Issue 7", "kind": "ready", "needs": [], "labels": []}
    ]


def test_an_issue_with_no_judgement_set_reads_as_a_plain_card() -> None:
    """Protects the page's refusal rules on an issue nobody has ranked.

    A card with no labels, links or lines of the board's own is ready, waits on
    nothing, and appears in none of the three judgement sections. ``state``
    carries no list of missing fields, because the board now carries them all.
    """
    board, _ = build(FakeGitHub([issue(1), issue(2)], []))
    for name in ("working", "planned", "next"):
        assert board[name] == {"schema": 1, "items": []}
    assert {c["kind"] for c in board["tracker"]["items"]} == {"ready"}
    assert all(c["needs"] == [] and "after" not in c for c in board["tracker"]["items"])
    state = board["state"]
    assert state["updatedAt"] == "2026-10-11T15:00:00Z"
    assert state["issues"] == {"open": 2}
    assert state["longestGapMinutes"] == 30
    assert state["staleAfterMinutes"] == 630
    assert "lacks" not in state
    assert state["source"] == "github"


def test_the_board_names_its_repository_and_title() -> None:
    """Protects the shared page, which names no repository of its own.

    The page builds every link from ``state.repo`` and heads itself with
    ``state.title``. An empty title gives the repository's name.
    """
    state = build(FakeGitHub([issue(1)], []))[0]["state"]
    assert state["repo"] == REPO
    assert state["title"] == "octo-repo build board"
    titled = bb.build(FakeGitHub([issue(1)], []), REPO, 30, NOW, "Octo board")[0]["state"]
    assert titled["title"] == "Octo board"


def test_the_command_line_passes_the_title_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the reusable workflow's ``title`` input on its way to the page."""
    fake = FakeGitHub([issue(1)], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]
    assert bb.main([*argv, "--title", "Octo board"]) == 0
    assert json.loads((out / "board.json").read_text())["state"]["title"] == "Octo board"
    assert bb.main([*argv, "--title", ""]) == 0
    assert json.loads((out / "board.json").read_text())["state"]["title"] == "octo-repo build board"


# The three lines a caller can add, and the state keys they write. A board
# built with none of them carries exactly the keys it carried before they
# existed.
BEFORE_KEYS = {
    "schema",
    "repo",
    "title",
    "updatedAt",
    "issues",
    "source",
    "longestGapMinutes",
    "staleAfterMinutes",
}


def _with(gh: FakeGitHub, **lines: str) -> tuple[dict, dict]:
    """The board built with the caller's subtitle, note or head input."""
    return bb.build(gh, REPO, 30, NOW, **lines)


def test_a_caller_setting_no_line_gets_the_board_it_got_before() -> None:
    """Protects every current caller from the three new inputs.

    The template's own board, and the two repositories pinned to an older
    commit, set none of ``subtitle``, ``note`` or ``default-branch-head``. Their
    ``state`` carries exactly the keys it carried before, written identically
    whether the inputs are left out or passed empty, and the run sends exactly
    the requests it sent before, with no request for the default branch.
    """
    issues = [issue(1, mentioned_by=(7,)), issue(2)]
    prs = [pull(5, closes=(1,)), pull(7, state="MERGED", body="Part of #1")]
    left_out = FakeGitHub(issues, prs)
    board, _ = build(left_out)
    passed_empty = FakeGitHub(issues, prs)
    empty, _ = _with(passed_empty, subtitle="", note="", default_branch_head="")
    assert set(board["state"]) == BEFORE_KEYS
    assert json.dumps(empty) == json.dumps(board)
    assert passed_empty.calls == left_out.calls
    # One page of open issues, one page of open pull requests, and one batch
    # for the merged pull request 7 that issue 1 names.
    assert len(left_out.calls) == 3
    assert not any("defaultBranchRef" in q for q in left_out.calls)


# The board.json the generator at l3a0/repo-template commit cf2959a3, the last
# before these inputs, wrote for `every_case()` at `NOW` under `GOLDEN_CRON`.
# It was written once by running that commit's scripts/build_board.py, taken
# with `git show cf2959a3:scripts/build_board.py`, through its own `main()`.
# The file is never rewritten from the code under test, because a golden
# written by the head would compare the head with itself.
LINES_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "lines.json"
GOLDEN_CRON = 'on:\n  schedule:\n    - cron: "8,38 * * * *"\n'


class FixedNow(datetime):
    """``datetime`` whose ``now`` is ``NOW``, so a run's stamp is fixed."""

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return NOW


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [
            "--subtitle=",
            "--note=",
            "--default-branch-head=",
            "--label-colors=",
            "--sort-labels=",
        ],
    ],
    ids=["left-out", "passed-empty"],
)
def test_a_caller_setting_no_line_writes_the_bytes_cf2959a3_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: list[str]
) -> None:
    """Protects every current caller's board.json, byte for byte.

    The generator at cf2959a3 wrote ``LINES_GOLDEN`` from the same tracker
    before the three inputs existed. The head, with none of them set, has to
    write the same bytes to the file it publishes. The workflow passes every
    flag whether or not the caller set it, the two label inputs included, so
    passing them all empty counts too.
    """
    fake = every_case()
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setattr(bb, "datetime", FixedNow)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    workflow = tmp_path / "board.yml"
    workflow.write_text(GOLDEN_CRON, encoding="utf-8")
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(workflow), "--out", str(out)]
    assert bb.main([*argv, *lines]) == 0
    assert (out / "board.json").read_bytes() == LINES_GOLDEN.read_bytes()


def test_the_subtitle_reaches_the_state() -> None:
    """Protects the reusable workflow's ``subtitle`` input on its way to the page."""
    state = _with(FakeGitHub([issue(1)], []), subtitle="the order of work on the lake")[0]["state"]
    assert state["subtitle"] == "the order of work on the lake"
    assert set(state) == BEFORE_KEYS | {"subtitle"}


LINK_A = "https://github.com/octo-org/octo-repo/blob/main/docs/design.md"
LINK_B = "https://github.com/octo-org/octo-repo/blob/main/docs/build-plan.md"


@pytest.mark.parametrize(
    ("note", "pieces"),
    [
        ("Plain words only.", [{"text": "Plain words only."}]),
        (
            f"Read [the design doc]({LINK_A}) first.",
            [
                {"text": "Read "},
                {"text": "the design doc", "href": LINK_A},
                {"text": " first."},
            ],
        ),
        (
            f"[The design]({LINK_A}) and [the plan]({LINK_B})",
            [
                {"text": "The design", "href": LINK_A},
                {"text": " and "},
                {"text": "the plan", "href": LINK_B},
            ],
        ),
        (
            f"  The order\n follows   the rule:\n\tcapture first, in\n[the plan]({LINK_B}).\n",
            [
                {"text": "The order follows the rule: capture first, in "},
                {"text": "the plan", "href": LINK_B},
                {"text": "."},
            ],
        ),
        ("[brackets] and (parentheses) alone", [{"text": "[brackets] and (parentheses) alone"}]),
        (f"[a] [b]({LINK_A})", [{"text": "[a] "}, {"text": "b", "href": LINK_A}]),
    ],
    ids=["text", "one-link", "two-links", "line-breaks", "no-link", "bracket-then-link"],
)
def test_a_note_is_parsed_into_text_and_link_pieces(note: str, pieces: list[dict]) -> None:
    """Protects the note's one form of markup, parsed once here so the page only escapes.

    A folded YAML block keeps its line breaks in some forms, so every run of
    whitespace reads as one space.
    """
    state = _with(FakeGitHub([issue(1)], []), note=note)[0]["state"]
    assert state["note"] == pieces
    assert set(state) == BEFORE_KEYS | {"note"}


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "http://github.com/octo-org/octo-repo",
        "docs/design.md",
        'https://github.com/a"onmouseover="alert(1)',
        "https://github.com/a b",
        "https://",
        "https://github.com/a<b",
        "",
    ],
    ids=["javascript", "http", "relative", "quote", "space", "no-host", "angle", "empty"],
)
def test_a_note_linking_anywhere_but_https_stops_the_run(href: str) -> None:
    """Protects every reader's browser from a link the caller did not mean to draw.

    The run stops before reading GitHub, as a refused data label does, so the
    last good board stays up and the job summary says why.
    """
    gh = FakeGitHub([issue(1)], [])
    with pytest.raises(bb.BoardError, match="not an https:// address"):
        _with(gh, note=f"See [this]({href}).")
    assert gh.calls == []


def test_the_default_branch_head_costs_one_request_and_writes_seven_characters() -> None:
    """Protects the footer's commit, and every run that does not ask for it.

    The head is read through a request of its own, so a caller that sets the
    input pays exactly one more request than one that does not.
    """
    without = FakeGitHub([issue(1)], [])
    build(without)
    gh = FakeGitHub([issue(1)], [])
    state = _with(gh, default_branch_head="true")[0]["state"]
    assert state["main"] == "0a1b2c3"
    assert set(state) == BEFORE_KEYS | {"main"}
    assert len(gh.calls) == len(without.calls) + 1
    assert sum("defaultBranchRef" in q for q in gh.calls) == 1


@pytest.mark.parametrize("value", ["yes", "True", "false", "1", " true"])
def test_a_default_branch_head_other_than_true_stops_the_run(value: str) -> None:
    """Protects a caller from a value that reads as on and is not.

    The input takes an empty value or ``true``. Anything else stops the run
    before it reads GitHub, rather than quietly drawing no commit.
    """
    gh = FakeGitHub([issue(1)], [])
    message = f"the default-branch-head input {value!r} is neither empty nor true"
    with pytest.raises(bb.BoardError, match=f"^{re.escape(message)}$"):
        _with(gh, default_branch_head=value)
    assert gh.calls == []


@pytest.mark.parametrize(
    "head",
    [None, "not-a-commit-at-all", HEAD.upper()],
    ids=["missing", "not-hex", "upper-case"],
)
def test_a_missing_default_branch_head_stops_the_run(head: str | None) -> None:
    """Protects the footer from naming a commit the run never read.

    A repository GitHub answers with no default branch would leave the footer
    saying it was built against nothing, so the run stops and the last good
    board stays up. An answer that is not a lower-case hex commit stops it
    too, because the page names only seven lower-case hex characters.
    """
    gh = FakeGitHub([issue(1)], [], head=head)
    with pytest.raises(bb.BoardError, match="no default branch head"):
        _with(gh, default_branch_head="true")
    assert [q for q in gh.calls if "defaultBranchRef" in q] == [bb.HEAD_QUERY]


def test_a_repository_github_does_not_return_stops_the_run() -> None:
    """Protects the run from a null repository, which would otherwise raise AttributeError."""
    with pytest.raises(bb.BoardError, match="no default branch head"):
        bb.head_commit(lambda query, variables: {"repository": None}, "octo-org", "octo-repo")


def test_a_refused_note_stops_the_run_before_the_head_is_read() -> None:
    """Protects a caller asking for the head from a request a refused note wastes.

    Every input is checked before anything is read from GitHub, so a note
    that is refused sends no request, even the head's.
    """
    gh = FakeGitHub([issue(1)], [])
    with pytest.raises(bb.BoardError, match="not an https:// address"):
        _with(gh, note="See [x](http://example.com).", default_branch_head="true")
    assert gh.calls == []


def test_the_command_line_passes_the_three_lines_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the ``subtitle``, ``note`` and ``default-branch-head`` inputs on their way.

    The workflow passes each flag joined to its value by ``=`` whether or not
    the caller set it, so an empty value writes no key, and a refused note
    fails the run with its reason in the job summary.
    """
    fake = FakeGitHub([issue(1)], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def state() -> dict:
        return json.loads((out / "board.json").read_text())["state"]

    lines = [
        "--subtitle=-the order of work",
        f"--note=See [the design]({LINK_A}).",
        "--default-branch-head=true",
    ]
    assert bb.main([*argv, *lines]) == 0
    assert state()["subtitle"] == "-the order of work"
    assert state()["note"] == [
        {"text": "See "},
        {"text": "the design", "href": LINK_A},
        {"text": "."},
    ]
    assert state()["main"] == "0a1b2c3"
    assert bb.main([*argv, "--subtitle=", "--note=", "--default-branch-head="]) == 0
    assert set(state()) == BEFORE_KEYS
    (out / "board.json").unlink()
    assert bb.main([*argv, "--note=[x](http://example.com)"]) == 1
    assert not (out / "board.json").exists()
    assert "build_board: the note links to 'http://example.com'" in summary.read_text()


def test_the_command_line_with_none_of_the_three_flags_reads_no_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects a caller pinned before the inputs, whose workflow passes no flag.

    Each flag defaults to empty, so a run given none of them sends no request
    for the default branch and writes the keys it wrote before.
    """
    fake = FakeGitHub([issue(1)], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    assert bb.main(["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]) == 0
    assert set(json.loads((out / "board.json").read_text())["state"]) == BEFORE_KEYS
    assert not any("defaultBranchRef" in q for q in fake.calls)


def test_the_command_line_passes_the_data_label_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the reusable workflow's ``data-label`` input on its way to the kind.

    The workflow passes the input as ``--data-label`` whether or not the caller
    set it, so an empty value has to read as no data label, and a refused one
    has to fail the run rather than publish. A misspelt label fails no read, so
    the job summary counts the open issues carrying it, and a refusal puts its
    reason in the summary, where the run's page shows it. The workflow writes
    each flag joined to its value by ``=``, so a label starting with ``-`` is
    still read as the value.
    """
    fake = FakeGitHub([issue(1, labels=(DATA_LABEL,))], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def kind() -> str:
        return json.loads((out / "board.json").read_text())["tracker"]["items"][0]["kind"]

    summary = tmp_path / "summary.md"
    assert bb.main([*argv, f"--data-label={DATA_LABEL}"]) == 0
    assert kind() == "data"
    assert f"| Data label | `{DATA_LABEL}` on 1 open issues |" in summary.read_text()
    summary.unlink()
    assert bb.main([*argv, "--data-label="]) == 0
    assert kind() == "ready"
    assert "| Data label | none named |" in summary.read_text()
    summary.unlink()
    assert bb.main([*argv, "--data-label=blocked-on-dat"]) == 0
    assert kind() == "ready"
    assert "| Data label | `blocked-on-dat` on 0 open issues |" in summary.read_text()
    assert bb.main([*argv, "--data-label=-raw-data"]) == 0
    assert "| Data label | `-raw-data` on 0 open issues |" in summary.read_text()
    assert bb.main(argv) == 0
    assert kind() == "ready"
    (out / "board.json").unlink()
    summary.unlink()
    assert bb.main([*argv, "--data-label=deferred"]) == 1
    assert not (out / "board.json").exists()
    assert "build_board: the data label 'deferred' is a label the board already reads" in (
        summary.read_text()
    )


# ---- Label chips: GitHub's colours and name order ----

# The state keys a board carried before ``label-colors`` existed, in the order
# the generator writes them. ``board.json`` is written in insertion order, so a
# key added here changes the bytes every caller publishes.
STATE_KEYS = [
    "schema",
    "repo",
    "title",
    "updatedAt",
    "issues",
    "source",
    "longestGapMinutes",
    "staleAfterMinutes",
]


LABELS_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "labels.json"


def labels_github() -> FakeGitHub:
    """A repository whose board exercises every field a label input could move.

    Labels arrive out of name order and carry GitHub's colours, in either case.
    The issues also carry a band, a working label, a data-looking label, a
    verdict, an order line, after lines and "blocked by" links, and the pull
    requests close, reference and review them. One title is not ASCII, so the
    file's encoding is compared too.
    """
    return FakeGitHub(
        [
            issue(
                1,
                title="Colour the façade's chips",
                labels=("test", "deferred", "band:1", "enhancement"),
                colors={"test": "5319E7", "deferred": "ededed", "band:1": "c2e0c6"},
                body="Board order: 2\nBoard after: #3\n",
                comments=(("OWNER", "Board verdict: build after 2 passes"),),
            ),
            issue(
                2,
                milestone=None,
                labels=("working:build", "question", "Bug", "accessibility", "band:2"),
                colors={"question": "d876e3", "Bug": "D73A4A", "accessibility": "a2eeef\n"},
                blocked_by=((1, "OPEN"), (9, "CLOSED")),
            ),
            issue(
                3,
                labels=("replication", "blocked-on-data"),
                colors={"replication": "0e8a16"},
                mentioned_by=(22,),
            ),
            issue(4, labels=(), sub_issues=2, body="Board after: #1 #2\n"),
            issue(5, labels=("decision", "github_actions"), colors={"github_actions": "000000"}),
        ],
        [
            pull(20, closes=(1,), comments=(("OWNER", "## Review\n"),)),
            pull(21, body="Part of #2", contexts=(check("test", "FAILURE"),)),
            pull(22, state="MERGED", body="Part of #3"),
        ],
    )


def _main_writes(module: object, out: Path) -> bytes:
    """The bytes ``module.main`` writes to ``board.json`` for ``labels_github()``.

    The run reads GitHub through ``labels_github()`` and stamps the board at
    ``NOW``, so two generators' files can be compared byte for byte. Neither
    label flag is passed. The module's attributes are put back afterwards.
    """
    fake = labels_github()
    fake.requests, fake.retries, fake.cost = 1, 0, 1

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return NOW

    saved = module.GhGraphql, module.datetime
    module.GhGraphql, module.datetime = (lambda: fake), Frozen
    try:
        argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]
        assert module.main(argv) == 0
    finally:
        module.GhGraphql, module.datetime = saved
    return (out / "board.json").read_bytes()


def test_with_neither_label_input_the_board_is_the_bytes_cf2959a3_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects every caller that sets neither ``label-colors`` nor ``sort-labels``.

    ``tests/fixtures/build_board_generator/labels.json`` is the file that
    ``scripts/build_board.py`` at l3a0/repo-template ``cf2959a3``, the commit
    before the label inputs, wrote for ``labels_github()``. The generator here,
    run the same way with neither flag, has to write the same bytes. Comparing
    the file rather than a parsed copy catches a key added anywhere, a changed
    key order, and a change to how the file is serialised. To write the file
    again, run ``_main_writes`` on ``cf2959a3``'s generator, never on this one.
    """
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert _main_writes(bb, tmp_path / "site") == LABELS_GOLDEN.read_bytes()


def test_with_neither_label_input_the_board_is_the_one_it_was() -> None:
    """Protects every caller that sets neither ``label-colors`` nor ``sort-labels``.

    The labels keep the order GitHub returns, and ``state`` carries exactly the
    keys it carried before, so no ``labelColors``. Passing both inputs empty
    writes the same board as passing neither. The byte comparison with
    ``cf2959a3``'s output is the test above.
    """
    gh = lambda: FakeGitHub(  # noqa: E731
        [issue(1, labels=("test", "deferred", "band:1", "enhancement"))], []
    )
    board, _ = build(gh())
    assert card(board, 1)["labels"] == ["test", "deferred", "enhancement"]
    assert list(board["state"]) == STATE_KEYS
    assert build(gh(), label_colors="", sort_labels="")[0] == board


def test_sort_labels_puts_each_cards_labels_in_name_order() -> None:
    """Protects the chip order a caller setting ``sort-labels`` gets.

    GitHub returns an issue's labels in the order they were added. The sort is
    Python's code-point order, so a capital sorts ahead of a lower-case letter,
    and the board's own labels are still left off. Sorting writes no colours.
    """
    gh = FakeGitHub(
        [
            issue(1, labels=("test", "deferred")),
            issue(2, labels=("working:build", "question", "band:2", "Bug", "accessibility")),
        ],
        [],
    )
    board, _ = build(gh, sort_labels="true")
    assert card(board, 1)["labels"] == ["deferred", "test"]
    assert card(board, 2)["labels"] == ["Bug", "accessibility", "question"]
    assert list(board["state"]) == STATE_KEYS


def test_label_colors_writes_each_card_labels_colour_lower_cased() -> None:
    """Protects the map the page fills each chip from under ``label-colors``.

    The map holds each label a card draws, keyed by name in sorted order, with
    GitHub's colour lower-cased, since GitHub returns some in capitals. The
    board's own labels draw no chip, so they are left out, and so is a colour
    that is not six hex digits, which the page would write into a style
    attribute. The labels keep GitHub's order, because colouring sorts nothing.
    """
    gh = FakeGitHub(
        [
            issue(
                1,
                labels=(
                    "opentofu",
                    "band:1",
                    "working:build",
                    "broken",
                    "short",
                    "long",
                    "newline",
                ),
                colors={
                    "opentofu": "F9DB4E",
                    "band:1": "ededed",
                    "working:build": "0e8a16",
                    "broken": "zzzzzz",
                    "short": "fff",
                    "long": "a2eeef0",
                    "newline": "a2eeef\n",
                },
            ),
            issue(2, labels=("enhancement",), colors={"enhancement": "a2eeef"}),
        ],
        [],
    )
    board, _ = build(gh, label_colors="true")
    assert board["state"]["labelColors"] == {"enhancement": "a2eeef", "opentofu": "f9db4e"}
    assert list(board["state"]["labelColors"]) == ["enhancement", "opentofu"]
    assert list(board["state"]) == [*STATE_KEYS, "labelColors"]
    assert card(board, 1)["labels"] == ["opentofu", "broken", "short", "long", "newline"]


def test_the_page_and_the_generator_accept_the_same_colours() -> None:
    """Protects the colour check from drifting between its two halves.

    The generator keeps a colour only when it matches ``HEX_COLOUR`` whole, and
    the page checks it again before writing it into a style attribute. A
    pattern that changed on one side alone would drop colours the other keeps.
    """
    found = re.findall(r"^const HEX_COLOUR = /(.*)/;$", PAGE.read_text(encoding="utf-8"), re.M)
    assert found == [f"^{bb.HEX_COLOUR.pattern}$"]


def test_label_colors_with_no_coloured_label_writes_an_empty_map() -> None:
    """Protects the map's presence, which follows the input rather than its contents.

    A caller that sets ``label-colors`` gets ``state.labelColors`` even when no
    card draws a label with a usable colour, so the key says the input reached
    the generator.
    """
    board, _ = build(FakeGitHub([issue(1, labels=("test",))], []), label_colors="true")
    assert board["state"]["labelColors"] == {}


def test_a_label_read_on_a_later_page_carries_its_colour() -> None:
    """Protects the colour of a label past an issue's first hundred.

    The first page of labels comes with the issue, and the rest are read again
    from where it stopped. Both reads select ``color`` beside ``name``, or a
    label read on a later page would draw the page's own colour.
    """
    first = issue(1, labels=("enhancement",), colors={"enhancement": "a2eeef"})
    first["labels"]["pageInfo"]["hasNextPage"] = True
    later = conn([{"name": "question", "color": "D876E3"}], cursor="c2")
    gh = FakeGitHub([first], [], nested={("I1", "labels", "c1"): later})
    board, _ = build(gh, label_colors="true")
    assert board["state"]["labelColors"] == {"enhancement": "a2eeef", "question": "d876e3"}
    assert "nodes{name color}" in bb.ISSUES_QUERY
    assert [q for q in gh.calls if "node(id:$id)" in q] == [
        "query($id:ID!, $after:String) { node(id:$id) { ... on Issue { labels: labels(first:100, "
        "after:$after) { pageInfo{hasNextPage endCursor} nodes{ name color } } } } }"
    ]


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--label-colors", "yes"),
        ("--label-colors", "True"),
        ("--sort-labels", "name"),
        ("--sort-labels", "false"),
    ],
)
def test_a_label_input_other_than_empty_or_true_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str, value: str
) -> None:
    """Protects a caller from a board that quietly ignores its input.

    Each input takes empty or ``true``. Any other value stops the run before
    it reads GitHub, and the reason goes under ``## Board run failed`` in the
    job summary, where the run's page shows it, since the run stops the same
    way until someone edits the caller.
    """
    fake = FakeGitHub([issue(1)], [])
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]
    assert bb.main([*argv, f"{flag}={value}"]) == 1
    assert fake.calls == []
    assert not (out / "board.json").exists()
    name = flag.removeprefix("--")
    assert summary.read_text() == (
        "## Board run failed\n\n"
        f"build_board: the {name} input {value!r} is neither empty nor true\n"
    )


def test_the_command_line_passes_the_label_inputs_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the two label inputs on their way from the workflow to the board.

    The workflow passes each as a flag joined to its value by ``=``, whether or
    not the caller set it, so an empty value has to read as off. A run of the
    script that leaves both flags out reads them as off too.
    """
    fake = FakeGitHub([issue(1, labels=("test", "deferred"), colors={"test": "5319E7"})], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def written() -> dict:
        return json.loads((out / "board.json").read_text())

    assert bb.main([*argv, "--label-colors=true", "--sort-labels=true"]) == 0
    assert written()["state"]["labelColors"] == {"test": "5319e7"}
    assert written()["tracker"]["items"][0]["labels"] == ["deferred", "test"]
    assert bb.main([*argv, "--label-colors=true"]) == 0
    assert written()["state"]["labelColors"] == {"test": "5319e7"}
    assert written()["tracker"]["items"][0]["labels"] == ["test", "deferred"]
    assert bb.main([*argv, "--sort-labels=true"]) == 0
    assert "labelColors" not in written()["state"]
    assert written()["tracker"]["items"][0]["labels"] == ["deferred", "test"]
    assert bb.main([*argv, "--label-colors=", "--sort-labels="]) == 0
    assert "labelColors" not in written()["state"]
    assert written()["tracker"]["items"][0]["labels"] == ["test", "deferred"]
    assert bb.main(argv) == 0
    assert "labelColors" not in written()["state"]
    assert written()["tracker"]["items"][0]["labels"] == ["test", "deferred"]


def test_the_page_fills_the_chips_the_generator_coloured(tmp_path: Path) -> None:
    """Protects the join between the colour map and the chip that reads it.

    A map the generator writes under a key the page does not read would leave
    every chip in the page's own colours, and neither half's tests would see it.
    The band label ranks the card, so the page's short view draws it.
    """
    gh = FakeGitHub(
        [
            issue(
                1,
                labels=("band:1", "replication", "enhancement"),
                colors={"band:1": "ededed", "replication": "1D76DB"},
            )
        ],
        [],
    )
    board, _ = build(gh, label_colors="true", sort_labels="true")
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids, _ = run_fetch_page(tmp_path, [served(board)])
    drawn = ids["flow"]["html"] + ids["board"]["html"]
    assert (
        '<b style="color:#2F7F86">enhancement</b>'
        '<b style="background:#1d76db;border-color:#1d76db;color:#000">replication</b>'
    ) in drawn


# ---- The milestone default ----
#
# ``--milestone-default`` turns on the page's milestone selector. Only a named
# one cuts each milestone's title at its first comma and writes
# ``state.milestoneDefault``, so a caller naming none gets the board it had.


@pytest.mark.parametrize(
    ("names", "chosen"),
    [
        (["MVP 4", "MVP 4", ""], "MVP 4"),
        (["MVP 10", "MVP 9", ""], "MVP 9"),
        (["MVP 4", "MVP 3", ""], "MVP 3"),
        (["MVP 12", "MVP 10", ""], "MVP 10"),
        (["Post-MVP 1", "MVP 4", ""], "MVP 4"),
        (["MVP 4b", "MVPs", ""], None),
        (["MVP4", "mvp 2", ""], None),
        (["MVP ", "MVP 0", ""], "MVP 0"),
        (["", "", ""], None),
    ],
    ids=[
        "one open MVP",
        "a number, not text",
        "the lowest open MVP",
        "two digits",
        "a prefix",
        "no MVP name",
        "near misses",
        "zero",
        "none",
    ],
)
def test_the_default_is_the_lowest_numbered_match(names: list[str], chosen: str | None) -> None:
    """Protects the milestone the page opens on, compared as a number.

    These are marketlake's cases for its page's default, which matched
    ``^MVP (\\d+)$``. MVP 10 comes after MVP 9, a name with anything around
    the number is no match, and None opens the page on every milestone. A
    card with no milestone has the empty name, which no pattern matches.
    """
    assert bb.default_milestone("MVP <n>", names) == chosen


@pytest.mark.parametrize(
    ("pattern", "names", "chosen"),
    [
        ("v1.<n>", ["v1x2", "v1.3"], "v1.3"),
        ("v1.<n>", ["v1x2"], None),
        ("Backlog", ["Backlog", "Backlog 2"], "Backlog"),
        ("Backlog", ["Backlog 2"], None),
        ("MVP <n>", ["MVP 4", "MVP 04"], "MVP 04"),
        ("<n>", ["12", "3", "x"], "3"),
        ("Slice <n> (beta)", ["Slice 2 (beta)", "Slice 1 (beta"], "Slice 2 (beta)"),
    ],
    ids=[
        "a dot is a dot",
        "a dot matches no other character",
        "no number matches one name",
        "no number matches only that name",
        "a tie goes to the name that sorts first",
        "a number alone",
        "brackets are literal",
    ],
)
def test_the_pattern_matches_its_literal_parts_exactly(
    pattern: str, names: list[str], chosen: str | None
) -> None:
    """Protects a pattern from matching names its caller never wrote.

    Every character but ``<n>`` stands for itself, so a dot or a bracket in a
    milestone's name is escaped rather than read as a regular expression. A
    tie between two spellings of one number goes to the name that sorts
    first, so two runs over the same issues open on the same milestone.
    """
    assert bb.default_milestone(pattern, names) == chosen


def test_a_number_too_long_to_convert_is_no_match() -> None:
    """Protects a run from a milestone named with thousands of digits.

    Python refuses to convert more than 4,300 digits to an int, so an
    unbounded number would stop every run on that title. A number of more
    than 18 digits matches no pattern, and the default falls to the next.
    """
    assert bb.default_milestone("MVP <n>", ["MVP " + "9" * 5000, "MVP 3"]) == "MVP 3"
    assert bb.default_milestone("MVP <n>", ["MVP " + "1" * 19]) is None
    assert bb.default_milestone("MVP <n>", ["MVP " + "1" * 18]) == "MVP " + "1" * 18


def test_a_tie_opens_on_one_milestone_whatever_the_hash_seed() -> None:
    """Protects two runs over the same issues from opening on different milestones.

    ``default_milestone`` reads the names through a set, whose order follows
    Python's string hash, which changes from one process to the next. Three
    spellings of one number tie, so only the name breaking the tie keeps the
    answer the same in every process.
    """
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('bb', {str(SCRIPT)!r})\n"
        "bb = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(bb)\n"
        "print(bb.default_milestone('MVP <n>', ['MVP 4', 'MVP 04', 'MVP 004']))\n"
    )
    answers = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
        ).stdout.strip()
        for seed in range(8)
    }
    assert answers == {"MVP 004"}


def test_the_short_name_is_stripped_on_both_sides() -> None:
    """Protects a title written with spaces around its short name."""
    assert bb.milestone_short(" MVP 4 , serve the bars") == "MVP 4"
    assert bb.milestone_short("MVP 4") == "MVP 4"
    assert bb.milestone_short("") == ""


@pytest.mark.parametrize(
    ("pattern", "reason"),
    [
        ("MVP <n>.<n>", "names <n> more than once"),
        ("MVP <n>, serve", "has a comma"),
    ],
)
def test_a_milestone_default_no_name_can_match_is_refused(pattern: str, reason: str) -> None:
    """Protects a board from a pattern that would open it on every milestone in silence.

    A pattern with two numbers has no single number to compare, and one with
    a comma can match no short name, since every name is cut at its first
    comma. The run stops before reading GitHub rather than publish that.
    """
    gh = FakeGitHub([issue(1)], [])
    with pytest.raises(bb.BoardError, match=reason):
        build(gh, milestone_default=pattern)
    assert gh.calls == []


def test_with_no_milestone_default_the_board_keeps_whole_titles_and_no_default() -> None:
    """Protects every caller that names no milestone default from a change to its board.

    Two current callers have milestone titles with a comma. With the input
    empty, ``ms`` keeps the whole title, ``state`` carries no
    ``milestoneDefault``, and two titles that would cut to one name report
    nothing, so the board and its job summary are what they were.
    """
    gh = FakeGitHub(
        [
            issue(1, milestone="Round 1, gaps the first review found"),
            issue(2, milestone="Round 1, the second pass"),
            issue(3, milestone=None),
        ],
        [],
    )
    board, report = build(gh)
    assert [c["ms"] for c in board["tracker"]["items"]] == [
        "Round 1, gaps the first review found",
        "Round 1, the second pass",
        "",
    ]
    assert "milestoneDefault" not in board["state"]
    assert report["label_conflicts"] == []


def test_a_milestone_default_cuts_each_title_and_names_the_milestone() -> None:
    """Protects the selector's names and the milestone the page opens on.

    Each title is cut at its first comma and stripped, a card with no
    milestone keeps the empty name, and the default is resolved against the
    cut names, since "MVP 4, serve the bars" never matches ``MVP <n>`` whole.
    """
    gh = FakeGitHub(
        [
            issue(1, milestone="MVP 5, take orders"),
            issue(2, milestone="MVP 4 , serve the bars"),
            issue(3, milestone="Round 1, gaps the first review found"),
            issue(4, milestone=None),
            issue(5, milestone="Backlog"),
            issue(6, milestone="MVP 4 , serve the bars, then orders"),
        ],
        [],
    )
    board, report = build(gh, milestone_default="MVP <n>")
    assert [c["ms"] for c in board["tracker"]["items"]] == [
        "MVP 5",
        "MVP 4",
        "Round 1",
        "",
        "Backlog",
        "MVP 4",
    ]
    assert board["state"]["milestoneDefault"] == "MVP 4"
    assert report["label_conflicts"] == [
        'milestones "MVP 4 , serve the bars" and "MVP 4 , serve the bars, then orders" '
        'both cut to "MVP 4"'
    ]
    board, _ = build(gh, milestone_default="Slice <n>")
    assert board["state"]["milestoneDefault"] is None


def test_two_titles_cutting_to_one_name_are_reported() -> None:
    """Protects the selector from merging two milestones without saying so.

    Two open milestones whose titles cut to one name would read as one entry
    in the selector, so the run lists them where the job summary lists what
    disagrees, three of them as a group. The groups and the titles in each
    come out in name order, whatever order the issues were filed in.
    """
    gh = FakeGitHub(
        [
            issue(1, milestone="Slice 1, b"),
            issue(2, milestone="Slice 1"),
            issue(3, milestone="Slice 1, a"),
            issue(4, milestone="MVP 4, take orders"),
            issue(5, milestone="MVP 4, take orders"),
            issue(6, milestone="MVP 4, serve the bars"),
        ],
        [],
    )
    _, report = build(gh, milestone_default="MVP <n>")
    assert report["label_conflicts"] == [
        'milestones "MVP 4, serve the bars" and "MVP 4, take orders" both cut to "MVP 4"',
        'milestones "Slice 1", "Slice 1, a" and "Slice 1, b" all cut to "Slice 1"',
    ]


def test_the_command_line_passes_the_milestone_default_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the reusable workflow's ``milestone-default`` input on its way to the page.

    The workflow passes the input whether or not the caller set it, so an
    empty value writes no ``milestoneDefault`` and no summary row, which keeps
    the summary's other rows where they were. A set one names what it matched,
    and one that matches nothing says so, because a misspelt pattern fails no
    read. The pattern goes in a code span, or GitHub's renderer would read
    ``<n>`` as a tag. A refused one fails the run with its reason in the
    summary.
    """
    fake = FakeGitHub([issue(1, milestone="MVP 4, serve the bars")], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def state() -> dict:
        return json.loads((out / "board.json").read_text())["state"]

    assert bb.main([*argv, "--milestone-default=MVP <n>"]) == 0
    assert state()["milestoneDefault"] == "MVP 4"
    assert summary.read_text().endswith(
        "| Data label | none named |\n"
        "| Review heading | none named |\n"
        "| Milestone default | `MVP <n>` opens on MVP 4 |\n"
    )
    summary.unlink()
    assert bb.main([*argv, "--milestone-default=Slice <n>"]) == 0
    assert state()["milestoneDefault"] is None
    assert "| Milestone default | `Slice <n>` matches no open milestone |" in summary.read_text()
    summary.unlink()
    assert bb.main([*argv, "--milestone-default="]) == 0
    assert "milestoneDefault" not in state()
    assert summary.read_text().endswith(
        "| Data label | none named |\n| Review heading | none named |\n"
    )
    summary.unlink()
    assert bb.main(argv) == 0
    assert "milestoneDefault" not in state()
    (out / "board.json").unlink()
    summary.unlink()
    assert bb.main([*argv, "--milestone-default=MVP <n>, x"]) == 1
    assert not (out / "board.json").exists()
    assert "build_board: the milestone default 'MVP <n>, x' has a comma" in summary.read_text()


MILESTONE_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "milestones.json"


def milestone_tracker() -> FakeGitHub:
    """A repository whose milestone titles hold one comma, two, or none, and one with none."""
    return FakeGitHub(
        [
            issue(1, milestone="Round 1, gaps the first review found", labels=("band:1",)),
            issue(2, milestone="Round 1, the second pass", blocked_by=((1, "OPEN"),)),
            issue(3, milestone="MVP 4, serve the bars, then orders", labels=("decision",)),
            issue(4, milestone="MVP 4", labels=("working:build",)),
            issue(5, milestone=None, labels=()),
            issue(
                6,
                milestone="Slice 1",
                sub_issues=2,
                comments=(("OWNER", "Board verdict: build after 2 passes"),),
            ),
        ],
        [pull(20, closes=(4,))],
    )


@pytest.mark.parametrize("argv", [[], ["--milestone-default="]], ids=["left out", "empty"])
def test_with_no_milestone_default_the_board_is_the_bytes_the_base_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """Protects every caller that names no milestone default from a board that moves.

    ``MILESTONE_GOLDEN`` is the ``board.json`` that the command line at
    l3a0/repo-template commit cf2959a3, before the input existed, wrote for
    ``milestone_tracker``. This run has to write the same bytes, read as the
    command line writes them, whether the input is left out or passed empty
    as the workflow passes it.
    """

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return NOW

    fake = milestone_tracker()
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setattr(bb, "datetime", Frozen)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    base = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]
    assert bb.main([*base, *argv]) == 0
    written = (out / "board.json").read_bytes()
    assert written == MILESTONE_GOLDEN.read_bytes().removesuffix(b"\n")


def test_the_page_opens_on_the_milestone_the_generator_names(tmp_path: Path) -> None:
    """Protects the join between the generator's default and the page's selector.

    The page lists the cut names, opens on the one the generator resolved, and
    draws only that milestone's cards.
    """
    gh = FakeGitHub(
        [
            issue(1, milestone="MVP 4, serve the bars", labels=("band:1",)),
            issue(2, milestone="MVP 5, take orders", labels=("band:1",)),
            issue(3, milestone=None, labels=("band:1",)),
        ],
        [],
    )
    board, _ = build(gh, milestone_default="MVP <n>")
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = draw_page(tmp_path, board)
    assert ids["mssel"]["value"] == "MVP 4"
    assert '<option value="MVP 5">MVP 5 (1)</option>' in ids["mssel"]["html"]
    assert cards(ids, "board") == {1}


# ---- The judgement fields, from labels, links and lines ----


def card(board: dict, n: int) -> dict:
    return next(c for c in board["tracker"]["items"] if c["n"] == n)


@pytest.mark.parametrize(
    ("labels", "subs", "data_label", "kind"),
    [
        ((), 0, "", "ready"),
        (("question",), 0, "", "ready"),
        (("decision",), 0, "", "decision"),
        (("deferred",), 0, "", "deferred"),
        (("deferred", "decision"), 0, "", "deferred"),
        (("decision",), 3, "", "parent"),
        ((), 1, "", "parent"),
        ((DATA_LABEL,), 0, DATA_LABEL, "data"),
        ((DATA_LABEL, "deferred"), 0, DATA_LABEL, "data"),
        (("decision", DATA_LABEL), 0, DATA_LABEL, "data"),
        ((DATA_LABEL,), 3, DATA_LABEL, "parent"),
        (("deferred",), 0, DATA_LABEL, "deferred"),
        ((DATA_LABEL,), 0, "", "ready"),
        (("waiting-on-data",), 0, "waiting-on-data", "data"),
    ],
)
def test_a_cards_kind_comes_from_its_labels_and_sub_issues(
    labels: tuple[str, ...], subs: int, data_label: str, kind: str
) -> None:
    """Protects the kind word and the column a card's kind decides.

    ``question`` is not ``decision``, because an issue can carry it while it
    waits on research rather than on the owner. Any sub-issue makes a parent,
    open or closed. The data label sets the kind ``data`` ahead of
    ``deferred`` and ``decision``, and only when the caller names it, so with an
    empty input ``blocked-on-data`` is an ordinary label. The kind follows
    whatever label the caller names rather than one spelling.
    """
    board, _ = build(FakeGitHub([issue(1, labels=labels, sub_issues=subs)], []), data_label)
    assert card(board, 1)["kind"] == kind


def test_an_empty_data_label_reads_the_kinds_it_read_before() -> None:
    """Protects every caller that names no data label from a change to its board.

    The kind labels read are exactly the module's two, so no label becomes the
    kind ``data`` and nothing reads an empty label name as matching.
    """
    assert (
        bb.kind_labels("") == bb.KIND_LABELS == (("deferred", "deferred"), ("decision", "decision"))
    )
    assert bb.kind_labels(DATA_LABEL) == ((DATA_LABEL, "data"), *bb.KIND_LABELS)
    board, _ = build(FakeGitHub([issue(1, labels=("", DATA_LABEL))], []))
    assert {c["kind"] for c in board["tracker"]["items"]} == {"ready"}


@pytest.mark.parametrize("label", ["deferred", "decision", "working:build", "band:2"])
def test_a_data_label_the_board_already_reads_is_refused(label: str) -> None:
    """Protects a board from reading one label as two things.

    Named as the data label, ``deferred`` would make every deferred card report
    a conflict and read as waiting on data. The run stops before reading
    GitHub rather than publish that.
    """
    gh = FakeGitHub([issue(1, labels=(label,))], [])
    with pytest.raises(bb.BoardError, match="already reads"):
        build(gh, label)
    assert gh.calls == []


def test_needs_keeps_only_blockers_that_are_open_issues() -> None:
    """Protects a card from waiting on work that has landed.

    A "blocked by" link outlives its blocker closing, and the page draws only
    open issues. So a closed
    blocker, or one that is not an open issue here, drops out.
    """
    gh = FakeGitHub(
        [
            issue(1),
            issue(2, blocked_by=((1, "OPEN"), (3, "CLOSED"), (9, "OPEN"))),
        ],
        [],
    )
    board, _ = build(gh)
    assert card(board, 2)["needs"] == [1]
    assert card(board, 1)["needs"] == []


def test_a_blocker_in_another_repository_is_not_this_repositorys_issue() -> None:
    """Protects a card from waiting on an issue that shares only a number.

    A "blocked by" link can name an issue in any repository, and issue 1 in a
    sibling repository is not issue 1 here.
    """
    gh = FakeGitHub([issue(1), issue(2, blocked_by=((1, "OPEN", "octo-org/other"),))], [])
    board, _ = build(gh)
    assert card(board, 2)["needs"] == []


def test_lines_inside_a_fenced_block_are_not_read() -> None:
    """Protects the board from a comment or body quoting the formats.

    A skill or a review that shows the verdict line in a fence is explaining
    it, not recording one.
    """
    fenced = "The format:\n\n```text\nBoard verdict: build after 5 passes\n```\n"
    body = "```\nBoard order: 3\nBoard after: #1\n```\n"
    gh = FakeGitHub(
        [issue(1), issue(2, labels=("band:1",), body=body, comments=(("OWNER", fenced),))], []
    )
    board, _ = build(gh)
    assert board["planned"]["items"] == []
    assert board["next"]["items"] == [{"issue": 2, "band": 1, "ready": "plan"}]
    assert "after" not in card(board, 2)


def test_an_issue_claiming_two_kinds_is_reported() -> None:
    """Protects a kind label that loses from going unnoticed."""
    gh = FakeGitHub(
        [
            issue(1, labels=("decision", "deferred")),
            issue(2, labels=("decision",), sub_issues=1),
            issue(3, labels=("deferred", DATA_LABEL)),
        ],
        [],
    )
    board, report = build(gh, DATA_LABEL)
    assert [c["kind"] for c in board["tracker"]["items"]] == ["deferred", "parent", "data"]
    assert report["label_conflicts"] == [
        "#1 reads as deferred and decision, read as deferred",
        "#2 reads as parent and decision, read as parent",
        "#3 reads as data and deferred, read as data",
    ]


@pytest.mark.parametrize(
    "body",
    [
        "Note: Board verdict: build after 5 passes",
        "Board verdict: build after 5 passes, and then some",
    ],
)
def test_a_verdict_line_must_stand_alone(body: str) -> None:
    """Protects the plan marker from prose that mentions the format."""
    board, _ = build(FakeGitHub([issue(1, comments=(("OWNER", body),))], []))
    assert board["planned"]["items"] == []


@pytest.mark.parametrize(
    "body",
    [
        "See Board order: 3\nBoard after: #2\n",
        "Board order: 3 or so\nNot Board after: #2\n",
    ],
)
def test_order_and_after_lines_must_stand_alone(body: str) -> None:
    """Protects the sort from a sentence that quotes a board line mid-way."""
    gh = FakeGitHub([issue(1, labels=("band:1",), body=body), issue(2)], [])
    board, _ = build(gh)
    entry = board["next"]["items"][0]
    assert "order" not in entry
    if body.startswith("See"):
        assert card(board, 1)["after"] == [2]
    else:
        assert "after" not in card(board, 1)


@pytest.mark.parametrize("label", ["old-band:1", "band:1-old"])
def test_only_a_whole_band_label_ranks_a_card(label: str) -> None:
    """Protects the priority order from a label that only contains a band."""
    board, _ = build(FakeGitHub([issue(1, labels=(label,))], []))
    assert board["next"]["items"] == []
    assert card(board, 1)["labels"] == [label]


def test_after_names_neither_the_card_itself_nor_a_bare_number() -> None:
    """Protects a card from sorting below itself, or below a stray digit."""
    gh = FakeGitHub([issue(1), issue(2), issue(5, body="Board after: #5, 1, #2\n")], [])
    board, _ = build(gh)
    assert card(board, 5)["after"] == [2]


def test_the_job_summary_lists_what_disagrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the one place a conflict is reported, since it does not fail the run."""
    fake = FakeGitHub([issue(1, labels=("band:1", "band:3"))], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    assert bb.main(["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]) == 0
    assert (
        "| Labels or lines that disagree | #1 carries 2 band labels, read as band:1 |"
        in summary.read_text()
    )


def test_after_comes_from_its_line_and_keeps_open_issues() -> None:
    """Protects a measured ordering from prose that only mentions a number."""
    body = "Waits on nothing.\n\nBoard after: #1, #3 and #2\nSee #4 too.\n"
    gh = FakeGitHub([issue(1), issue(2), issue(5, body=body)], [])
    board, _ = build(gh)
    assert card(board, 5)["after"] == [1, 2]
    assert "after" not in card(board, 1)


def test_a_band_label_puts_the_card_in_the_priority_order() -> None:
    """Protects the default view, which draws only the cards ``next`` names.

    The order line takes a decimal, so a card can go between two others
    without renumbering either, and an order written as a whole number stays
    one.
    """
    gh = FakeGitHub(
        [
            issue(1, labels=("band:3",), body="Board order: 14.05\n"),
            issue(2, labels=("band:1",), body="Board order: 22\n"),
            issue(3, labels=("band:5",)),
            issue(4),
        ],
        [],
    )
    board, _ = build(gh)
    assert board["next"]["items"] == [
        {"issue": 1, "band": 3, "ready": "plan", "order": 14.05},
        {"issue": 2, "band": 1, "ready": "plan", "order": 22},
        {"issue": 3, "band": 5, "ready": "plan"},
    ]
    assert '"order":22}' in json.dumps(board["next"], separators=(",", ":"))


def test_the_boards_own_labels_are_left_off_the_cards_chips() -> None:
    """Protects a card from drawing its rank and its session twice."""
    labels = ("enhancement", "band:1", "working:build", "decision")
    board, _ = build(FakeGitHub([issue(1, labels=labels)], []))
    assert card(board, 1)["labels"] == ["enhancement", "decision"]


@pytest.mark.parametrize(
    ("labels", "comments", "ready"),
    [
        (("band:1",), (), "plan"),
        (("band:1", "decision"), (), "decide"),
        (("band:1",), (("OWNER", "## Verdict\n\nBoard verdict: build after 5 passes\n"),), "build"),
        (("band:1", "decision"), (("OWNER", "Board verdict: build after 1 pass"),), "build"),
        (("band:1",), (("OWNER", "Board verdict: decide after 3 passes."),), "decide"),
        (("band:1",), (("NONE", "Board verdict: build after 5 passes"),), "plan"),
    ],
)
def test_a_ranked_cards_readiness_comes_from_its_verdict_then_its_kind(
    labels: tuple[str, ...], comments: tuple[tuple[str, str], ...], ready: str
) -> None:
    """Protects the sort, which reads ``ready`` after the band and the order."""
    board, _ = build(FakeGitHub([issue(1, labels=labels, comments=comments)], []))
    assert board["next"]["items"][0]["ready"] == ready


@pytest.mark.parametrize(
    ("comments", "planned"),
    [
        (
            (("OWNER", "## Decompose verdict\n\nBoard verdict: build after 5 passes\n"),),
            (5, "build"),
        ),
        (
            (
                ("OWNER", "Board verdict: build after 5 passes"),
                ("OWNER", "Board verdict: decide after 7 passes"),
            ),
            (7, "decide"),
        ),
        ((("CONTRIBUTOR", "Board verdict: build after 5 passes"),), None),
        ((("COLLABORATOR", "Board verdict: build after 5 passes"),), None),
        ((("MEMBER", "Board verdict: build after 5 passes"),), None),
        ((("OWNER", "The line `Board verdict: build after 5 passes` goes here."),), None),
        ((("OWNER", "Board verdict: ready after 5 passes"),), None),
    ],
)
def test_only_the_owners_newest_verdict_line_plans_a_card(
    comments: tuple[tuple[str, str], ...], planned: tuple[int, str] | None
) -> None:
    """Protects the plan marker from a stranger's comment and from prose.

    Anyone can comment on a public repository. A loop run again writes a new
    verdict, so the newest wins, and a line quoted inside a sentence is not one.
    """
    board, _ = build(FakeGitHub([issue(1, comments=comments)], []))
    items = board["planned"]["items"]
    if planned is None:
        assert items == []
    else:
        assert items == [{"n": 1, "passes": planned[0], "ready": planned[1]}]


def test_a_working_label_marks_the_session_on_the_card() -> None:
    """Protects the columns a session holds a card in, and the review word.

    A build session's open branch reads "review in progress" until its review
    is posted, and a branch nobody holds reads
    "no review posted".
    """
    gh = FakeGitHub(
        [
            issue(1, labels=("working:build",)),
            issue(2, labels=("working:decompose",)),
            issue(3),
        ],
        [pull(10, closes=(1,)), pull(11, closes=(3,))],
    )
    board, _ = build(gh)
    assert board["working"]["items"] == [{"n": 1, "kind": "build"}, {"n": 2, "kind": "decompose"}]
    assert {p["pr"]: p["review"] for p in prs_of(board)} == {
        10: "review in progress",
        11: "no review posted",
    }


def test_labels_that_disagree_take_one_value_and_are_reported() -> None:
    """Protects the board from freezing on one stray label.

    Two bands take the lower, both session labels take ``build`` in either
    order, and two order lines take the first, and the job summary lists each.
    """
    gh = FakeGitHub(
        [
            issue(
                1,
                labels=("band:3", "band:1", "working:decompose", "working:build"),
                body="Board order: 4\nBoard order: 9\n",
            )
        ],
        [],
    )
    board, report = build(gh)
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert board["working"]["items"] == [{"n": 1, "kind": "build"}]
    swapped = FakeGitHub([issue(1, labels=("working:build", "working:decompose"))], [])
    assert build(swapped)[0]["working"]["items"] == [{"n": 1, "kind": "build"}]
    assert report["label_conflicts"] == [
        "#1 carries both working labels, read as build",
        "#1 carries 2 band labels, read as band:1",
        "#1 carries 2 order lines, read as 4",
    ]


# ---- Markers the board does not use ----


def summary_of(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeGitHub, *args: str
) -> str:
    """The job summary a run writes, read through ``main`` as the workflow runs it."""
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out), *args]
    assert bb.main(argv) == 0
    return summary.read_text()


def summary_row(text: str, name: str) -> str:
    """The value of the summary row ``name``."""
    rows = [line for line in text.splitlines() if line.startswith(f"| {name} | ")]
    assert len(rows) == 1, name
    return rows[0].removeprefix(f"| {name} | ").removesuffix(" |")


PASS = "## Plan audit, pass 1\n\nFound nothing.\n"
VERDICT_LINE = "Board verdict: build after 2 passes"
# More lines than the pass heading has characters, so an offset that dropped
# each line's newline would put a verdict right after the heading above it.
PREAMBLE = "Note.\n" * 30


def test_the_issues_query_reads_each_issues_author() -> None:
    """Protects the unread row from going quiet on every real run.

    ``FakeGitHub`` answers from fixtures whatever a query selects, so only the
    query's own text shows that a run reads who wrote each issue. Without it
    every body reads as a stranger's, and no near miss in one is ever listed.
    """
    node = re.search(r"nodes \{\n\s*(id [^\n]*)\n", bb.ISSUES_QUERY)
    assert node, "the issues query's node selection moved"
    assert "authorAssociation" in node.group(1).split()


def test_the_issues_query_reads_both_sub_issue_counts() -> None:
    """Protects the parent rule from a field the live read never asked for.

    Under ``ranking=order``, ``tracker_card`` reads ``total`` and
    ``completed`` from every issue's ``subIssuesSummary``, and otherwise
    ``totalCount`` from its ``subIssues``. ``FakeGitHub`` answers from
    fixtures whatever a query selects, so a query that dropped a field would
    pass every other test here and stop the live run on a missing key.
    """
    summary = re.search(r"subIssuesSummary\{([^}]*)\}", bb.issues_query(True))
    assert summary, "the order query reads no subIssuesSummary"
    assert sorted(summary.group(1).split()) == ["completed", "total"]
    assert "subIssues{totalCount}" not in bb.issues_query(True)
    assert "subIssues{totalCount}" in bb.ISSUES_QUERY
    assert "subIssuesSummary" not in bb.ISSUES_QUERY


@pytest.mark.parametrize(("ranking", "field"), [("", "subIssues{"), ("order", "subIssuesSummary{")])
def test_the_ranking_chooses_the_sub_issue_field_the_live_read_asks_for(
    ranking: str, field: str
) -> None:
    """Protects each rule from a query that asks for the other rule's field.

    ``FakeGitHub`` hands every issue both fields, so only the query text
    shows which one a run asked GitHub for. A run that read the wrong one
    would stop on a missing key against the live API.
    """
    gh = FakeGitHub([issue(1, sub_issues=(2, 1))], [])
    bb.build(gh, REPO, 30, NOW, ranking=ranking)
    issues_queries = [q for q in gh.calls if "issues(states:OPEN" in q]
    assert issues_queries
    assert all(field in q for q in issues_queries)
    other = "subIssuesSummary{" if field == "subIssues{" else "subIssues{"
    assert not any(other in q for q in issues_queries)


@pytest.mark.parametrize(
    ("near_miss", "kind"),
    [
        ("Board order: first", "Board order"),
        ("Board order 3", "Board order"),
        ("**Board order**: 3", "Board order"),
        ("- Board Order: 3", "Board order"),
        ("Board order: 1234567890123456", "Board order"),
        ("Board after: soon", "Board after"),
        ("Board after: 3", "Board after"),
        ("Board after", "Board after"),
        ("Board verdict: build after 3 passes", "Board verdict"),
        ("Board after #2", "Board after"),
        ("> Board order: 3", "Board order"),
        ("1. Board order: 3", "Board order"),
        ("1) Board order: 3", "Board order"),
        ("+ Board order: 3", "Board order"),
        ("Board  order: 3", "Board order"),
        ("10. Board order: first", "Board order"),
        ("Board order #3", "Board order"),
        ("**Board after**", "Board after"),
        ("Board after   ", "Board after"),
        ("Board after: #2x", "Board after"),
        ("Board verd\u0130ct: build after 3 passes", "Board verdict"),
        ("Board verd\u0131ct: build after 3 passes", "Board verdict"),
    ],
)
def test_a_near_miss_in_the_owners_body_is_listed_as_unread(near_miss: str, kind: str) -> None:
    """Protects a mistyped body marker from vanishing with nothing said.

    A verdict counts only in a comment, so a verdict line in a body is unread
    too. The well-formed line beside the near miss still reaches the board.
    """
    body = f"{near_miss}\nBoard order: 2\nBoard after: #2\n"
    gh = FakeGitHub([issue(1, labels=("band:1",), body=body), issue(2)], [])
    board, report = build(gh)
    assert report["unread"] == [(1, kind)]
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 2}]
    assert card(board, 1)["after"] == [2]


@pytest.mark.parametrize(
    "body",
    [
        "Board orders form one sequence.\nBoard after the merge, rebase.\n",
        "See Board order: 3 in the skill.\n",
        "```\nBoard order: first\nBoard verdict: build after 3 passes\n```\n",
        "Board order: 2\nBoard after: #2\n",
    ],
)
def test_prose_fences_and_markers_read_are_not_listed_as_unread(body: str) -> None:
    """Protects the summary from listing prose about the markers on every run."""
    gh = FakeGitHub([issue(1, labels=("band:1",), body=body), issue(2)], [])
    _, report = build(gh)
    assert report["unread"] == []


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "COLLABORATOR", "MEMBER"])
def test_a_strangers_body_is_read_as_before_and_its_near_misses_are_not_listed(
    association: str,
) -> None:
    """Protects the summary from a stranger filling it, and the board from changing.

    Anyone can open an issue on a public repository. Its order and after lines
    still count, as they did before the summary listed anything.
    """
    body = "Board order: first\nBoard order: 4\nBoard after: soon\nBoard after: #2\n"
    gh = FakeGitHub(
        [issue(1, labels=("band:1",), body=body, association=association), issue(2)], []
    )
    board, report = build(gh)
    assert report["unread"] == []
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert card(board, 1)["after"] == [2]


def test_every_after_line_in_a_body_counts() -> None:
    """Protects the second of two after lines from being read over by the first."""
    gh = FakeGitHub([issue(1, body="Board after: #2\nBoard after: #3\n"), issue(2), issue(3)], [])
    board, _ = build(gh)
    assert card(board, 1)["after"] == [2, 3]


def test_an_unbanded_cards_near_miss_is_listed_as_unread() -> None:
    """Protects a near miss on a card the priority order does not draw."""
    _, report = build(FakeGitHub([issue(1, body="Board order: first\n")], []))
    assert report["unread"] == [(1, "Board order")]


@pytest.mark.parametrize(
    ("comment", "kinds"),
    [
        ("Board order: 3", ["Board order"]),
        ("Board after: #2", ["Board after"]),
        ("Board verdict: ready after 5 passes", ["Board verdict"]),
        ("**Board verdict**: build after 5 passes", ["Board verdict"]),
        ("Board verdict: build after 1234567890123456 passes", ["Board verdict"]),
        ("Board verdict: decide after", ["Board verdict"]),
        ("Board verd\u0130ct: build after 5 passes", ["Board verdict"]),
        ("Board verd\u0131ct: build after 5 passes", ["Board verdict"]),
        ("The line `Board verdict: build after 5 passes` goes here.", []),
        ("```\nBoard verdict: ready after 5 passes\n```", []),
    ],
)
def test_a_near_miss_in_an_owners_comment_is_listed_as_unread(
    comment: str, kinds: list[str]
) -> None:
    """Protects a mistyped verdict from vanishing with nothing said.

    An order or after line counts only in a body, so one in a comment is
    unread too. The well-formed verdict beside the near miss still plans the
    card.
    """
    comments = (("OWNER", f"{comment}\n{VERDICT_LINE}\n"),)
    board, report = build(FakeGitHub([issue(1, comments=comments), issue(2)], []))
    assert report["unread"] == [(1, kind) for kind in kinds]
    assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]


def test_a_strangers_near_miss_in_a_comment_is_not_listed() -> None:
    """Protects the summary from a stranger filling it."""
    comments = (("NONE", "Board order: 3\nBoard verdict: ready after 5 passes\n"),)
    _, report = build(FakeGitHub([issue(1, comments=comments)], []))
    assert report["unread"] == []
    assert report["refused"] == []


def test_refused_verdicts_come_out_in_issue_order() -> None:
    """Protects the refused row from listing issues in the order a set holds them.

    Twelve issues are enough for a set's order to differ from the sorted one.
    """
    issues = [issue(n, comments=(("NONE", VERDICT_LINE),)) for n in range(1, 13)]
    _, report = build(FakeGitHub(issues, []))
    assert report["refused"] == [(n, "Board verdict, not the owner's") for n in range(1, 13)]


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "COLLABORATOR", "MEMBER"])
def test_a_strangers_verdict_is_listed_as_refused(association: str) -> None:
    """Protects a verdict the board refuses from vanishing with nothing said.

    The verdict still plans nothing, because anyone can comment on a public
    repository.
    """
    comments = ((association, VERDICT_LINE),)
    board, report = build(FakeGitHub([issue(1, comments=comments)], []))
    assert report["refused"] == [(1, "Board verdict, not the owner's")]
    assert report["unread"] == []
    assert board["planned"]["items"] == []


@pytest.mark.parametrize(
    "comment",
    [
        ("OWNER", VERDICT_LINE),
        ("NONE", f"```\n{VERDICT_LINE}\n```"),
        ("NONE", f"Quoting `{VERDICT_LINE}` here."),
    ],
)
def test_an_owners_verdict_or_a_quoted_one_is_not_refused(comment: tuple[str, str]) -> None:
    """Protects the refused row from listing what was never a stranger's verdict."""
    _, report = build(FakeGitHub([issue(1, comments=(comment,))], []))
    assert report["refused"] == []


@pytest.mark.parametrize(
    "comments",
    [
        (("OWNER", PASS),),
        (("OWNER", VERDICT_LINE), ("OWNER", PASS)),
        (("OWNER", f"{VERDICT_LINE}\n\n{PASS}"),),
        (("OWNER", PASS), ("OWNER", "## Plan audit, pass 2\n"), ("NONE", VERDICT_LINE)),
        (("OWNER", f"{VERDICT_LINE}\n{PASS}"),),
        (("OWNER", f"{PASS}\n{VERDICT_LINE}\n## Plan audit, pass 2\n"),),
        (("OWNER", VERDICT_LINE), ("OWNER", "   ## Plan audit, pass 1\n")),
    ],
)
def test_a_pass_after_the_newest_verdict_is_a_plan_with_no_verdict(
    comments: tuple[tuple[str, str], ...],
) -> None:
    """Protects a finished decompose loop that never wrote its verdict.

    Its card waits for a builder that the board never sends, and the owner
    learns of it only from this row.
    """
    _, report = build(FakeGitHub([issue(1, comments=comments)], []))
    assert report["no_verdict"] == [1]


@pytest.mark.parametrize(
    "comments",
    [
        (),
        (("OWNER", f"{PASS}\n{VERDICT_LINE}\n"),),
        (("OWNER", f"{PREAMBLE}{PASS.splitlines()[0]}\n{VERDICT_LINE}\n"),),
        (("OWNER", PASS), ("OWNER", VERDICT_LINE)),
        (("NONE", PASS),),
        (("OWNER", f"```\n{PASS}```\n"),),
        (("OWNER", f"The heading `{PASS.splitlines()[0]}` opens a pass."),),
        (("OWNER", "## Plan audit, pass N\n"),),
    ],
)
def test_a_verdict_after_the_newest_pass_or_no_pass_is_not_listed(
    comments: tuple[tuple[str, str], ...],
) -> None:
    """Protects the row from listing a plan that finished properly.

    An exit comment headed as the last pass and ending with the verdict is the
    usual shape, and the verdict comes after the heading in it.
    """
    _, report = build(FakeGitHub([issue(1, comments=comments)], []))
    assert report["no_verdict"] == []


def test_a_card_that_owes_no_verdict_is_not_listed() -> None:
    """Protects the row from cards whose missing verdict is no work for the owner.

    A parent builds nothing, a deferred card is one nobody should take, a
    decompose loop still holds its card, and an open pull request is carrying
    the plan out, whether it closes the issue or names it with ``Part of``. A
    data label takes the kind ahead of ``deferred``, so the
    label is what is tested. A merged pull request carries nothing out.
    """
    comments = (("OWNER", PASS),)
    gh = FakeGitHub(
        [
            issue(1, comments=comments, sub_issues=1),
            issue(2, comments=comments, labels=("deferred",)),
            issue(3, comments=comments, labels=("deferred", DATA_LABEL)),
            issue(4, comments=comments, labels=("working:decompose",)),
            issue(5, comments=comments),
            issue(6, comments=comments, mentioned_by=(21,)),
            issue(7, comments=comments, labels=("working:build",)),
            issue(8, comments=comments),
        ],
        [
            pull(20, closes=(5,)),
            pull(21, state="MERGED", body="Part of #6"),
            pull(22, body="Part of #8"),
        ],
    )
    board, report = build(gh, DATA_LABEL)
    assert card(board, 3)["kind"] == "data"
    assert report["no_verdict"] == [6, 7]


def test_equal_order_lines_are_a_conflict() -> None:
    """Protects a leftover order line, whose edit would move nothing, from going unseen."""
    gh = FakeGitHub([issue(1, labels=("band:1",), body="Board order: 4\nBoard order: 4\n")], [])
    board, report = build(gh)
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert report["label_conflicts"] == ["#1 carries 2 order lines, read as 4"]
    single = FakeGitHub([issue(1, labels=("band:1",), body="Board order: 4\n")], [])
    assert build(single)[1]["label_conflicts"] == []


# Rows of the job summary at l3a0/repo-template commit cf2959a3, before the
# four marker rows. The l3a0 plugin's sync-prune-next skill reads the four new
# rows by name, so a change to a name or to the order fails here.
SUMMARY_ROWS_BEFORE = [
    "GitHub read at",
    "GraphQL requests",
    "GraphQL requests tried again after a server or connection error",
    "GraphQL points",
    "Open issues",
    "Open pull requests",
    "Merged or closed pull requests read",
    "Pull request items written",
    "Open pull requests naming no open issue",
    "Check states mapped to neither way",
    "Labels or lines that disagree",
    "Data label",
]
MARKER_ROWS = [
    "Marker lines not read",
    "Marker lines refused",
    "Markers dropped",
    "Finished plans with no verdict after them",
]
# The row the review-heading input added after every row above. It is written
# whether or not a caller names a heading, as the data label's row is.
REVIEW_ROWS = ["Review heading"]


def test_the_job_summary_adds_the_four_marker_rows_after_the_disagreements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the rows a status round reads by name, and every row before them."""
    text = summary_of(monkeypatch, tmp_path, FakeGitHub([issue(1)], []))
    rows = [line.split(" | ")[0].removeprefix("| ") for line in text.splitlines()[4:]]
    at = SUMMARY_ROWS_BEFORE.index("Labels or lines that disagree") + 1
    assert rows == (SUMMARY_ROWS_BEFORE[:at] + MARKER_ROWS + SUMMARY_ROWS_BEFORE[at:] + REVIEW_ROWS)
    for name in MARKER_ROWS:
        assert summary_row(text, name) == "none"


def test_the_job_summary_lists_each_marker_it_did_not_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the one place a mistyped or misplaced marker surfaces."""
    gh = FakeGitHub(
        [
            issue(2, body="Board after: soon\n"),
            issue(1, body="Board order: first\n", comments=(("NONE", VERDICT_LINE),)),
            issue(3, comments=(("OWNER", PASS),)),
            issue(4, comments=(("OWNER", PASS),)),
        ],
        [],
    )
    text = summary_of(monkeypatch, tmp_path, gh)
    assert summary_row(text, "Marker lines not read") == "#1 Board order; #2 Board after"
    assert summary_row(text, "Marker lines refused") == "#1 Board verdict, not the owner's"
    assert summary_row(text, "Markers dropped") == "none"
    assert summary_row(text, "Finished plans with no verdict after them") == "#3, #4"


def test_the_job_summary_lists_a_dropped_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the dropped row from printing nothing when a marker goes unused."""
    gh = FakeGitHub([issue(2, body="Board after: #2\n"), issue(1, body="Board order: 3\n")], [])
    text = summary_of(monkeypatch, tmp_path, gh)
    assert summary_row(text, "Markers dropped") == (
        "#1 Board order on a card with no band; #2 Board after, naming itself"
    )


def test_the_job_summary_lists_the_drops_ranking_by_order_makes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the drops ``--ranking=order`` makes from vanishing unseen.

    The pull request that closes l3a0/repo-template#46 added the three
    phrases, each listed under its issue in number order. #4's order has no
    band and ranks the card, because under ``order`` the line alone does, so
    it is not listed as an order on a card with no band.
    """
    gh = FakeGitHub(
        [
            issue(2, sub_issues=1, comments=(("OWNER", VERDICT_LINE),)),
            issue(1, sub_issues=1, body="Board order: 1\n"),
            issue(3, labels=("deferred",), comments=(("OWNER", VERDICT_LINE),)),
            issue(4, body="Board order: 2\n"),
        ],
        [],
    )
    text = summary_of(monkeypatch, tmp_path, gh, "--ranking=order")
    assert summary_row(text, "Markers dropped") == (
        "#1 Board order on a parent; #2 Board verdict on a parent; "
        "#3 Board verdict on a deferred card"
    )


def test_an_order_on_a_card_with_no_band_is_listed_as_dropped() -> None:
    """Protects a well-formed order that ranks nothing from vanishing unseen.

    Only a banded card has a place in the priority order, so the order line on
    an unbanded card sets nothing. A banded card's order is not listed.
    """
    gh = FakeGitHub(
        [issue(1, body="Board order: 3\n"), issue(2, labels=("band:1",), body="Board order: 3\n")],
        [],
    )
    board, report = build(gh)
    assert report["dropped"] == [(1, "Board order on a card with no band")]
    assert board["next"]["items"] == [{"issue": 2, "band": 1, "ready": "plan", "order": 3}]
    assert build(FakeGitHub([issue(1)], []))[1]["dropped"] == []


@pytest.mark.parametrize(
    ("body", "dropped"),
    [
        ("Board after: #5\n", True),
        ("Board after: #5 and #5\n", True),
        ("Board after: #5, #2\n", False),
        ("Board after: #2\n", False),
        ("Board after: #7\n", False),
        ("Board after: octo-org/octo-repo#5\n", True),
        ("Board after: other/repo#3 #5\n", False),
    ],
)
def test_an_after_line_naming_only_its_own_card_is_listed_as_dropped(
    body: str, dropped: bool
) -> None:
    """Protects an after line that can never hold its card from vanishing unseen.

    A line naming another issue too still sets something, and a line naming a
    closed issue is a blocker that has finished, so neither is listed. A line
    whose other reference was refused is listed as refused rather than
    dropped, because it named something besides the card.
    """
    board, report = build(FakeGitHub([issue(2), issue(5, body=body)], []))
    assert report["dropped"] == ([(5, "Board after, naming itself")] if dropped else [])
    assert card(board, 5).get("after", []) == ([2] if "#2" in body else [])


def marker_tracker() -> FakeGitHub:
    """A tracker holding every marker shape the summary rows read, at once."""
    passed = (("OWNER", PASS),)
    return FakeGitHub(
        [
            issue(
                1,
                labels=("band:1",),
                body="Board order: first\nBoard order: 2\nBoard after: soon\nBoard after: #2\n"
                "Board verdict: build after 3 passes\n",
            ),
            issue(2, labels=("band:2",), body="Board order: 5\r\nBoard after: #1\r\n"),
            issue(
                3,
                labels=("band:1",),
                body="Board order: 7\nBoard order: seven\nBoard after: #1\n",
                association="NONE",
            ),
            issue(4, comments=(("NONE", VERDICT_LINE), ("OWNER", PASS))),
            issue(5, labels=("band:1",), comments=(("OWNER", f"{PASS}\n{VERDICT_LINE}\n"),)),
            issue(6, labels=("band:1",), body="Board order: 4\nBoard order: 4\n"),
            issue(7, comments=(("OWNER", "Board order: 3\n**Board verdict**: build after 2\n"),)),
            issue(
                8,
                body="```\nBoard order: x\n```\n",
                comments=(("OWNER", f"```\n{PASS}```\n"),),
            ),
            issue(9, comments=passed, sub_issues=1),
            issue(10, comments=passed, labels=("deferred",)),
            issue(11, comments=passed, labels=("working:decompose",)),
            issue(12, comments=passed),
            issue(13, comments=passed, mentioned_by=(31,)),
            issue(14, comments=(("OWNER", VERDICT_LINE), ("OWNER", PASS))),
            issue(15, comments=passed, labels=("deferred", DATA_LABEL)),
            issue(16, labels=("band:2",), body="Board order: 8\nBoard order: 1\n"),
            issue(17, body="Board order: 3\nBoard after: #17\n"),
        ],
        [pull(30, closes=(12,)), pull(31, state="MERGED", body="Part of #13")],
    )


def test_every_marker_shape_reaches_its_row() -> None:
    """Protects the four rows on a tracker holding all their cases at once."""
    _, report = build(marker_tracker(), DATA_LABEL)
    assert report["unread"] == [
        (1, "Board after"),
        (1, "Board order"),
        (1, "Board verdict"),
        (7, "Board order"),
        (7, "Board verdict"),
    ]
    assert report["refused"] == [(4, "Board verdict, not the owner's")]
    assert report["dropped"] == [
        (17, "Board after, naming itself"),
        (17, "Board order on a card with no band"),
    ]
    assert report["no_verdict"] == [4, 13, 14]
    assert "#6 carries 2 order lines, read as 4" in report["label_conflicts"]


MARKERS_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "markers.json"


class FrozenNow(datetime):
    """A ``datetime`` whose ``now`` is ``NOW``, so a run's board carries a fixed time."""

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return NOW


def test_the_marker_rows_change_nothing_in_the_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects every caller that sets no input from a board that moves.

    The rows list what the board did not use, so the board itself has to stay
    as it was. ``MARKERS_GOLDEN`` is the ``board.json`` that the command line at
    l3a0/repo-template commit cf2959a3 wrote for ``marker_tracker``, and this
    run has to write the same bytes but one. The file is read as the command
    line writes it, so a change to how it is written fails here too. #2's body
    ends its lines with ``\\r\\n``, so cf2959a3 lost its order line, and
    since l3a0/repo-template#48 the generator reads it. No current caller's
    data carries a ``\\r``.
    """
    monkeypatch.setattr(bb, "datetime", FrozenNow)
    summary_of(monkeypatch, tmp_path, marker_tracker(), "--data-label", DATA_LABEL)
    written = (tmp_path / "site" / "board.json").read_bytes()
    golden = MARKERS_GOLDEN.read_bytes().removesuffix(b"\n")
    lost = b'{"issue":2,"band":2,"ready":"plan"}'
    assert golden.count(lost) == 1
    assert written == golden.replace(lost, b'{"issue":2,"band":2,"ready":"plan","order":5}')


def compat_tracker() -> FakeGitHub:
    """A tracker holding the order lines, after lines, references and blockers
    that l3a0/repo-template#48 reads differently, each in a form both readers
    read alike.

    Strangers' issues carry lines, an after line names this repository by
    name, a blocker and a closing link name it in GitHub's spelling, and every
    number is short.
    """
    return FakeGitHub(
        [
            issue(
                1,
                labels=("band:1",),
                body="Board order: 3\nBoard after: #2, octo-org/octo-repo#4 and #99\n",
            ),
            issue(
                2,
                labels=("band:2",),
                body="Board order: 2.5\nBoard after: #1\n",
                association="NONE",
            ),
            issue(
                3,
                labels=("band:1",),
                body="Board order: -1\n",
                association="CONTRIBUTOR",
                comments=(("OWNER", "Board verdict: build after 4 passes"),),
                mentioned_by=(22,),
            ),
            issue(
                4,
                blocked_by=((2, "OPEN"), (7, "OPEN", "other/repo"), (1, "CLOSED")),
                comments=(("NONE", VERDICT_LINE),),
            ),
            issue(5, body="Board after: #4\n", association="MEMBER", closed_by=(21,)),
        ],
        [
            pull(20, body="Part of #4"),
            pull(21, closes=(5,)),
            pull(22, state="MERGED", body="Part of #3"),
        ],
    )


COMPAT = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "compat.json"


def test_a_caller_that_sets_no_input_gets_the_board_it_got_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects every caller that sets no input from a board that moves.

    ``COMPAT`` is the ``board.json`` that the generator at l3a0/repo-template
    commit cf2959a3 wrote for ``compat_tracker``, and this run has to write the
    same bytes. The file is read as the command line writes it, so a change to
    how it is written fails here too. A stranger's lines still count, and a
    reference to this repository by name still reads, until a caller sets
    ``owner-body-lines``.
    """
    monkeypatch.setattr(bb, "datetime", FrozenNow)
    summary_of(monkeypatch, tmp_path, compat_tracker())
    written = (tmp_path / "site" / "board.json").read_bytes()
    assert written == COMPAT.read_bytes().removesuffix(b"\n")


# ---- Marker lines from strangers, other repositories and long numbers ----

# Two open issues numbered with 15 digits and with 16, so a reference to either
# can only reach the board by being read.
FIFTEEN = 123456789012345
SIXTEEN = 1234567890123456
# More digits than Python 3.12 turns into an ``int``, which raises
# ``ValueError`` past 4,300.
HUGE = "9" * 4301


@pytest.mark.parametrize(
    ("order", "read"),
    [
        (str(FIFTEEN), FIFTEEN),
        ("1234567890.12345", 1234567890.12345),
        (str(SIXTEEN), None),
        ("1234567890.123456", None),
        ("9" * 400, None),
    ],
)
def test_an_order_longer_than_fifteen_digits_is_not_read(order: str, read: object) -> None:
    """Protects the page from an order it cannot draw.

    JavaScript reads every number as a double, which holds 15 digits exactly.
    A 400-digit order is infinity, which ``board.json`` cannot carry. An order
    that is not read is listed as unread in the owner's body.
    """
    gh = FakeGitHub([issue(1, labels=("band:1",), body=f"Board order: {order}\n")], [])
    board, report = build(gh)
    [entry] = board["next"]["items"]
    if read is None:
        assert "order" not in entry
        assert report["unread"] == [(1, "Board order")]
    else:
        assert entry["order"] == read
        assert report["unread"] == []
    json.dumps(board, allow_nan=False)


# Each form a `Board after:` line can name an issue in, with `{n}` for its number.
AFTER_FORMS = [
    "#{n}",
    "octo-org/octo-repo#{n}",
    "[#{n}](https://github.com/octo-org/octo-repo/issues/{n})",
]


@pytest.mark.parametrize("form", AFTER_FORMS)
@pytest.mark.parametrize(("number", "read"), [(FIFTEEN, True), (SIXTEEN, False)])
def test_an_after_reference_longer_than_fifteen_digits_is_no_reference(
    number: int, read: bool, form: str
) -> None:
    """Protects the read of a stranger's line from a number ``int()`` refuses.

    Every form a reference takes has the limit, because each one is turned
    into an ``int``.
    """
    line = form.format(n=number)
    gh = FakeGitHub([issue(1, body=f"Board after: {line}\n"), issue(number)], [])
    board, report = build(gh)
    assert card(board, 1).get("after") == ([number] if read else None)
    assert report["unread"] == ([] if read else [(1, "Board after")])


@pytest.mark.parametrize(("number", "read"), [(FIFTEEN, True), (SIXTEEN, False)])
def test_a_pass_count_longer_than_fifteen_digits_leaves_the_last_verdict(
    number: int, read: bool
) -> None:
    """Protects a planned card from a verdict whose count ``int()`` refuses."""
    comments = (
        ("OWNER", VERDICT_LINE),
        ("OWNER", f"Board verdict: decide after {number} passes"),
    )
    board, report = build(FakeGitHub([issue(1, comments=comments)], []))
    if read:
        assert board["planned"]["items"] == [{"n": 1, "passes": number, "ready": "decide"}]
        assert report["unread"] == []
    else:
        assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]
        assert report["unread"] == [(1, "Board verdict")]


@pytest.mark.parametrize(("number", "read"), [(FIFTEEN, True), (SIXTEEN, False)])
def test_a_part_of_reference_longer_than_fifteen_digits_is_no_reference(
    number: int, read: bool
) -> None:
    """Protects the run from a branch whose ``Part of`` number ``int()`` refuses."""
    gh = FakeGitHub([issue(number)], [pull(20, body=f"Part of #{number}")])
    items = prs_of(build(gh)[0])
    assert [p["issue"] for p in items] == ([number] if read else [])


def test_a_number_too_long_for_int_still_builds_the_board() -> None:
    """Protects every board run from one stranger's issue.

    Before the limit, a ``Board after:`` line carrying more than 4,300 digits
    made ``int()`` raise, and every run failed until someone edited the issue.
    A pass count and a ``Part of`` number reached the same error, and a long
    order reached ``Infinity``.
    """
    gh = FakeGitHub(
        [
            issue(
                1,
                body="".join(f"Board after: {form.format(n=HUGE)}\n" for form in AFTER_FORMS),
                association="NONE",
            ),
            issue(2, labels=("band:1",), body=f"Board order: {HUGE}\n"),
            issue(3, comments=(("OWNER", f"Board verdict: build after {HUGE} passes"),)),
        ],
        [pull(20, body=f"Part of #{HUGE}")],
    )
    board, report = build(gh)
    assert "after" not in card(board, 1)
    assert board["next"]["items"] == [{"issue": 2, "band": 1, "ready": "plan"}]
    assert board["planned"]["items"] == []
    assert prs_of(board) == []
    assert report["unread"] == [(2, "Board order"), (3, "Board verdict")]
    json.dumps(board, allow_nan=False)


def test_a_board_json_cannot_carry_fails_the_run_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the page from a ``board.json`` that ``JSON.parse`` refuses.

    Python writes infinity as ``Infinity``, which is not JSON, so the page
    would draw nothing. The run stops instead, keeps the last good board up,
    and says why where the run's page shows it rather than as a traceback.
    """
    real = bb.build

    def build_with_infinity(*args: object, **kwargs: object) -> tuple[dict, dict]:
        board, report = real(*args, **kwargs)
        board["next"]["items"] = [{"issue": 1, "band": 1, "ready": "plan", "order": float("inf")}]
        return board, report

    fake = FakeGitHub([issue(1)], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.setattr(bb, "build", build_with_infinity)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]
    assert bb.main(argv) == 1
    assert not (out / "board.json").exists()
    text = summary.read_text()
    assert "## Board run failed" in text
    assert "build_board: board.json would carry a number JSON cannot hold" in text


@pytest.mark.parametrize(
    "body",
    [
        "```\r\ncode\r\n```\r\nBoard order: 3\r\nBoard after: #2\r\n",
        "```\rcode\r```\rBoard order: 3\rBoard after: #2\r",
        "```\ncode\n```\nBoard order: 3\nBoard after: #2\n",
    ],
    ids=["crlf", "cr", "lf"],
)
def test_a_body_is_read_through_any_line_ending(body: str) -> None:
    """Protects an order the owner edited in a browser from being lost.

    GitHub's web editor saves ``\\r\\n``. Read with the ``\\r`` on it, an order
    line failed its pattern with nothing said, and the fence's closing line
    never matched, so the fence removed every marker after it.
    """
    gh = FakeGitHub([issue(1, labels=("band:1",), body=body), issue(2)], [])
    board, report = build(gh)
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 3}]
    assert card(board, 1)["after"] == [2]
    assert report["unread"] == []


@pytest.mark.parametrize("end", ["\r\n", "\r", "\n"], ids=["crlf", "cr", "lf"])
def test_a_comment_is_read_through_any_line_ending(end: str) -> None:
    """Protects a verdict the owner posted from a browser from being lost."""
    text = end.join(["## Plan audit, pass 3", "", "```", "x", "```", VERDICT_LINE, ""])
    board, report = build(FakeGitHub([issue(1, comments=(("OWNER", text),))], []))
    assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]
    assert report["unread"] == []
    assert report["no_verdict"] == []


def test_a_fence_in_a_crlf_body_still_hides_what_it_quotes() -> None:
    """Protects the fence rule once the fence closes, so it still quotes."""
    body = "```\r\nBoard order: 9\r\n```\r\nBoard order: 3\r\n"
    board, _ = build(FakeGitHub([issue(1, labels=("band:1",), body=body)], []))
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 3}]


@pytest.mark.parametrize("run_repo", [REPO, "Octo-Org/Octo-Repo"])
@pytest.mark.parametrize(
    "spelling", ["octo-org/octo-repo", "Octo-Org/Octo-Repo", "OCTO-ORG/OCTO-REPO"]
)
def test_a_repository_is_the_same_whatever_its_case(spelling: str, run_repo: str) -> None:
    """Protects a reference typed in another case from reading as another repository.

    GitHub treats an owner and a repository named in any case as the same one,
    so the run's own name is folded too, not only the name each reference
    carries.
    """
    gh = FakeGitHub(
        [
            issue(1, blocked_by=((2, "OPEN", spelling),)),
            issue(2),
            issue(3, body=f"Board after: {spelling}#2\n"),
            issue(4, body=f"Board after: [#2](https://github.com/{spelling}/issues/2)\n"),
            issue(5),
        ],
        [pull(20, closes=((5, spelling),))],
    )
    board, report = bb.build(gh, run_repo, 30, NOW)
    assert card(board, 1)["needs"] == [2]
    assert card(board, 3)["after"] == [2]
    assert card(board, 4)["after"] == [2]
    assert [p["issue"] for p in prs_of(board)] == [5]
    assert report["refused"] == []


OTHER = "Board after, naming another repository"
DISAGREE = "Board after, link and number disagree"
HERE = "https://github.com/octo-org/octo-repo"


@pytest.mark.parametrize(
    ("line", "after", "refused"),
    [
        ("#2", [2], []),
        ("octo-org/octo-repo#2", [2], []),
        (f"[#2]({HERE}/issues/2)", [2], []),
        (f"[#2]({HERE}/pull/2)", [2], []),
        (f"[#2]({HERE}/issues/2#issuecomment-5)", [2], []),
        (f"[#2]({HERE}/pull/2/files)", [2], []),
        ("other/repo#2", None, [OTHER]),
        ("[#2](https://github.com/other/repo/issues/2)", None, [OTHER]),
        ("[#2](https://example.com/issues/2)", None, [OTHER]),
        (f"[#2]({HERE}/issues/3)", None, [DISAGREE]),
        ("other/repo#3 [#4](https://github.com/o/r/issues/5)", None, [OTHER]),
        (f"other/repo#3, [#4]({HERE}/issues/5), #2", [2], [DISAGREE, OTHER]),
        ("x#2 and a/#3", None, []),
        (f"[#2]({HERE}/issues/2x)", None, [OTHER]),
        # Three behaviours ported from l3a0/marketlake and named on #48. A
        # `#N` right after `/`, `-`, `.` or a word character is skipped with
        # nothing listed.
        ("#3/#4", [3], []),
        ("#3-#4", [3], []),
        ("repo-template#3 #4", [4], []),
        # A link to an address that is not an issue's is refused as naming
        # another repository, and a zero-padded number as a disagreement.
        ("[#2](../issues/2)", None, [OTHER]),
        (f"[#2]({HERE}/discussions/2)", None, [OTHER]),
        (f"[#2]({HERE}/issues/02)", None, [DISAGREE]),
        # A link that opens with `[#N](` and that `LINK_REF` cannot read is
        # refused, so its `#N` never reads as an issue here.
        ('[#2](https://github.com/other/repo/issues/2 "title")', None, [OTHER]),
        ("[#2]( https://github.com/other/repo/issues/2)", None, [OTHER]),
        ("[#2](https://github.com/other/repo/issues/2(x))", None, [OTHER]),
        # A reference-style link names no address on the line, so it reads as
        # its `#N`.
        ("[#2][ref]", [2], []),
        ("[#2](https://gitlab.com/octo-org/octo-repo/issues/2)", None, [OTHER]),
        (
            "[#2](https://evil.example/https://github.com/octo-org/octo-repo/issues/2)",
            None,
            [OTHER],
        ),
        ("x-#2 and x.#2", None, []),
        (f"[#2]({HERE}/issues/2#3)", [2], []),
    ],
)
def test_each_reference_shape_on_an_after_line(
    line: str, after: list[int] | None, refused: list[str]
) -> None:
    """Protects ``after`` from an issue number that belongs to another repository.

    Read as a bare ``#N``, another repository's number would order the card
    behind an issue here it does not mean. A link whose text and address name
    different numbers is refused too, because nothing says which was meant. A
    refused reference leaves the rest of its line read, and a line naming
    nothing at all is listed as unread.
    """
    gh = FakeGitHub(
        [issue(1, body=f"Board after: {line}\n"), *(issue(n) for n in (2, 3, 4, 5))], []
    )
    board, report = build(gh)
    assert card(board, 1).get("after") == after
    assert report["refused"] == [(1, phrase) for phrase in refused]
    assert report["unread"] == ([] if after or refused else [(1, "Board after")])


def test_a_strangers_refused_reference_is_listed_once_a_kind() -> None:
    """Protects the summary from a stranger filling it with refused references."""
    line = " ".join(f"other/repo#{i} [#{i}]({HERE}/issues/{i + 1})" for i in range(50))
    gh = FakeGitHub([issue(1, body=f"Board after: {line}\n" * 3, association="NONE")], [])
    _, report = build(gh)
    assert report["refused"] == [(1, DISAGREE), (1, OTHER)]


STRANGER_BODY = "Board order: 4\nBoard after: #2\n"


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "COLLABORATOR", "MEMBER"])
def test_owner_body_lines_refuses_a_strangers_order_and_after(association: str) -> None:
    """Protects the order from a stranger's body, once the caller asks for that.

    Anyone can open an issue on a public repository. With the input empty a
    stranger's lines count, as they always have. With it ``true`` they set
    nothing, and each kind is listed as refused.
    """
    issues = [issue(1, labels=("band:1",), body=STRANGER_BODY, association=association), issue(2)]
    board, report = bb.build(FakeGitHub(issues, []), REPO, 30, NOW, owner_body_lines="true")
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan"}]
    assert "after" not in card(board, 1)
    assert report["refused"] == [
        (1, "Board after, not the owner's"),
        (1, "Board order, not the owner's"),
    ]
    assert report["unread"] == []
    board, report = build(FakeGitHub(issues, []))
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert card(board, 1)["after"] == [2]
    assert report["refused"] == []


def test_owner_body_lines_still_reads_the_owners_body() -> None:
    """Protects the owner's own lines once the input is on."""
    issues = [issue(1, labels=("band:1",), body=STRANGER_BODY), issue(2)]
    board, report = bb.build(FakeGitHub(issues, []), REPO, 30, NOW, owner_body_lines="true")
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert card(board, 1)["after"] == [2]
    assert report["refused"] == []


@pytest.mark.parametrize(
    "body",
    [
        "Board order: first\nBoard after soon\n",
        "```\nBoard order: 4\nBoard after: #2\n```\n",
        "See Board order: 4 in the skill.\n",
        "",
    ],
)
def test_owner_body_lines_refuses_only_lines_that_would_count(body: str) -> None:
    """Protects the refused row from listing a stranger's prose or quotes."""
    issues = [issue(1, body=body, association="NONE"), issue(2)]
    _, report = bb.build(FakeGitHub(issues, []), REPO, 30, NOW, owner_body_lines="true")
    assert report["refused"] == []
    assert report["unread"] == []


@pytest.mark.parametrize("value", ["yes", "True", "TRUE", "1", "false", " true", "true "])
def test_an_owner_body_lines_value_other_than_empty_or_true_stops_the_run(value: str) -> None:
    """Protects a caller that misspells the input from strangers' lines counting.

    The run stops before it reads GitHub, as a refused data label does.
    """
    fake = FakeGitHub([issue(1)], [])
    with pytest.raises(bb.BoardError, match="owner-body-lines"):
        bb.build(fake, REPO, 30, NOW, owner_body_lines=value)
    assert fake.calls == []


def test_the_command_line_passes_owner_body_lines_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the reusable workflow's ``owner-body-lines`` input on its way to the read.

    The workflow passes the input as ``--owner-body-lines`` whether or not the
    caller set it, so an empty value has to read anyone's body, and a refused
    one has to fail the run with its reason in the summary.
    """
    issues = [issue(1, labels=("band:1",), body=STRANGER_BODY, association="NONE"), issue(2)]
    fake = FakeGitHub(issues, [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def entry() -> dict:
        return json.loads((out / "board.json").read_text())["next"]["items"][0]

    assert bb.main([*argv, "--owner-body-lines=true"]) == 0
    assert "order" not in entry()
    assert summary_row(summary.read_text(), "Marker lines refused") == (
        "#1 Board after, not the owner's; #1 Board order, not the owner's"
    )
    assert bb.main([*argv, "--owner-body-lines="]) == 0
    assert entry()["order"] == 4
    assert bb.main(argv) == 0
    assert entry()["order"] == 4
    (out / "board.json").unlink()
    summary.unlink()
    assert bb.main([*argv, "--owner-body-lines=yes"]) == 1
    assert not (out / "board.json").exists()
    assert "build_board: the owner-body-lines input 'yes' is neither empty nor true" in (
        summary.read_text()
    )


# ---- Ranking by order lines alone ----
#
# ``--ranking=order`` ranks a card by its ``Board order:`` line alone, as
# l3a0/marketlake's generator does, for a repository that keeps no ``band:N``
# labels. The cases are ported from ``tests/unit/test_board_generator.py`` in
# l3a0/marketlake at commit ``cc9d3432``, and each also runs with the input
# empty, where the board has to be the one the band rule wrote before.


def ranked(ranking: str, issues: list[dict], data_label: str = "") -> tuple[dict, dict]:
    """The board and report for ``issues`` under ``ranking``."""
    return bb.build(FakeGitHub(issues, []), REPO, 30, NOW, data_label=data_label, ranking=ranking)


@pytest.mark.parametrize(
    ("labels", "sub_issues", "by_band", "by_order"),
    [
        (("deferred",), (2, 1), "parent", "parent"),
        (("enhancement",), (1, 0), "parent", "parent"),
        (("deferred",), (2, 2), "parent", "deferred"),
        (("enhancement", "deferred"), (0, 0), "deferred", "deferred"),
        (("enhancement",), (3, 3), "parent", "ready"),
        (("decision",), (1, 1), "parent", "decision"),
        ((), (0, 0), "ready", "ready"),
    ],
)
def test_a_parent_under_order_is_one_with_an_open_sub_issue(
    labels: tuple[str, ...], sub_issues: tuple[int, int], by_band: str, by_order: str
) -> None:
    """Protects the parent rule each input asks for.

    ``subIssuesSummary`` counts closed sub-issues in ``total`` too. With the
    input empty any sub-issue makes a parent, as before, because closed
    children carry a parent's work. Under ``order`` only an open one does, so
    an issue whose children have all closed is the card its labels say.
    """
    issues = [issue(1, labels=labels, sub_issues=sub_issues)]
    assert card(ranked("", issues)[0], 1)["kind"] == by_band
    assert card(ranked("order", issues)[0], 1)["kind"] == by_order


@pytest.mark.parametrize(
    ("body", "order"),
    [
        ("Board order: 3", 3),
        ("Board order: 0", 0),
        ("Board order: -2", -2),
        ("Board order: 14.5", 14.5),
        ("Board order: 2.0", 2),
        ("Intro.\n\n \tBoard order: 7\t\n\nMore prose.", 7),
        ("Board order: 7\r\nBoard after: #2\r\n", 7),
        ("Board order: 123456789012345", 123456789012345),
        ("Board order: -123456789012345", -123456789012345),
        ("Board order: 12345678901234.5", 12345678901234.5),
    ],
)
def test_an_order_line_in_the_owners_body_ranks_the_card(body: str, order: float) -> None:
    """Protects a repository with no band labels from a board that ranks nothing.

    Under ``order`` every entry carries band 0, so the order alone ranks a
    card. With the input empty the same issue carries no ``band:N`` label and
    ranks nowhere, as before.
    """
    issues = [issue(1, body=body), issue(2)]
    board, report = ranked("order", issues)
    assert board["next"]["items"] == [{"issue": 1, "band": 0, "ready": "plan", "order": order}]
    assert type(board["next"]["items"][0]["order"]) is type(order)
    assert report["unread"] == report["label_conflicts"] == report["dropped"] == []
    assert board["state"]["ranking"] == "order"
    board, _ = ranked("", issues)
    assert board["next"]["items"] == []
    assert "ranking" not in board["state"]


def test_under_order_a_band_label_neither_ranks_a_card_nor_sets_its_band() -> None:
    """Protects the order from a band label a repository left behind.

    #1 carries two band labels and an order, #2 a band label and no order. With
    the input empty both rank by band and the two labels are reported. Under
    ``order`` #1 ranks at band 0 with nothing reported, and #2 does not rank.
    """
    issues = [
        issue(1, labels=("band:2", "band:3"), body="Board order: 5"),
        issue(2, labels=("band:1",)),
    ]
    board, report = ranked("order", issues)
    assert board["next"]["items"] == [{"issue": 1, "band": 0, "ready": "plan", "order": 5}]
    assert report["label_conflicts"] == []
    assert card(board, 1)["labels"] == []
    board, report = ranked("", issues)
    assert board["next"]["items"] == [
        {"issue": 1, "band": 2, "ready": "plan", "order": 5},
        {"issue": 2, "band": 1, "ready": "plan"},
    ]
    assert report["label_conflicts"] == ["#1 carries 2 band labels, read as band:2"]


def test_under_order_the_first_of_several_order_lines_wins_and_is_reported() -> None:
    issues = [
        issue(1, body="Board order: 4\nBoard order: 9"),
        issue(2, body="Board order: 5\n" * 2),
    ]
    board, report = ranked("order", issues)
    assert [(x["issue"], x["order"]) for x in board["next"]["items"]] == [(1, 4), (2, 5)]
    assert report["label_conflicts"] == [
        "#1 carries 2 order lines, read as 4",
        "#2 carries 2 order lines, read as 5",
    ]


def test_a_verdict_and_an_order_on_a_parent_are_dropped_and_reported() -> None:
    """Protects a parent from being offered to a builder.

    A parent builds nothing. Under ``order`` its order and its verdict are
    dropped, from ``next`` and from ``planned``, and both drops are listed.
    With the input empty a band label ranks it with its verdict, as before,
    and nothing is listed.
    """
    one = issue(
        1,
        labels=("band:1",),
        sub_issues=(2, 1),
        body="Board order: 1",
        comments=(("OWNER", VERDICT_LINE),),
    )
    board, report = ranked("order", [one])
    assert board["planned"]["items"] == board["next"]["items"] == []
    assert report["dropped"] == [(1, "Board order on a parent"), (1, "Board verdict on a parent")]
    board, report = ranked("", [one])
    assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "build", "order": 1}]
    assert report["dropped"] == []


def test_a_parent_whose_sub_issues_have_all_closed_keeps_its_order_and_verdict() -> None:
    """Protects the drop from reaching a card that is no longer a parent under ``order``."""
    one = issue(1, sub_issues=(3, 3), body="Board order: 1", comments=(("OWNER", VERDICT_LINE),))
    board, report = ranked("order", [one])
    assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]
    assert board["next"]["items"] == [{"issue": 1, "band": 0, "ready": "build", "order": 1}]
    assert report["dropped"] == []


@pytest.mark.parametrize(
    "labels", [("deferred",), ("deferred", DATA_LABEL)], ids=["deferred", "deferred data"]
)
def test_a_verdict_on_a_deferred_card_is_dropped_and_its_order_kept(
    labels: tuple[str, ...],
) -> None:
    """Protects a deferred card from being offered to a builder.

    Nobody should take a deferred card, so under ``order`` its verdict is
    dropped and listed. It keeps its order, which the page hides. The label is
    read rather than the kind, because a data label takes the kind ahead of
    ``deferred``. With the input empty a band label ranks it with its verdict.
    """
    one = issue(
        1, labels=(*labels, "band:2"), body="Board order: 1", comments=(("OWNER", VERDICT_LINE),)
    )
    board, report = ranked("order", [one], DATA_LABEL)
    assert board["planned"]["items"] == []
    assert board["next"]["items"] == [{"issue": 1, "band": 0, "ready": "plan", "order": 1}]
    assert report["dropped"] == [(1, "Board verdict on a deferred card")]
    board, report = ranked("", [one], DATA_LABEL)
    assert board["planned"]["items"] == [{"n": 1, "passes": 2, "ready": "build"}]
    assert board["next"]["items"] == [{"issue": 1, "band": 2, "ready": "build", "order": 1}]
    assert report["dropped"] == []


@pytest.mark.parametrize("association", ["NONE", "CONTRIBUTOR", "COLLABORATOR", "MEMBER"])
def test_under_order_a_strangers_order_line_ranks_nothing(association: str) -> None:
    """Protects the order from a stranger's issue putting itself first.

    Under ``order`` a body line alone ranks a card, so the run reads body
    lines only from the owner's issues, with ``owner-body-lines`` left empty.
    The stranger's lines are listed as refused. With the input empty the
    stranger's line counts on a card a band label ranks, as before.
    """
    issues = [issue(1, labels=("band:1",), body=STRANGER_BODY, association=association), issue(2)]
    board, report = ranked("order", issues)
    assert board["next"]["items"] == []
    assert "after" not in card(board, 1)
    assert report["refused"] == [
        (1, "Board after, not the owner's"),
        (1, "Board order, not the owner's"),
    ]
    board, report = ranked("", issues)
    assert board["next"]["items"] == [{"issue": 1, "band": 1, "ready": "plan", "order": 4}]
    assert report["refused"] == []


@pytest.mark.parametrize("value", ["true", "Order", "ORDER", "band", " order", "order ", "1"])
def test_a_ranking_value_other_than_empty_or_order_stops_the_run(value: str) -> None:
    """Protects a caller that misspells the input from a board that ranks nothing.

    A misspelt value would otherwise keep the band rule and draw a repository
    with no band labels an empty build order. The run stops before it reads
    GitHub, as a refused data label does.
    """
    fake = FakeGitHub([issue(1)], [])
    with pytest.raises(bb.BoardError, match="ranking is"):
        bb.build(fake, REPO, 30, NOW, ranking=value)
    assert fake.calls == []


def test_the_command_line_passes_the_ranking_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the reusable workflow's ``ranking`` input on its way to the read.

    The workflow passes the input as ``--ranking`` whether or not the caller
    set it, so an empty value has to keep the band rule and write no
    ``state.ranking``, and lists the orders on #2 and #3, which carry no
    band, as dropped. ``order`` ranks #2 by its line alone and lists only the
    drop on the parent #3. A refused value fails the run with
    its reason in the summary.
    """
    issues = [
        issue(1, labels=("band:1",)),
        issue(2, body="Board order: 4\n"),
        issue(3, sub_issues=1, body="Board order: 1\n"),
    ]
    fake = FakeGitHub(issues, [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def board() -> dict:
        return json.loads((out / "board.json").read_text())

    assert bb.main([*argv, "--ranking=order"]) == 0
    assert board()["state"]["ranking"] == "order"
    assert [x["issue"] for x in board()["next"]["items"]] == [2]
    assert summary_row(summary.read_text(), "Markers dropped") == "#3 Board order on a parent"
    summary.unlink()
    assert bb.main([*argv, "--ranking="]) == 0
    assert "ranking" not in board()["state"]
    assert [x["issue"] for x in board()["next"]["items"]] == [1]
    assert summary_row(summary.read_text(), "Markers dropped") == (
        "#2 Board order on a card with no band; #3 Board order on a card with no band"
    )
    assert bb.main(argv) == 0
    assert "ranking" not in board()["state"]
    (out / "board.json").unlink()
    summary.unlink()
    assert bb.main([*argv, "--ranking=true"]) == 1
    assert not (out / "board.json").exists()
    assert "build_board: ranking is 'true', and takes only empty or order" in summary.read_text()


def ranking_tracker() -> FakeGitHub:
    """A tracker holding every case ``--ranking=order`` reads differently.

    Orders with and without a band label, a band label with no order, parents
    with an open sub-issue and with every sub-issue closed, deferred cards
    with verdicts, one of them also a data card, and strangers' order lines
    with and without a band label.
    """
    passed = (("OWNER", VERDICT_LINE),)
    return FakeGitHub(
        [
            issue(1, labels=("band:1",), body="Board order: 2\n"),
            issue(2, body="Board order: 1\n"),
            issue(3, labels=("band:2",)),
            issue(
                4, labels=("band:1",), sub_issues=(2, 1), body="Board order: 3\n", comments=passed
            ),
            issue(
                5, labels=("band:1",), sub_issues=(3, 3), body="Board order: 4\n", comments=passed
            ),
            issue(6, sub_issues=(1, 1), comments=passed),
            issue(7, labels=("deferred", "band:2"), body="Board order: 5\n", comments=passed),
            issue(8, labels=("deferred", DATA_LABEL), comments=passed),
            issue(9, labels=("deferred",), body="Board order: 6\n", comments=passed),
            issue(10, labels=("band:1",), body="Board order: 0.5\n", association="NONE"),
            issue(11, body="Board order: 7\n", association="CONTRIBUTOR"),
            issue(12, labels=("decision", "band:3"), comments=passed),
        ],
        [],
    )


RANKING_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "ranking.json"


def test_a_caller_that_sets_no_ranking_gets_the_board_it_got_before() -> None:
    """Protects every current caller from a board that moves.

    ``RANKING_GOLDEN`` is the ``board.json`` that the generator at
    l3a0/repo-template commit cf2959a3 wrote for ``ranking_tracker`` with the
    data label set, and this run, with no ``ranking`` input, has to write the
    same bytes. That generator read ``subIssues{totalCount}``, so it was fed
    each issue with that field set to ``subIssuesSummary.total``. The orders
    on the three unbanded cards rank nothing and are listed as dropped, as
    under the band rule they always are, and no drop ``order`` makes is
    listed.
    """
    board, report = build(ranking_tracker(), DATA_LABEL)
    written = json.dumps(board, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert written == RANKING_GOLDEN.read_text(encoding="utf-8").removesuffix("\n")
    assert report["dropped"] == [
        (2, "Board order on a card with no band"),
        (9, "Board order on a card with no band"),
        (11, "Board order on a card with no band"),
    ]


def test_the_same_tracker_under_order_ranks_by_its_lines_alone() -> None:
    """Protects the cases the golden holds, read the way ``order`` reads them."""
    board, report = ranked("order", ranking_tracker().issues, DATA_LABEL)
    assert board["next"]["items"] == [
        {"issue": 1, "band": 0, "ready": "plan", "order": 2},
        {"issue": 2, "band": 0, "ready": "plan", "order": 1},
        {"issue": 5, "band": 0, "ready": "build", "order": 4},
        {"issue": 7, "band": 0, "ready": "plan", "order": 5},
        {"issue": 9, "band": 0, "ready": "plan", "order": 6},
    ]
    assert [(p["n"], p["ready"]) for p in board["planned"]["items"]] == [
        (5, "build"),
        (6, "build"),
        (12, "build"),
    ]
    assert [card(board, n)["kind"] for n in (4, 5, 6)] == ["parent", "ready", "ready"]
    assert report["dropped"] == [
        (4, "Board order on a parent"),
        (4, "Board verdict on a parent"),
        (7, "Board verdict on a deferred card"),
        (8, "Board verdict on a deferred card"),
        (9, "Board verdict on a deferred card"),
    ]
    assert report["refused"] == [
        (10, "Board order, not the owner's"),
        (11, "Board order, not the owner's"),
    ]


RANKING_PAGE = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "ranking-page.json"


def in_flight_tracker() -> FakeGitHub:
    """A band-rule tracker whose one ranked card is in flight.

    #1 is ranked and has an open pull request, so the build order holds
    nothing ranked while the ranking does. Beside it sit unranked cards, one
    behind another, a parent and a deferred card with a band.
    """
    return FakeGitHub(
        [
            issue(1, labels=("band:1",), body="Board order: 1\n"),
            issue(2),
            issue(3, blocked_by=((2, "OPEN"),)),
            issue(4, sub_issues=(2, 1)),
            issue(5, labels=("deferred", "band:2")),
        ],
        [pull(20, closes=(1,))],
    )


def unranked_tracker() -> FakeGitHub:
    """A band-rule tracker that ranks nothing.

    #1 carries an order line and no band, so it ranks nowhere. The rest are an
    unranked card, one behind it, a parent and a deferred card.
    """
    return FakeGitHub(
        [
            issue(1, body="Board order: 1\n"),
            issue(2),
            issue(3, blocked_by=((2, "OPEN"),)),
            issue(4, sub_issues=(2, 1)),
            issue(5, labels=("deferred",)),
        ],
        [],
    )


# Each case's tracker and the card it picks, which draws the chain bar.
PAGE_CASES = {
    "ranking_tracker": (ranking_tracker, 1),
    "ranked_card_in_flight": (in_flight_tracker, 2),
    "nothing_ranked": (unranked_tracker, 2),
}


@pytest.mark.parametrize("case", list(PAGE_CASES))
def test_the_page_draws_a_board_with_no_ranking_as_it_did_before(tmp_path: Path, case: str) -> None:
    """Protects every current caller's page from a change it did not ask for.

    ``RANKING_PAGE`` holds, for each case, what the page at
    l3a0/repo-template commit cf2959a3 drew from the ``board.json`` that the
    generator at that commit wrote for the case's tracker, with its card
    picked. It covers eight elements: the build order, the line above it, the
    board note, the order note, the In flight section, its note, the chain
    under it and the chain bar. The page here, drawing what the generator
    writes with no ``ranking`` input, has to draw the same. None of the eight
    carries the board's age, so the golden does not move with the clock.

    The second and third cases reach the branches ``ranking: order`` adds. One
    ranks only a card in flight and one ranks nothing, which is where the
    unranked view, the line above the board and the order note's reasons
    differ from the band rule's.
    """
    tracker, picked = PAGE_CASES[case]
    board, _ = build(tracker(), DATA_LABEL)
    ids = draw_page(tmp_path, board, click=picked)
    golden = json.loads(RANKING_PAGE.read_text(encoding="utf-8"))[case]
    assert {element: ids[element]["html"] for element in golden} == golden


def test_the_page_draws_every_card_the_generator_writes_when_nothing_is_ranked(
    tmp_path: Path,
) -> None:
    """Protects the join between the generator's ``state.ranking`` and the page.

    With no order line on any card, ``next`` is empty. Under ``order`` the
    page opens on MVP 4 and draws every card there, under a line saying why.
    The parent #1 counts, and so does #3, whose sub-issues have all closed and
    which is a plain card here. The same issues with the input empty draw
    only the parent, as before.
    """
    issues = [
        issue(1, milestone="MVP 4, serve the bars", sub_issues=(3, 1)),
        issue(2, milestone="MVP 4, serve the bars"),
        issue(3, milestone="MVP 4, serve the bars", sub_issues=(2, 2), blocked_by=((2, "OPEN"),)),
        issue(4, milestone="MVP 5, take orders"),
        issue(5, milestone=None, labels=("deferred",)),
    ]
    board, _ = bb.build(
        FakeGitHub(issues, []), REPO, 30, NOW, milestone_default="MVP <n>", ranking="order"
    )
    assert board["next"]["items"] == []
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = draw_page(tmp_path, board)
    assert ids["mssel"]["value"] == "MVP 4"
    assert cards(ids, "board") == {1, 2, 3}
    assert text(ids, "more") == (
        "Nothing in MVP 4 is ranked yet, so all 3 open issues in MVP 4 not in flight are showing."
    )
    board, _ = build(FakeGitHub(issues, []), milestone_default="MVP <n>")
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = draw_page(tmp_path, board)
    assert cards(ids, "board") == {1, 3}


def test_under_order_an_order_of_zero_sorts_first(tmp_path: Path) -> None:
    """Protects the card at ``Board order: 0`` on a board ranked by order alone.

    Under ``ranking: order`` the order is the whole ranking, so a fallback
    that read 0 as missing put that card last. Ported from
    ``test_an_order_of_zero_sorts_first`` in l3a0/marketlake's
    ``tests/component/test_board_page.py`` at commit ``cc9d3432``.
    """
    gh = FakeGitHub(
        [
            issue(10, body="Board order: 1\n"),
            issue(11, body="Board order: 30\n"),
            issue(12, body="Board order: 0\n"),
        ],
        [],
    )
    board, _ = ranked("order", gh.issues)
    assert [(x["issue"], x["order"]) for x in board["next"]["items"]] == [
        (10, 1),
        (11, 30),
        (12, 0),
    ]
    chips, _ = _rank_chips(tmp_path, board)
    assert chips == {12: 1, 10: 2, 11: 3}


def test_under_order_a_first_column_with_no_free_card_lists_none(tmp_path: Path) -> None:
    """Protects the board note when every card drawn is a parent.

    Ported from l3a0/marketlake's ``test_a_first_column_with_no_free_card_lists_none``
    at commit ``cc9d3432``. Both cards are parents with an open sub-issue, so
    nothing ranks, every card is drawn, and none is free to take.
    """
    issues = [
        issue(755, milestone="MVP 2", sub_issues=(3, 1)),
        issue(865, milestone="MVP 2", sub_issues=(2, 0)),
    ]
    board, _ = bb.build(
        FakeGitHub(issues, []), REPO, 30, NOW, milestone_default="MVP <n>", ranking="order"
    )
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = draw_page(tmp_path, board)
    assert cards(ids, "board") == {755, 865}
    assert text(ids, "more") == (
        "Nothing in MVP 2 is ranked yet, so all 2 open issues in MVP 2 not in flight are showing."
    )
    assert text(ids, "boardnote").startswith(
        "0 cards are free for a session to take today , out of 2 in the first column. "
        "2 cards there are not free, because a card can be a parent whose children carry "
        "the work"
    )


def test_under_order_the_page_draws_what_the_generator_writes(tmp_path: Path) -> None:
    """Protects the join between the two halves under ``ranking: order``.

    Ported from l3a0/marketlake's ``test_the_page_draws_what_the_generator_writes``
    at commit ``cc9d3432``. Each card lands somewhere different.

    1. #20 carries ``working:build`` and has no branch, so it is under Building.
    2. #21 carries ``working:decompose``, so it is under Being planned.
    3. #22 has an owner verdict and nothing blocking it, so it is under
       Planned, no builder.
    4. #23 is ranked at order 1 with an after line naming #24, so it stays in
       the build order with its chip.
    5. #24 is ranked behind it at order 2.5.
    """
    issues = [
        issue(20, labels=("working:build",)),
        issue(21, labels=("working:decompose",)),
        issue(
            22,
            comments=(("OWNER", "## Plan audit, pass 3\n\nBoard verdict: build after 3 passes"),),
        ),
        issue(23, body="Board order: 1\nBoard after: #24"),
        issue(24, body="Board order: 2.5"),
    ]
    board, _ = ranked("order", issues)
    assert [w["n"] for w in board["working"]["items"]] == [20, 21]
    assert [p["n"] for p in board["planned"]["items"]] == [22]
    assert board["next"]["items"] == [
        {"issue": 23, "band": 0, "ready": "plan", "order": 1},
        {"issue": 24, "band": 0, "ready": "plan", "order": 2.5},
    ]
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = draw_page(tmp_path, board)
    assert cards(ids, "flow") == {20, 21, 22}
    flow = text(ids, "flow")
    for heading in ("Building", "Being planned", "Planned, no builder"):
        assert heading in flow
    assert "plan complete, 3 passes" in flow
    assert "undefined" not in json.dumps(ids)
    assert cards(ids, "board") == {23, 24}
    chips, _ = _rank_chips(tmp_path, board)
    assert chips == {23: 1, 24: 2}
    assert "it should land after #24" in text(ids, "board")


def test_a_verdict_on_a_deferred_parent_is_dropped_as_a_parents() -> None:
    """Protects which phrase a card that is both a parent and deferred gets.

    The parent rule is checked first, so the drop names the parent.
    """
    one = issue(1, labels=("deferred",), sub_issues=(2, 1), comments=(("OWNER", VERDICT_LINE),))
    _, report = ranked("order", [one])
    assert report["dropped"] == [(1, "Board verdict on a parent")]


# A 65,000-character line of each shape. Anyone can write an issue body, and the
# build job has a 10-minute limit. The link pattern l3a0/marketlake uses
# retried the rest of the line from every `[#N](` no `)` closed, and the first
# shape took 9.6 s through it. Every shape here took under 6 ms through the
# patterns ported, so a second leaves room for a loaded runner.
HOSTILE = [
    "[#1](",
    "[#1](https://github.com/",
    "[#1](https://github.com/a/b/issues/",
    "a",
    "/",
    "1",
    "#",
    "#1",
    "a/",
    "a/b#",
    ".-",
    "[",
    "](",
]


@pytest.mark.parametrize("shape", HOSTILE)
def test_a_long_hostile_after_line_reads_inside_a_second(shape: str) -> None:
    """Protects every board run from a stranger's line built to be slow to read."""
    line = "Board after: " + shape * (65_000 // len(shape))
    gh = FakeGitHub([issue(1, body=f"{line}\n", association="NONE")], [])
    start = time.perf_counter()
    build(gh)
    assert time.perf_counter() - start < 1.0


@pytest.mark.parametrize("run", ["`" * 65_536, "~" * 65_536], ids=["backticks", "tildes"])
def test_a_long_fence_run_with_no_newline_reads_inside_a_second(run: str) -> None:
    """Protects every board run from a stranger's body or comment that opens no fence.

    Every body and comment has its fences removed before anything checks who
    wrote it. A greedy opening run tried every shorter run on a last line of
    backticks with no newline after it, and 65,536 of them took about 3 s.
    About 200 such comments would have run every caller's build past its
    10-minute limit, whatever ``owner-body-lines`` said.
    """
    gh = FakeGitHub([issue(1, body=run, association="NONE", comments=(("NONE", run),))], [])
    start = time.perf_counter()
    build(gh)
    assert time.perf_counter() - start < 1.0


def test_an_issues_comments_and_blockers_are_read_to_their_end() -> None:
    """Protects a verdict or a blocker past the first hundred.

    An issue's comments go under an alias, because a pull request's comments
    share the name, and the further pages must ask for the issue's.
    """
    first = issue(5, labels=("band:2",))
    first["issueComments"] = conn([], more=True, cursor="c1")
    first["blockedBy"] = conn([], more=True, cursor="b1")
    nested = {
        ("I5", "issueComments", "c1"): conn(
            [{"authorAssociation": "OWNER", "body": "Board verdict: build after 2 passes"}]
        ),
        ("I5", "blockedBy", "b1"): conn([blocker(6, "OPEN")]),
    }
    gh = FakeGitHub([first, issue(6)], [], nested)
    board, _ = build(gh)
    assert card(board, 5)["needs"] == [6]
    assert board["planned"]["items"] == [{"n": 5, "passes": 2, "ready": "build"}]
    paged = [q for q in gh.calls if "node(id:$id)" in q]
    assert any("issueComments: comments(" in q for q in paged)


def test_a_pull_request_from_a_fork_gets_no_item() -> None:
    """Protects the free list from a stranger's branch.

    Anyone can open a pull request on a public repository, and one whose body
    says ``Part of`` an issue, or closes it, would otherwise draw a branch on
    that card. Dependabot's branches live here, so they still count.
    """
    gh = FakeGitHub(
        [issue(5), issue(6)],
        [
            pull(7, body="Part of #5", fork=True),
            pull(8, closes=(6,), fork=True),
            pull(9, closes=(6,)),
        ],
    )
    board, report = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == [(9, 6)]
    assert report["open_prs_left_out"] == [7, 8]


def test_a_cross_reference_from_another_repository_reads_nothing_here() -> None:
    """Protects the run from a sibling repository's pull request number.

    Issue 40 here is cross-referenced from pull requests in
    ``octo-org/sibling`` and ``octo-org/other``. Read by number,
    such a reference would fetch this repository's pull request of the same
    number, or stop the run when there is none.
    """
    first = issue(40)
    first["timelineItems"] = conn(
        [{"source": {"number": 999, "repository": {"nameWithOwner": "other/repo"}}}]
    )
    gh = FakeGitHub([first], [])
    board, report = build(gh)
    assert prs_of(board) == []
    assert report["other_prs_read"] == 0
    assert not any("pullRequest(number:999" in q for q in gh.calls)


@pytest.mark.parametrize("here", [False, True])
def test_an_issue_closed_from_another_repository_reads_nothing_here(here: bool) -> None:
    """Protects the run from another repository's closing pull request.

    Issue 40 here is closed by pull request 34 in ``other/repo``, which a
    closing keyword such as "closes octo-org/octo-repo#40" there registers.
    Read by number in this repository, the reference stops the run when there
    is no pull request 34 here, and reads an unrelated one when there is.
    """
    prs = [pull(34, state="MERGED", body="Bumps ruff.")] if here else []
    gh = FakeGitHub([issue(40, closed_by=((34, "other/repo"),))], prs)
    board, report = build(gh)
    assert prs_of(board) == []
    assert report["other_prs_read"] == 0
    assert not any("pullRequest(number:" in q for q in gh.calls)


@pytest.mark.parametrize("here", [REPO, "octo-org/second-repo"])
def test_a_closing_link_to_another_repositorys_issue_draws_nothing_here(here: str) -> None:
    """Protects a card from a branch that closes another repository's issue.

    Pull request 10 closes ``other/repo#1``, and issue 1 here is open. Read as
    this repository's issue 1, the link would draw the branch on that card as
    a closing link. Pull request 11 closes ``other/repo#3`` and issue 2 here,
    so it draws on 2 alone. Pull request 12 closes ``other/repo#5`` and is part
    of issue 5 here, so it draws on 5 as a ``Part of`` branch, not a closing one.
    The board is built for two repositories, so "here" is whichever repository
    the run was given rather than one name the generator could carry.
    """
    gh = FakeGitHub(
        [issue(1), issue(2), issue(3), issue(5)],
        [
            pull(10, closes=((1, "other/repo"),)),
            pull(11, closes=((3, "other/repo"), (2, here))),
            pull(12, closes=((5, "other/repo"),), body="Part of #5"),
        ],
    )
    board, report = bb.build(gh, here, 30, NOW)
    assert [(p["pr"], p["issue"], p["linked"], p.get("partOf")) for p in prs_of(board)] == [
        (11, 2, True, None),
        (12, 5, False, True),
    ]
    assert report["open_prs_left_out"] == [10]


def test_a_same_named_repository_under_another_owner_is_not_this_one() -> None:
    """Protects the board from a fork or namesake of this repository.

    ``elsewhere/octo-repo`` shares this repository's name under another owner.
    Its issue 1 closed by pull request 10 here, its issue 1 blocking issue 2
    here, and its pull request 34 closing issue 40 here all name that other
    repository, so none of them reads as this one's.
    """
    other = "elsewhere/octo-repo"
    gh = FakeGitHub(
        [issue(1), issue(2, blocked_by=((1, "OPEN", other),)), issue(40, closed_by=((34, other),))],
        [pull(10, closes=((1, other),))],
    )
    board, report = build(gh)
    assert prs_of(board) == []
    assert report["open_prs_left_out"] == [10]
    assert card(board, 2)["needs"] == []
    assert not any("pullRequest(number:34" in q for q in gh.calls)


def entry_selection(query: str, field: str) -> str:
    """What a query selects from each entry of the list ``field`` names."""
    start = query.index("nodes{", query.index(f"{field}(")) + len("nodes{")
    depth, end = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(query[end], 0)
        end += 1
    return " ".join(query[start : end - 1].split())


def test_a_reference_to_another_repository_past_the_first_page_is_dropped() -> None:
    """Protects the filter on the pages after the first hundred links.

    It covers each of the four lists the board keeps only this repository's
    entries of: closed-by links, closing links, cross-references and "blocked
    by" links. The fake answers every query from its fixtures whatever the
    query selects, so the test also reads what each query asks for, on the
    first page and on the pages after it. A query that stopped selecting the
    repository would leave every entry from it reading as another
    repository's, and the live board would lose them while every fixture here
    still carried one. Whitespace is left out of the comparison, because the
    first-page query breaks its cross-reference selection across lines.
    """
    first = issue(5)
    first["closedByPullRequestsReferences"] = conn([], more=True, cursor="b1")
    first["timelineItems"] = conn([], more=True, cursor="t1")
    first["blockedBy"] = conn([], more=True, cursor="x1")
    opened = pull(7)
    opened["closingIssuesReferences"] = conn([], more=True, cursor="k1")
    nested = {
        ("I5", "closedByPullRequestsReferences", "b1"): conn([ref((34, "other/repo")), ref(6)]),
        ("I5", "timelineItems", "t1"): conn(
            [{"source": {"number": 35, "repository": {"nameWithOwner": "other/repo"}}}]
        ),
        ("I5", "blockedBy", "x1"): conn([blocker(9, "OPEN", "other/repo"), blocker(8, "OPEN")]),
        ("P7", "closingIssuesReferences", "k1"): conn([ref((5, "other/repo")), ref(8)]),
    }
    gh = FakeGitHub(
        [first, issue(8), issue(9)], [pull(6, state="MERGED", closes=(5,)), opened], nested
    )
    board, report = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == [(6, 5), (7, 8)]
    assert report["other_prs_read"] == 1
    assert card(board, 5)["needs"] == [8]
    assert not any(re.search(r"pullRequest\(number:3[45]\b", q) for q in gh.calls)
    issues_query = [q for q in gh.calls if "issues(states:OPEN" in q]
    wanted = {
        "closedByPullRequestsReferences": ("number repository{nameWithOwner}", issues_query),
        "timelineItems": (
            "... on CrossReferencedEvent{source{"
            "... on PullRequest{number repository{nameWithOwner}}}}",
            issues_query,
        ),
        "blockedBy": ("number state repository{nameWithOwner}", issues_query),
        "closingIssuesReferences": (
            "number repository{nameWithOwner}",
            [q for q in gh.calls if "pullRequests(states:OPEN" in q or "pullRequest(number:" in q],
        ),
    }
    for field, (selection, first_pages) in wanted.items():
        paged = [q for q in gh.calls if "node(id:$id)" in q and f"{field}: " in q]
        assert first_pages and paged, field
        selected = {"".join(entry_selection(q, field).split()) for q in first_pages + paged}
        assert selected == {"".join(selection.split())}, field


def test_a_null_reference_is_dropped_rather_than_read() -> None:
    """Protects the run from an entry GitHub sent as null.

    GitHub's schema lets an entry of either list, of an issue's "blocked by"
    links or of its cross-references be null, which it sends for an entry the
    token cannot read. A cross-reference can also carry a null source. Every
    issue and pull request here is readable, so a null one belongs to another
    repository, and reading its number would stop the run. An entry that names
    no repository is read the same way, since nothing says it is this one's.
    Pull request 34 does not exist here, and issue 5 is open, so reading either
    unnamed entry as this repository's would fail the run or add an item.
    """
    first = issue(5)
    first["closedByPullRequestsReferences"] = conn([None, {"number": 34}, ref(6)])
    first["blockedBy"] = conn([None, blocker(8, "OPEN")])
    first["timelineItems"] = conn([None, {"source": None}])
    opened = pull(7)
    opened["closingIssuesReferences"] = conn([None, {"number": 5, "repository": None}, ref(8)])
    gh = FakeGitHub([first, issue(8)], [pull(6, state="MERGED", closes=(5,)), opened])
    board, report = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == [(6, 5), (7, 8)]
    assert card(board, 5)["needs"] == [8]
    assert report["other_prs_read"] == 1


def references_fake() -> FakeGitHub:
    """Closing links, closed-by links, cross-references and blockers, all in this repository.

    Issue 1 is closed by open pull request 10 on the first page of its
    closed-by links and by merged pull request 16 on the second. Merged pull
    request 11 closes issue 2. Issue 3 is cross-referenced by merged pull
    request 12, which is part of it. Issue 4 is blocked by issue 1, open, and
    issue 3, closed. Issue 5 is blocked by issue 2 and cross-referenced by
    closed pull request 13, which is part of it. Open pull request 14 closes
    issues 4 and 5 and carries the owner's review, and open pull request 15
    names no issue.
    """
    first = issue(1, closed_by=(10,))
    first["closedByPullRequestsReferences"] = conn([ref(10)], more=True, cursor="c1")
    issues = [
        first,
        issue(2, closed_by=(11,), labels=("band:1",)),
        issue(3, mentioned_by=(12,)),
        issue(4, blocked_by=((1, "OPEN"), (3, "CLOSED"))),
        issue(5, blocked_by=((2, "OPEN"),), mentioned_by=(13,)),
    ]
    prs = [
        pull(10, closes=(1,)),
        pull(11, state="MERGED", closes=(2,)),
        pull(12, state="MERGED", body="Part of #3"),
        pull(13, state="CLOSED", body="Part of #5"),
        pull(14, closes=(4, 5), comments=(("OWNER", "## Review\n"),)),
        pull(15, body="Bumps ruff."),
        pull(16, state="MERGED", closes=(1,)),
    ]
    nested = {("I1", "closedByPullRequestsReferences", "c1"): conn([ref(16)])}
    return FakeGitHub(issues, prs, nested)


def board_bytes(board: dict) -> str:
    """The board as ``cmd_build`` writes it, with the time it was read masked."""
    board["state"]["updatedAt"] = "MASKED"
    return json.dumps(board, ensure_ascii=False, separators=(",", ":"))


REFERENCES_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator" / "references.json"


def test_references_within_this_repository_write_the_board_they_wrote_before() -> None:
    """Protects every caller from a board that moves when no reference leaves the repository.

    ``REFERENCES_GOLDEN`` is the ``board.json`` that the generator at
    l3a0/repo-template commit cf2959a3, before the repository filter, wrote
    for ``references_fake``. Every reference there names this repository, so
    the filter has nothing to drop, and this run has to write the same bytes.
    """
    board, _ = build(references_fake())
    written = board_bytes(board)
    assert written == REFERENCES_GOLDEN.read_text(encoding="utf-8").removesuffix("\n")


def test_a_closed_part_of_pull_request_reads_as_closed() -> None:
    """Protects a card from reading as landed when its branch was abandoned.

    The page frees a card whose pull request closed unmerged, and holds one
    whose pull request merged with no ``Part of``. So the two states must stay
    apart.
    """
    gh = FakeGitHub([issue(5, mentioned_by=(6,))], [pull(6, state="CLOSED", body="Part of #5")])
    board, _ = build(gh)
    assert [(p["pr"], p["state"]) for p in prs_of(board)] == [(6, "closed")]


def test_an_open_pull_request_an_issue_also_references_gets_one_item() -> None:
    """Protects a card from drawing one branch twice.

    An open pull request is read with the open list and is also among the
    issue's cross-references, so it must not be read a second time by number.
    """
    gh = FakeGitHub([issue(5, closed_by=(6,), mentioned_by=(6,))], [pull(6, closes=(5,))])
    board, report = build(gh)
    assert [(p["pr"], p["issue"]) for p in prs_of(board)] == [(6, 5)]
    assert report["other_prs_read"] == 0


def test_a_pull_request_closing_one_issue_and_part_of_another_marks_only_the_second() -> None:
    """Protects the ``Part of`` mark from following whether anything else closes.

    The mark belongs to each issue the pull request names, so one that closes
    5 and is part of 6 leaves 5 to close on merge and 6 open on purpose.
    """
    gh = FakeGitHub([issue(5), issue(6)], [pull(7, closes=(5,), body="Part of #6")])
    board, _ = build(gh)
    assert [(p["issue"], p["linked"], p.get("partOf")) for p in prs_of(board)] == [
        (5, True, None),
        (6, False, True),
    ]


def test_each_check_is_labelled_with_its_own_name() -> None:
    """Protects the label of a status context, which carries no ``name``."""
    contexts = (check("test", "SUCCESS"), status("ci/legacy", "PENDING"))
    gh = FakeGitHub([issue(5)], [pull(6, closes=(5,), contexts=contexts)])
    board, _ = build(gh)
    assert prs_of(board)[0]["rollup"] == [["test", "success"], ["ci/legacy", "running"]]


def test_the_tracker_and_the_pull_requests_come_out_in_number_order() -> None:
    """Protects a board whose order does not depend on how GitHub listed it."""
    gh = FakeGitHub(
        [issue(9), issue(3), issue(5)],
        [pull(40, closes=(9,)), pull(30, closes=(3,)), pull(20, closes=(9,))],
    )
    board, _ = build(gh)
    assert [c["n"] for c in board["tracker"]["items"]] == [3, 5, 9]
    assert [(p["issue"], p["pr"]) for p in prs_of(board)] == [(3, 30), (9, 20), (9, 40)]


def test_a_pull_request_that_cannot_be_read_stops_the_run() -> None:
    """Protects the board from a reference GitHub answers with nothing."""
    gh = FakeGitHub([issue(5, mentioned_by=(77,))], [])
    with pytest.raises(bb.BoardError, match="pull request 77 could not be read"):
        build(gh)


def test_a_node_that_vanishes_mid_read_stops_the_run() -> None:
    """Protects a nested list from being cut short by a node that went away."""

    class Vanishing(FakeGitHub):
        def __call__(self, query: str, variables: dict) -> dict:
            if "node(id:$id)" in query:
                self.calls.append(query)
                return {"node": None}
            return super().__call__(query, variables)

    first = issue(5)
    first["labels"] = conn([], more=True, cursor="l1")
    with pytest.raises(bb.BoardError, match="Issue I5 vanished while reading its labels"):
        build(Vanishing([first], []))


# ---- Where reviewed comes from ----


@pytest.mark.parametrize(
    ("association", "body", "reviewed"),
    [
        ("OWNER", "## Review\n\nFour lenses ran.", True),
        ("OWNER", "\n## Review of the fixes\n", True),
        ("NONE", "## Review\n\nLooks good to me.", False),
        ("CONTRIBUTOR", "## Review\n", False),
        ("COLLABORATOR", "## Review\n", False),
        ("MEMBER", "## Review\n", False),
        ("OWNER", "## Reviewer notes\n", False),
        ("OWNER", "The review is below.\n## Review\n", False),
    ],
)
def test_only_the_owners_review_heading_counts(association: str, body: str, reviewed: bool) -> None:
    """Protects the owner's queue from a stranger's comment.

    Anyone can comment on a public repository, and a comment headed
    ``## Review`` is what moves a pull request toward the owner's column.
    """
    gh = FakeGitHub([issue(5)], [pull(6, closes=(5,), comments=((association, body),))])
    board, _ = build(gh)
    item = prs_of(board)[0]
    assert item["reviewed"] is reviewed
    assert item["review"] == ("review posted" if reviewed else "no review posted")


# ---- The review heading a caller names ----
#
# The times a review is judged against. The head commit was made at HEAD_AT,
# and a marker counts only when posted strictly after it. The name differs
# from HEAD, the commit oid the default-branch-head tests read.
HEAD_AT = "2026-10-29T12:00:00Z"
AFTER = "2026-10-29T12:05:00Z"
BEFORE = "2026-10-29T11:55:00Z"
SECOND_AFTER = "2026-10-29T12:00:01Z"
HEADING = "Review complete"
MARKED = "review complete"
UNMARKED = "no Review complete marker since the head commit"
# The path the board's own runs come from, as the reusable workflow hardcodes
# it for the caller, and a CI workflow beside it.
WORKFLOW_PATH = ".github/workflows/board.yml"
CI_PATH = ".github/workflows/ci.yml"


def _reviewed(pr: dict, **inputs: str) -> tuple[bool, str]:
    """Whether the board reads ``pr``, which closes issue 5, as reviewed, and its words."""
    item = prs_of(build(FakeGitHub([issue(5)], [pr]), **inputs)[0])[0]
    return item["reviewed"], item["review"]


@pytest.mark.parametrize(
    ("comments", "reviews", "marketlake", "shared"),
    [
        ((("OWNER", "## Review complete\n\nAll lenses ran.", AFTER),), (), True, True),
        ((("OWNER", "## Review complete\n", BEFORE),), (), False, True),
        ((("OWNER", "## Review round 1, lenses running\n", AFTER),), (), False, True),
        ((("OWNER", "## Review completeness check\n", AFTER),), (), False, True),
        ((("OWNER", "  ## Review complete\n", AFTER),), (), False, True),
        ((), (("OWNER", "## Review complete\n", AFTER),), True, False),
    ],
    ids=["after-head", "before-head", "round-heading", "longer-heading", "indented", "a-review"],
)
def test_the_review_heading_counts_only_its_own_line_after_the_head(
    comments: tuple, reviews: tuple, marketlake: bool, shared: bool
) -> None:
    """Protects the owner's queue from a review that has not finished, or has gone stale.

    These are the six rows of l3a0/repo-template#47's table. Under
    ``review-heading`` the generator reads l3a0/marketlake's rule: the whole
    first line is the heading, the author is the owner, and it was posted
    after the head commit, as a comment or as a submitted review. Without the
    input the shared rule stands, which counts any owner comment opening
    ``## Review`` at any time and reads no review, so each row checks both.
    """
    pr = pull(6, closes=(5,), comments=comments, reviews=reviews, committed=HEAD_AT)
    assert _reviewed(pr, review_heading=HEADING) == (marketlake, MARKED if marketlake else UNMARKED)
    word = "review posted" if shared else "no review posted"
    assert _reviewed(pr) == (shared, word)


@pytest.mark.parametrize(
    ("comments", "reviews", "committed", "reviewed"),
    [
        ((("OWNER", "## Review complete", AFTER),), (), HEAD_AT, True),
        ((("OWNER", "## Review complete\r\n\r\nAll lenses ran.", AFTER),), (), HEAD_AT, True),
        ((("OWNER", "## Review complete", HEAD_AT),), (), HEAD_AT, False),
        ((("OWNER", "## Review complete.", AFTER),), (), HEAD_AT, False),
        ((("OWNER", "\n## Review complete", AFTER),), (), HEAD_AT, False),
        ((("OWNER", "## Review complete", AFTER),), (), None, False),
        ((("NONE", "## Review complete", AFTER),), (), HEAD_AT, False),
        ((("COLLABORATOR", "## Review complete", AFTER),), (), HEAD_AT, False),
        ((), (("CONTRIBUTOR", "## Review complete", AFTER),), HEAD_AT, False),
        ((), (("OWNER", "## Review complete", None),), HEAD_AT, False),
        ((), (("OWNER", "## Review complete", BEFORE),), HEAD_AT, False),
        ((("OWNER", "## Review complete", None),), (), HEAD_AT, False),
        (
            (("OWNER", "## Review complete", BEFORE), ("OWNER", "## Review complete", AFTER)),
            (),
            HEAD_AT,
            True,
        ),
        (
            (("OWNER", "## Review complete", BEFORE),),
            (("OWNER", "## Review complete", AFTER),),
            HEAD_AT,
            True,
        ),
        ((("OWNER", "## Review complete", SECOND_AFTER),), (), HEAD_AT, True),
        ((), (("OWNER", "## Review complete", SECOND_AFTER),), HEAD_AT, True),
        ((), (("OWNER", "## Review complete", AFTER, "c-older"),), HEAD_AT, False),
        ((), (("OWNER", "## Review complete", AFTER, None),), HEAD_AT, False),
        ((("NONE", "Thanks", BEFORE), ("OWNER", "## Review complete", AFTER)), (), HEAD_AT, True),
        (
            (
                ("OWNER", "## Review round 1, lenses running", AFTER),
                ("OWNER", "## Review complete", AFTER),
            ),
            (),
            HEAD_AT,
            True,
        ),
        ((("OWNER", "## Review complete", AFTER), ("NONE", "LGTM", AFTER)), (), HEAD_AT, True),
        ((("MEMBER", "## Review complete", AFTER),), (), HEAD_AT, False),
        ((("FIRST_TIMER", "## Review complete", AFTER),), (), HEAD_AT, False),
        ((("FIRST_TIME_CONTRIBUTOR", "## Review complete", AFTER),), (), HEAD_AT, False),
        ((("MANNEQUIN", "## Review complete", AFTER),), (), HEAD_AT, False),
    ],
    ids=[
        "whole-body",
        "crlf",
        "same-second-as-head",
        "trailing-dot",
        "second-line",
        "head-has-no-date",
        "stranger-comment",
        "collaborator-comment",
        "stranger-review",
        "pending-review",
        "review-before-head",
        "comment-with-no-date",
        "second-marker-after-head",
        "review-after-a-stale-comment",
        "comment-one-second-after-head",
        "review-one-second-after-head",
        "review-of-an-older-commit",
        "review-naming-no-commit",
        "stranger-before-the-marker",
        "round-heading-before-the-marker",
        "stranger-after-the-marker",
        "member-comment",
        "first-timer-comment",
        "first-time-contributor-comment",
        "mannequin-comment",
    ],
)
def test_a_review_heading_needs_the_owner_and_a_time_after_the_head(
    comments: tuple, reviews: tuple, committed: str | None, reviewed: bool
) -> None:
    """Protects the rule's edges: who posted, when, and how the line ends.

    A review still pending has no ``submittedAt``, and a head commit GitHub
    gives no ``committedDate`` cannot be compared, so either reads as no
    review rather than as one. GitHub's web editor saves ``\\r\\n``, so the
    first line may end in ``\\r``. One second after the head is enough, so a
    rule that adds slack to the comparison fails here. A submitted review
    names the commit it reviewed, and one started on an older commit reviewed
    code the head no longer holds, so it does not count however late it was
    submitted. Every entry is read, so a marker counts wherever it sits among
    the other comments. Only ``OWNER`` counts, whatever other association
    GitHub gives the author.
    """
    pr = pull(6, closes=(5,), comments=comments, reviews=reviews)
    if committed is not None:
        pr["commits"]["nodes"][0]["commit"]["committedDate"] = committed
    assert _reviewed(pr, review_heading=HEADING) == (reviewed, MARKED if reviewed else UNMARKED)


def test_the_review_words_come_from_the_heading_and_name_no_session() -> None:
    """Protects the card's line from the shared wording under a named heading.

    The words are built from the heading, so a caller naming another one reads
    its own name back, with only its first letter lowered. Without the input a
    card held by a session reads ``review in progress``. Under it there is no
    such wording, because a marker not yet posted reads the same whoever holds
    the card.
    """
    heading = "Ready for Owner"
    held = issue(5, labels=("working:build",))
    marked = pull(
        6,
        closes=(5,),
        comments=(("OWNER", "## Ready for Owner", AFTER),),
        committed=HEAD_AT,
        reviews=(),
    )
    unmarked = pull(7, closes=(5,), committed=HEAD_AT, reviews=())
    board, _ = build(FakeGitHub([held], [marked, unmarked]), review_heading=heading)
    assert [(p["pr"], p["reviewed"], p["review"]) for p in prs_of(board)] == [
        (6, True, "ready for Owner"),
        (7, False, "no Ready for Owner marker since the head commit"),
    ]
    board, _ = build(FakeGitHub([held], [unmarked]))
    assert prs_of(board)[0]["review"] == "review in progress"


def test_a_heading_is_matched_as_written_and_keeps_its_case() -> None:
    """Protects a heading that holds characters a pattern reads specially.

    The heading is matched as text, so its parentheses and dot match only
    themselves, and only its first letter is lowered in the card's words.
    """
    heading = "Review Complete (v2)"
    marked = pull(
        6, closes=(5,), comments=(("OWNER", f"## {heading}", AFTER),), reviews=(), committed=HEAD_AT
    )
    assert _reviewed(marked, review_heading=heading) == (True, "review Complete (v2)")
    near = pull(
        6,
        closes=(5,),
        comments=(("OWNER", "## Review Complete v2", AFTER),),
        reviews=(),
        committed=HEAD_AT,
    )
    assert _reviewed(near, review_heading=heading) == (
        False,
        "no Review Complete (v2) marker since the head commit",
    )


def test_a_review_list_longer_than_a_page_is_read_to_its_end() -> None:
    """Protects a review GitHub listed past the first hundred.

    Under ``review-heading`` the reviews are read like every other nested
    list. Without it they are not read at all, since nothing uses them, so the
    same pull request costs no request for them.
    """
    pr = pull(6, closes=(5,), committed=HEAD_AT, reviews=())
    pr["reviews"] = conn([], more=True, cursor="r1")
    nested = {
        ("P6", "reviews", "r1"): conn(
            [
                {
                    "authorAssociation": "OWNER",
                    "body": "## Review complete",
                    "submittedAt": AFTER,
                    "commit": {"oid": "c6"},
                }
            ]
        )
    }
    gh = FakeGitHub([issue(5)], [pr], nested)
    board, _ = build(gh, review_heading=HEADING)
    assert prs_of(board)[0]["reviewed"] is True
    pages = [q for q in gh.calls if "node(id:$id)" in q]
    assert len(pages) == 1
    assert "reviews: reviews(first:100" in pages[0]
    assert "submittedAt commit{oid}" in pages[0]
    gh = FakeGitHub([issue(5)], [pr], nested)
    board, _ = build(gh)
    assert prs_of(board)[0]["reviewed"] is False
    assert not any("node(id:$id)" in q for q in gh.calls)


# What each input adds to the query, and the input that adds it.
HEADING_FIELDS = ("createdAt", "reviews(first:100)", "submittedAt commit{oid}", "committedDate")
RUN_FIELD = "checkSuite{workflowRun{file{path}}}"


@pytest.mark.parametrize(("heading", "settle"), [(False, False), (True, False), (False, True)])
def test_each_input_selects_only_the_fields_it_reads(heading: bool, settle: bool) -> None:
    """Protects a caller from a field it never asked for, on every page.

    A caller that sets neither input sends the query it sent before either
    existed, so it pays no point for a review it does not read, and a field
    its token cannot resolve cannot stop its board. The first page comes from
    ``pr_fields`` and every later one from ``nested``, so a field added to one
    and not the other reads as missing only on a long list. GitHub returns
    only what a query selects, which the fake does not, so this reads the
    selections themselves, and then the query a run sends.
    """
    fragment = bb.pr_fields(heading, settle)
    table = bb.nested(heading, settle)
    for field in HEADING_FIELDS:
        assert (field in fragment) is heading, field
    assert ("createdAt" in table["comments"][3]) is heading
    assert "submittedAt commit{oid}" in table["reviews"][3]
    assert (RUN_FIELD in fragment) is settle
    assert (RUN_FIELD in table["contexts"][3]) is settle
    # The whole selections, so a field dropped from one or moved to another
    # object fails here rather than only on GitHub.
    assert table["reviews"] == (
        "PullRequest",
        "reviews",
        "",
        "authorAssociation body submittedAt commit{oid}",
    )
    reviews = (
        "reviews(first:100){pageInfo{hasNextPage endCursor} "
        "nodes{authorAssociation body submittedAt commit{oid}}}"
    )
    assert (reviews in fragment) is heading
    head = (
        "commit{oid committedDate statusCheckRollup{id"
        if heading
        else "commit{statusCheckRollup{id"
    )
    assert head in fragment
    assert ("nodes{authorAssociation body createdAt}" in fragment) is heading
    pr = pull(6, closes=(5,), committed=HEAD_AT, reviews=())
    pr["comments"] = conn([], more=True, cursor="k1")
    pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"] = conn(
        [], more=True, cursor="x1"
    )
    pages = {("P6", "comments", "k1"): conn([]), ("R6", "contexts", "x1"): conn([])}
    gh = FakeGitHub([issue(5)], [pr], pages)
    build(gh, review_heading=HEADING if heading else "", settled_rollup="true" if settle else "")
    sent = next(q for q in gh.calls if "pullRequests(states:OPEN" in q)
    assert sent == bb.open_prs_query(fragment)
    comment_page = next(q for q in gh.calls if "comments: comments(" in q)
    check_page = next(q for q in gh.calls if "contexts: contexts(" in q)
    assert ("createdAt" in comment_page) is heading
    assert (RUN_FIELD in check_page) is settle


def test_a_head_with_no_oid_matches_no_review() -> None:
    """Protects the head-commit check from two missing oids reading as equal."""
    pr = pull(6, closes=(5,), committed=HEAD_AT, reviews=(("OWNER", "## Review complete", AFTER),))
    del pr["commits"]["nodes"][0]["commit"]["oid"]
    pr["reviews"]["nodes"][0]["commit"] = None
    assert _reviewed(pr, review_heading=HEADING) == (False, UNMARKED)


@pytest.mark.parametrize(
    "heading",
    ["## Review complete", "#Review complete", "Review\ncomplete", "Review complete\r"],
)
def test_a_review_heading_that_cannot_match_stops_the_run_before_any_read(heading: str) -> None:
    """Protects a caller from a heading that would quietly mark nothing reviewed."""
    gh = FakeGitHub([issue(5)], [pull(6, closes=(5,))])
    with pytest.raises(bb.BoardError, match="review heading"):
        build(gh, review_heading=heading)
    assert gh.calls == []


@pytest.mark.parametrize("value", ["yes", "True", "false", "1", " true", "true "])
def test_a_settled_rollup_other_than_true_or_empty_stops_the_run_before_any_read(
    value: str,
) -> None:
    """Protects a caller whose switch reads as on to them and off to the run."""
    gh = FakeGitHub([issue(5)], [pull(6, closes=(5,))])
    message = f"the settled-rollup input {value!r} is neither empty nor true"
    with pytest.raises(bb.BoardError, match=f"^{re.escape(message)}$"):
        build(gh, settled_rollup=value)
    assert gh.calls == []


def test_the_command_line_passes_the_two_inputs_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects ``review-heading`` and ``settled-rollup`` on their way from the workflow.

    The workflow passes both flags whether or not the caller set them, so an
    empty value is the old rule. A misspelt heading marks nothing reviewed and
    fails no read, so the job summary counts the items it marked. A refused
    value fails the run and puts its reason in the summary.
    """
    pr = pull(
        6,
        closes=(5,),
        comments=(("OWNER", "## Review complete", AFTER),),
        committed=HEAD_AT,
        reviews=(),
        contexts=(
            check("test", "SUCCESS"),
            check("board / build", None, "IN_PROGRESS", workflow=WORKFLOW_PATH),
        ),
    )
    second = pull(7, closes=(8,), committed=HEAD_AT, reviews=())
    fake = FakeGitHub([issue(5), issue(8)], [pr, second])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]

    def items() -> list[dict]:
        return json.loads((out / "board.json").read_text())["prs"]["items"]

    assert bb.main([*argv, f"--review-heading={HEADING}", "--settled-rollup=true"]) == 0
    assert [(p["reviewed"], p["review"]) for p in items()] == [(True, MARKED), (False, UNMARKED)]
    assert items()[0]["rollup"] == [["test", "success"]]
    assert "| Review heading | `## Review complete` on 1 of 2 pull request items |" in (
        summary.read_text()
    )
    summary.unlink()
    assert bb.main([*argv, "--review-heading=", "--settled-rollup="]) == 0
    assert items()[0]["review"] == "review posted"
    assert items()[0]["rollup"] == [["test", "success"], ["board / build", "running"]]
    assert "| Review heading | none named |" in summary.read_text()
    summary.unlink()
    assert bb.main([*argv, "--review-heading=Review compleet"]) == 0
    assert "| Review heading | `## Review compleet` on 0 of 2 pull request items |" in (
        summary.read_text()
    )
    (out / "board.json").unlink()
    summary.unlink()
    assert bb.main([*argv, "--settled-rollup=yes"]) == 1
    assert not (out / "board.json").exists()
    assert (
        "build_board: the settled-rollup input 'yes' is neither empty nor true"
        in summary.read_text()
    )
    summary.unlink()
    assert bb.main([*argv, "--review-heading=## Review complete"]) == 1
    assert "build_board: the review heading '## Review complete' starts with #" in (
        summary.read_text()
    )


# ---- The settled rollup a caller asks for ----


def _rollup_of(contexts: tuple[dict, ...], **inputs: str) -> list[list[str]]:
    pr = pull(6, closes=(5,), contexts=contexts)
    return prs_of(build(FakeGitHub([issue(5)], [pr]), **inputs)[0])[0]["rollup"]


def test_a_settled_rollup_leaves_out_only_the_boards_own_checks() -> None:
    """Protects a reviewed branch from reading as running while the board rebuilds.

    The board's own check runs have carried three names, all from the one
    workflow file, and a caller whose job id is not ``board`` names them
    another way again. So the file decides, and a CI job that happens to be
    called ``board / build`` stays. Only the whole path counts, so a workflow
    whose file name ends in ``board.yml`` or holds the word ``board`` stays. A
    check run from no workflow, such as one an app posts, has no file and stays
    too. Without the input every check stays, in GitHub's order.
    """
    contexts = (
        check("board / build", None, "IN_PROGRESS", workflow=WORKFLOW_PATH),
        check("pages / build", "FAILURE", workflow=WORKFLOW_PATH),
        check("build", "SUCCESS", workflow=WORKFLOW_PATH),
        check("board-build", "SUCCESS", workflow=WORKFLOW_PATH),
        check("board / build", "SUCCESS", workflow=CI_PATH),
        check("rank", "SUCCESS", workflow=".github/workflows/leaderboard.yml"),
        check("reuse", "SUCCESS", workflow=".github/workflows/build-board.yml"),
        check("app check", "SUCCESS"),
        {**check("no run", "SUCCESS"), "checkSuite": {"workflowRun": None}},
        status("board / build", "SUCCESS"),
    )
    assert _rollup_of(contexts, settled_rollup="true") == [
        ["app check", "success"],
        ["board / build", "success"],
        ["board / build", "success"],
        ["no run", "success"],
        ["rank", "success"],
        ["reuse", "success"],
    ]
    assert _rollup_of(contexts) == [
        ["board / build", "running"],
        ["pages / build", "failure"],
        ["build", "success"],
        ["board-build", "success"],
        ["board / build", "success"],
        ["rank", "success"],
        ["reuse", "success"],
        ["app check", "success"],
        ["no run", "success"],
        ["board / build", "success"],
    ]


def test_a_settled_rollup_is_sorted_by_name_then_word() -> None:
    """Protects the rollup from reading differently each time GitHub reorders it."""
    contexts = (
        check("test", "SUCCESS", workflow=CI_PATH),
        check("lint", "SUCCESS", workflow=CI_PATH),
        check("test", "FAILURE", workflow=CI_PATH),
        status("codeql", "SUCCESS"),
    )
    assert _rollup_of(contexts, settled_rollup="true") == [
        ["codeql", "success"],
        ["lint", "success"],
        ["test", "failure"],
        ["test", "success"],
    ]
    assert _rollup_of(contexts) == [
        ["test", "success"],
        ["lint", "success"],
        ["test", "failure"],
        ["codeql", "success"],
    ]


@pytest.mark.parametrize(
    ("state", "settled", "shared"),
    [
        ("SKIPPED", "skipped", "neutral"),
        ("CANCELLED", "neutral", "failure"),
        ("ACTION_REQUIRED", "neutral", "failure"),
        ("SUCCESS", "success", "success"),
        ("NEUTRAL", "neutral", "neutral"),
        ("STALE", "neutral", "neutral"),
        ("FAILURE", "failure", "failure"),
        ("TIMED_OUT", "failure", "failure"),
        ("STARTUP_FAILURE", "failure", "failure"),
    ],
)
def test_a_settled_rollup_remaps_three_states_and_keeps_the_rest(
    state: str, settled: str, shared: str
) -> None:
    """Protects a skipped job from holding a reviewed branch out of the owner's queue.

    A job whose condition kept it from running, such as one that runs only on
    the default branch, read as ``neutral``, which the page reads as neither
    way. Under the input it reads ``skipped``, which the page reads as
    settled, and a cancelled run or one waiting on an action reads as neither
    way rather than as a failure, as l3a0/marketlake's board read them.
    """
    contexts = (check("t", state, workflow=CI_PATH),)
    assert _rollup_of(contexts, settled_rollup="true") == [["t", settled]]
    assert _rollup_of(contexts) == [["t", shared]]


def test_a_status_state_reads_the_same_under_a_settled_rollup() -> None:
    """Protects the status-context states, which the input does not remap."""
    for state, word in (("ERROR", "failure"), ("PENDING", "running"), ("EXPECTED", "running")):
        assert _rollup_of((status("s", state),), settled_rollup="true") == [["s", word]]


REVIEW_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "build_board_generator"


def review_github() -> FakeGitHub:
    """A tracker holding every case the two inputs read differently, for the golden board.

    Comments of every shape the review rules tell apart, stamped and not: a
    marker after the head, one before it, a round heading, a longer heading, an
    indented one, a deeper one, a stranger's, and a submitted review. Checks
    from the board's own workflow under three names, from CI, from a workflow
    whose name only contains ``board``, from no workflow, a status context,
    and skipped, cancelled, waiting and running checks, out of name order. The
    data carries every field the inputs select, as a caller setting them
    would read it.
    """
    owner = "OWNER"
    contexts = (
        check("test", "SUCCESS", workflow=CI_PATH),
        check("board / build", None, "IN_PROGRESS", workflow=WORKFLOW_PATH),
        check("board-deploy", "FAILURE", workflow=WORKFLOW_PATH),
        check("build", "SUCCESS", workflow=WORKFLOW_PATH),
        check("board / build", "SUCCESS", workflow=CI_PATH),
        check("rank", "SUCCESS", workflow=".github/workflows/leaderboard.yml"),
        check("deploy", "SKIPPED", workflow=CI_PATH),
        check("approve", "CANCELLED", workflow=CI_PATH),
        check("gate", "ACTION_REQUIRED", workflow=CI_PATH),
        check("app check", "NEUTRAL"),
        status("codeql", "SUCCESS"),
        status("lint", "PENDING"),
    )
    prs = [
        pull(
            20,
            closes=(10,),
            comments=((owner, "## Review complete\n\nAll lenses ran.", AFTER),),
            contexts=contexts,
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            21,
            closes=(11,),
            comments=((owner, "## Review complete", BEFORE),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            22,
            closes=(12,),
            comments=((owner, "## Review round 1, lenses running", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            23,
            closes=(13,),
            comments=((owner, "## Review completeness check", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            24,
            closes=(14,),
            comments=((owner, "  ## Review complete", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            25,
            closes=(15,),
            comments=((owner, "### Review complete", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(
            26,
            closes=(16,),
            comments=(("NONE", "## Review complete", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(27, closes=(17,), committed=HEAD_AT, reviews=((owner, "## Review complete", AFTER),)),
        pull(
            28,
            closes=(18,),
            comments=((owner, "## Reviewer notes", AFTER),),
            committed=HEAD_AT,
            reviews=(),
        ),
        pull(29, closes=(19,), committed=HEAD_AT, reviews=()),
    ]
    # Pull request 29's comments and checks run past their first page, so the
    # query text recorded for a later page is compared too.
    later = prs[-1]
    later["comments"] = conn([], more=True, cursor="k1")
    later["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"] = conn(
        [], more=True, cursor="x1"
    )
    nested = {
        ("P29", "comments", "k1"): conn(
            [{"authorAssociation": owner, "body": "## Review complete", "createdAt": AFTER}]
        ),
        ("R29", "contexts", "x1"): conn(
            [
                check("board / deploy", "SUCCESS", workflow=WORKFLOW_PATH),
                check("test", "SKIPPED", workflow=CI_PATH),
            ]
        ),
    }
    issues = [issue(n) for n in range(10, 19)] + [issue(19, labels=("working:build",))]
    return FakeGitHub(issues, prs, nested)


class _Fixed(datetime):
    """``datetime`` with ``now`` held at ``NOW``, so a written board's stamp is fixed."""

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206 - the signature datetime.now has
        return NOW


def write_board(module, fake: FakeGitHub, out: Path, monkeypatch, *flags: str) -> bytes:  # noqa: ANN001
    """The bytes ``module.main`` writes to ``board.json`` for ``fake``, at ``NOW``."""
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(module, "GhGraphql", lambda: fake)
    monkeypatch.setattr(module, "datetime", _Fixed)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out / "summary.md"))
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out), *flags]
    assert module.main(argv) == 0
    return (out / "board.json").read_bytes()


def test_a_board_with_no_input_is_the_one_ec53810e_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects every current caller, which sets neither input.

    ``review.json`` is the ``board.json`` that the generator at
    l3a0/repo-template commit ``ec53810e``, the last on ``main`` before either
    input, wrote from ``review_github``. ``review_queries.json`` lists every
    query that run sent. The generator here, run the same way with neither
    input, has to write the same bytes and send the same query text, so a
    caller that never asked pays no point and meets no field its token might
    not read. Rewrite the two files only from the generator on ``main`` before
    either input, never from this one, or the test compares the head with
    itself. ``cf2959a3`` and ``7b86e288`` wrote the same board. Their queries
    differ from ``ec53810e``'s only where ``main`` changed them for every
    caller: ``7b86e288`` added the closing links' repository, and
    ``ec53810e`` added each issue's ``authorAssociation`` and each label's
    ``color``.
    """
    fake = review_github()
    written = write_board(bb, fake, tmp_path, monkeypatch)
    assert written == (REVIEW_GOLDEN / "review.json").read_bytes()
    assert fake.calls == json.loads(
        (REVIEW_GOLDEN / "review_queries.json").read_text(encoding="utf-8")
    )
    fake = review_github()
    empty = write_board(bb, fake, tmp_path, monkeypatch, "--review-heading=", "--settled-rollup=")
    assert empty == written


def test_the_golden_tracker_reads_differently_under_each_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the golden test from data that could not tell the rules apart.

    A golden board passes trivially if its data reads the same under every
    rule. So the same tracker has to read differently under each input.
    """
    plain = json.loads(write_board(bb, review_github(), tmp_path, monkeypatch))
    heading = json.loads(
        write_board(bb, review_github(), tmp_path, monkeypatch, f"--review-heading={HEADING}")
    )
    settled = json.loads(
        write_board(bb, review_github(), tmp_path, monkeypatch, "--settled-rollup=true")
    )

    def reviewed(board: dict) -> list[int]:
        return [p["pr"] for p in board["prs"]["items"] if p["reviewed"]]

    assert reviewed(plain) == [20, 21, 22, 23, 24, 29]
    assert reviewed(heading) == [20, 27, 29]
    assert plain["prs"]["items"][0]["rollup"] != settled["prs"]["items"][0]["rollup"]


# ---- Check states ----


@pytest.mark.parametrize(
    ("context", "word"),
    [
        (check("t", "SUCCESS"), "success"),
        (check("t", "FAILURE"), "failure"),
        (check("t", "TIMED_OUT"), "failure"),
        (check("t", "CANCELLED"), "failure"),
        (check("t", "ACTION_REQUIRED"), "failure"),
        (check("t", "STARTUP_FAILURE"), "failure"),
        (check("t", "NEUTRAL"), "neutral"),
        (check("t", "SKIPPED"), "neutral"),
        (check("t", "STALE"), "neutral"),
        (check("t", None, status="IN_PROGRESS"), "running"),
        (check("t", None, status="QUEUED"), "running"),
        (check("t", "SUCCESS", status="IN_PROGRESS"), "running"),
        (status("t", "SUCCESS"), "success"),
        (status("t", "FAILURE"), "failure"),
        (status("t", "ERROR"), "failure"),
        (status("t", "PENDING"), "running"),
        (status("t", "EXPECTED"), "running"),
    ],
)
def test_every_check_state_maps_to_one_of_the_pages_four_words(context: dict, word: str) -> None:
    """Protects a failing check from reading as green.

    The heads of the last 60 pull requests carried 355 ``SUCCESS``, 1
    ``NEUTRAL`` and 1 ``IN_PROGRESS``, so the common case hides a state passed
    through unmapped.
    """
    unknown: set[str] = set()
    assert bb.check_word(context, unknown) == word
    assert unknown == set()


def test_a_check_state_github_adds_later_is_neither_way_and_reported() -> None:
    gh = FakeGitHub([issue(5)], [pull(6, closes=(5,), contexts=(check("t", "SOMETHING_NEW"),))])
    board, report = build(gh)
    assert prs_of(board)[0]["rollup"] == [["t", "neutral"]]
    assert report["unknown_check_states"] == ["SOMETHING_NEW"]


def test_a_head_with_no_checks_has_an_empty_rollup() -> None:
    """Protects a conflicting pull request, which gets no run at all."""
    pr = pull(6, closes=(5,))
    pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"] = None
    board, _ = build(FakeGitHub([issue(5)], [pr]))
    assert prs_of(board)[0]["rollup"] == []


# ---- Requests and pagination ----


def test_one_run_makes_a_request_per_page_and_no_more() -> None:
    """Protects the request budget a busy hour spends.

    A busy hour can carry over a hundred issue events, and ``GITHUB_TOKEN``
    allows 1,000 REST requests an hour per repository. A generator reading per
    issue would spend more than one request for each open issue. Here 150
    open issues take two pages, 60 open pull requests take two, and 55 merged
    pull requests named by those issues take two batches of 50, so one run
    makes six requests whatever the issues hold.
    """
    issues = [issue(n, mentioned_by=(1000 + n,) if n < 55 else ()) for n in range(150)]
    prs = [pull(2000 + n, closes=(n,)) for n in range(60)]
    prs += [pull(1000 + n, state="MERGED", body=f"Part of #{n}") for n in range(55)]
    gh = FakeGitHub(issues, prs)
    board, _ = build(gh)
    assert len(gh.calls) == 6
    assert len(board["tracker"]["items"]) == 150
    assert len(prs_of(board)) == 115


def test_every_top_level_query_asks_what_it_cost() -> None:
    """Protects the job summary's GraphQL points row.

    ``GhGraphql`` sums the ``rateLimit{cost}`` each answer carries, so a
    top-level query that does not ask for it spends points the summary never
    counts. That covers the three query constants and the batch that reads
    pull requests by number, which the run builds as it goes.
    """
    for query in (bb.ISSUES_QUERY, bb.OPEN_PRS_QUERY, bb.HEAD_QUERY):
        assert "rateLimit{cost}" in query
    gh = FakeGitHub([issue(1, mentioned_by=(7,))], [pull(7, state="MERGED", body="Part of #1")])
    _with(gh, default_branch_head="true")
    top = [q for q in gh.calls if "node(id:$id)" not in q]
    assert len(top) == 4
    assert all("rateLimit{cost}" in q for q in top)


def test_a_nested_list_longer_than_a_page_is_read_to_its_end() -> None:
    """Protects a list GitHub cut at its page size.

    An issue named by more than 100 pull requests, or a pull request with more
    than 100 comments, would otherwise lose the rest silently. Each further
    page is one more request, and each asks for the page after the last one
    read. The comments take three pages, so a read that restarts from the
    first finds no page there and stops.
    """
    first = issue(5)
    first["timelineItems"] = conn([], more=True, cursor="t1")
    pr = pull(6, state="MERGED", body="Part of #5")
    pr["comments"] = conn([], more=True, cursor="k1")
    nested = {
        ("I5", "timelineItems", "t1"): conn(
            [{"source": {"number": 6, "repository": {"nameWithOwner": REPO}}}]
        ),
        ("P6", "comments", "k1"): conn([], more=True, cursor="k2"),
        ("P6", "comments", "k2"): conn([{"authorAssociation": "OWNER", "body": "## Review\n"}]),
    }
    gh = FakeGitHub([first], [pr], nested)
    board, _ = build(gh)
    assert [(p["pr"], p["reviewed"]) for p in prs_of(board)] == [(6, True)]
    assert sum("node(id:$id)" in q for q in gh.calls) == 3


def test_a_count_that_disagrees_with_the_pages_read_stops_the_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Protects the board from a read that disagrees with its count on every read.

    A list GitHub cut short would disagree this way on every read. The list is
    read three times, and each of the first two reads prints one line saying
    what it saw.
    """

    class Shifting(FakeGitHub):
        def __call__(self, query: str, variables: dict) -> dict:
            data = super().__call__(query, variables)
            if "issues(states:OPEN" in query:
                data["repository"]["issues"]["totalCount"] += 1
            return data

    gh = Shifting([issue(1)], [])
    with pytest.raises(bb.BoardError, match="read 1 issues against a total of 2 on 3 reads"):
        build(gh)
    assert sum("issues(states:OPEN" in q for q in gh.calls) == 3
    assert capsys.readouterr().err.count("reading the list again") == 2


def test_a_pull_request_count_that_disagrees_on_every_read_stops_the_run() -> None:
    """Protects the board from a pull request list it cannot trust.

    The pull request list is read by the same loop as the issue list, so a
    read that disagrees with its count on every read stops the run here too,
    rather than publishing the pull requests it did read.
    """

    class Shifting(FakeGitHub):
        def __call__(self, query: str, variables: dict) -> dict:
            data = super().__call__(query, variables)
            if "pullRequests(states:OPEN" in query:
                data["repository"]["pullRequests"]["totalCount"] += 1
            return data

    gh = Shifting([issue(1)], [pull(2000, closes=(1,))])
    with pytest.raises(bb.BoardError, match="read 1 pullRequests against a total of 2 on 3 reads"):
        build(gh)
    assert sum("pullRequests(states:OPEN" in q for q in gh.calls) == 3


def test_an_issue_repeated_beside_the_right_count_of_others_stops_the_run() -> None:
    """Protects the board from a page that repeats an issue.

    GitHub's pages continue after the last issue read, so a close or a filing
    cannot repeat one, and the generator keeps a guard against a page that
    repeats one anyway. Here issues 1 and 2 are two distinct numbers against a
    total of 2, so only the count of entries read, three, catches the repeat.
    A read accepted on its distinct numbers alone would draw issue 2 twice.
    """

    class Padded(FakeGitHub):
        def __call__(self, query: str, variables: dict) -> dict:
            data = super().__call__(query, variables)
            if "issues(states:OPEN" in query:
                data["repository"]["issues"]["nodes"] = [issue(1), issue(2), issue(2)]
            return data

    with pytest.raises(bb.BoardError, match="read 3 issues against a total of 2 on 3 reads"):
        build(Padded([issue(1), issue(2)], []))


def test_an_issue_read_twice_stops_the_run() -> None:
    """Protects the count from a page that repeats an issue another dropped."""

    class Repeating(FakeGitHub):
        def __call__(self, query: str, variables: dict) -> dict:
            data = super().__call__(query, variables)
            if "issues(states:OPEN" in query:
                data["repository"]["issues"]["nodes"] = [issue(1), issue(1)]
            return data

    gh = Repeating([issue(1), issue(2)], [])
    with pytest.raises(bb.BoardError, match="read 2 issues against a total of 2 on 3 reads"):
        build(gh)
    assert sum("issues(states:OPEN" in q for q in gh.calls) == 3


class Growing(FakeGitHub):
    """Opens one more issue or pull request partway through the first read.

    The entry lands between the first and second page of the list's first
    read, the way an issue filed while the run reads does. ``reads`` counts
    each time the list is asked for from its first page.
    """

    def __init__(self, issues: list[dict], prs: list[dict], field: str, extra: dict):
        super().__init__(issues, prs)
        self.field = field
        self.extra: dict | None = extra
        self.reads = 0

    def __call__(self, query: str, variables: dict) -> dict:
        if f"{self.field}(states:OPEN" in query:
            if variables.get("after") is None:
                self.reads += 1
            elif self.extra is not None:
                if self.field == "issues":
                    self.issues.append(self.extra)
                else:
                    self.prs[self.extra["number"]] = self.extra
                self.extra = None
        return super().__call__(query, variables)


def test_an_issue_filed_while_the_list_is_read_is_read_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Protects the board from an issue filed between two pages of one read.

    A run reading 119 issues against a total of 118 failed before reads were
    repeated. The first read here disagrees with its own count, so the whole list is
    read again from its first page, and the second read holds every issue,
    the new one included.
    """
    gh = Growing([issue(n) for n in range(101)], [], "issues", issue(101))
    board, _ = build(gh)
    assert [c["n"] for c in board["tracker"]["items"]] == list(range(102))
    assert gh.reads == 2
    assert (
        "build_board: read 102 issues against a total of 101, reading the list again (read 2 of 3)"
    ) in capsys.readouterr().err


def test_a_pull_request_opened_while_the_list_is_read_is_read_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Protects the open pull request list, which pages the same way."""
    prs = [pull(2000 + n, closes=(1,)) for n in range(51)]
    gh = Growing([issue(1)], prs, "pullRequests", pull(2051, closes=(1,)))
    board, _ = build(gh)
    assert [p["pr"] for p in prs_of(board)] == list(range(2000, 2052))
    assert gh.reads == 2
    assert (
        "build_board: read 52 pullRequests against a total of 51, "
        "reading the list again (read 2 of 3)"
    ) in capsys.readouterr().err


def test_an_issue_closed_after_its_page_was_read_is_left_off_the_board() -> None:
    """Protects the board from carrying an entry only the first read held.

    Issue 50 is closed after the first page of the first read, and issue 101
    is filed before its second page. Pages continue after the last issue read,
    the way GitHub's cursors do, so the close moves nothing onto or off the
    second page. The first read holds issue 50 and 102 issues against a total
    of 101, and the second read holds the 101 issues still open. The board
    is the second read exactly, without issue 50.
    """

    class ClosedAndFiled(FakeGitHub):
        def __init__(self, issues: list[dict]):
            super().__init__(issues, [])
            self.changed = False

        def _page(self, nodes: list[dict], size: int, after: str | None) -> dict:
            rest = [n for n in nodes if after is None or n["number"] > int(after)]
            chunk = rest[:size]
            return {
                "totalCount": len(nodes),
                "nodes": chunk,
                "pageInfo": {
                    "hasNextPage": len(rest) > size,
                    "endCursor": str(chunk[-1]["number"]) if chunk else after,
                },
            }

        def __call__(self, query: str, variables: dict) -> dict:
            if "issues(states:OPEN" in query and variables.get("after") and not self.changed:
                self.issues = [i for i in self.issues if i["number"] != 50] + [issue(101)]
                self.changed = True
            return super().__call__(query, variables)

    gh = ClosedAndFiled([issue(n) for n in range(101)])
    board, _ = build(gh)
    assert [c["n"] for c in board["tracker"]["items"]] == [n for n in range(102) if n != 50]
    assert sum("issues(states:OPEN" in q for q in gh.calls) == 4


def test_a_variable_with_no_value_is_left_out_of_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protects the first page of every list, which asks for no cursor.

    GraphQL reads a variable left out as null. Sent as text, it would arrive
    as the cursor "None", which GitHub refuses.
    """
    seen: list[list[str]] = []

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess:
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"data": {}}), stderr="")

    monkeypatch.setattr(bb.subprocess, "run", run)
    bb.GhGraphql()("query { viewer { login } }", {"owner": "octo-org", "first": 3, "after": None})
    args = seen[0]
    assert args[args.index("-f", 4) :] == ["-f", "owner=octo-org", "-F", "first=3"]


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (1, "", "gh api graphql failed"),
        (0, "not json", "returned no JSON"),
        (0, json.dumps({"errors": [{"message": "rate limited"}]}), "GraphQL errors"),
        (0, json.dumps({"data": None}), "returned no data"),
    ],
)
def test_a_failed_read_fails_the_run(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, message: str
) -> None:
    """Protects the last good board from a read that went wrong.

    An error read as an empty list publishes a board with no pull requests,
    which reads as correct. So every failure stops the run, and the last good
    board stays up. A server error is tried again first, and the tests below
    cover that.
    """
    done = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")
    monkeypatch.setattr(bb.subprocess, "run", lambda *a, **k: done)
    with pytest.raises(bb.BoardError, match=message):
        bb.GhGraphql()("query { viewer { login } }", {})


def test_the_cli_exits_non_zero_when_github_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    done = subprocess.CompletedProcess([], 1, stdout="", stderr="gh: HTTP 502")
    monkeypatch.setattr(bb.subprocess, "run", lambda *a, **k: done)
    monkeypatch.setattr(bb.time, "sleep", lambda _: None)
    argv = ["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(tmp_path)]
    assert bb.main(argv) == 1
    assert not (tmp_path / "board.json").exists()


# ---- A server error is tried again ----


class FlakyGh:
    """Stands in for ``subprocess.run`` running ``gh api graphql``.

    Each call fails with the next of ``failures`` as its stderr, the way ``gh``
    prints it, until none are left. After that it answers from ``github``,
    reading the query and variables back out of the arguments the generator
    built.
    """

    def __init__(self, failures: list[str], github: FakeGitHub | None = None):
        self.failures = list(failures)
        self.github = github
        self.calls = 0

    def __call__(self, args: list[str], **_: object) -> subprocess.CompletedProcess:
        self.calls += 1
        if self.failures:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr=self.failures.pop(0))
        query = args[4].removeprefix("query=")
        variables: dict = {}
        for flag, pair in zip(args[5::2], args[6::2], strict=True):
            key, value = pair.split("=", 1)
            variables[key] = int(value) if flag == "-F" else value
        data = self.github(query, variables) if self.github else {}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"data": data}), stderr="")


def test_two_server_errors_then_an_answer_still_build_the_board(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Protects the board from one bad minute at GitHub.

    In one 35-minute stretch, 11 of 16 board runs failed on a single 502 or
    504. A run for a pull request turns its ``build`` check red for a reason
    outside the pull request.
    """
    gh = FlakyGh(["gh: HTTP 502", "gh: HTTP 502"], FakeGitHub([issue(1)], [pull(2, closes=(1,))]))
    waits: list[float] = []
    monkeypatch.setattr(bb.subprocess, "run", gh)
    monkeypatch.setattr(bb.time, "sleep", waits.append)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    out = tmp_path / "site"
    assert bb.main(["build", "--repo", REPO, "--workflow", str(WORKFLOW), "--out", str(out)]) == 0
    board = json.loads((out / "board.json").read_text())
    assert [c["n"] for c in board["tracker"]["items"]] == [1]
    assert [(p["pr"], p["issue"]) for p in board["prs"]["items"]] == [(2, 1)]
    assert waits == [5, 20]
    assert "| GraphQL requests tried again after a server or connection error | 2 |" in (
        summary.read_text()
    )


def test_a_server_error_on_every_attempt_fails_after_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protects the last good board from an outage longer than the waits.

    The retry is bounded, so a GitHub that stays down still stops the run
    rather than holding the job until its timeout.
    """
    gh = FlakyGh(["gh: HTTP 504"] * 4)
    waits: list[float] = []
    monkeypatch.setattr(bb.subprocess, "run", gh)
    monkeypatch.setattr(bb.time, "sleep", waits.append)
    gql = bb.GhGraphql()
    with pytest.raises(bb.BoardError, match="HTTP 504"):
        gql("query { viewer { login } }", {})
    assert gh.calls == gql.requests == 3
    assert gql.retries == 2
    assert waits == [5, 20]


@pytest.mark.parametrize(
    "stderr",
    [
        "gh: Bad credentials (HTTP 401)",
        "gh: HTTP 404",
        "gh: Resource not accessible by integration (HTTP 403)",
        "gh: Field 'nosuch' doesn't exist on type 'User'",
        "gh: Something went wrong (HTTP 5020)",
        "gh: Something went wrong while executing your query. This may be the result of a "
        "timeout, or it could be a GitHub bug.",
    ],
)
def test_an_error_that_would_repeat_fails_at_once(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    """Protects the run from waiting on an answer that will not change.

    A refused token or a query GitHub rejects gets the same answer every time,
    so trying it again only delays the red check. ``gh`` printed the first and
    fourth forms in real runs. The second is a 4xx with no message, printed
    the way ``gh`` prints a bare 504. The fifth guards the match against a
    status that only starts with a 5. The last is GitHub's GraphQL timeout,
    which arrives in the body's ``errors`` list, so ``gh`` prints it with no
    status. It fails at once like any GraphQL error, and none of the failed
    board runs on record when this was written showed it.
    """
    gh = FlakyGh([stderr], FakeGitHub([], []))
    waits: list[float] = []
    monkeypatch.setattr(bb.subprocess, "run", gh)
    monkeypatch.setattr(bb.time, "sleep", waits.append)
    with pytest.raises(bb.BoardError, match="gh api graphql failed"):
        bb.GhGraphql()("query { viewer { login } }", {})
    assert gh.calls == 1
    assert waits == []


@pytest.mark.parametrize(
    "stderr",
    [
        "gh: HTTP 504",
        "gh: HTTP 502",
        "gh: Server Error (HTTP 502)",
        "gh: Server Error (HTTP 502)\nfurther detail",
        "error connecting to api.github.com\n"
        "check your internet connection or https://githubstatus.com",
        'Post "https://api.github.com/graphql": read tcp 10.1.0.4:41234->140.82.112.6:443: '
        "read: connection reset by peer",
    ],
)
def test_a_server_or_connection_error_is_tried_again(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    """Protects a read from each way ``gh`` reports GitHub being unreachable.

    ``gh`` printed the first, second and fifth forms in real runs. The third
    is a 5xx whose body carries a top-level ``message``, which is the only
    case where ``gh`` adds the status after the text. The fourth is the same
    with a line after it, since the match reads each line rather than only the
    last. The last is
    Go's own error for a connection that dropped, which ``gh`` passes through
    unchanged.
    """
    gh = FlakyGh([stderr])
    monkeypatch.setattr(bb.subprocess, "run", gh)
    monkeypatch.setattr(bb.time, "sleep", lambda _: None)
    assert bb.GhGraphql()("query { viewer { login } }", {}) == {}
    assert gh.calls == 2


# ---- The stale threshold ----


def test_the_stale_threshold_is_the_longest_gap_plus_ten_hours_for_a_dropped_run() -> None:
    """Protects the page's stale warning from a schedule GitHub mostly skips.

    The workflow's cron line leaves 30 minutes between runs. GitHub can start
    a scheduled run late or drop it, and documents no bound. One measurement
    found up to 603 minutes between two scheduled runs over 185 hours, and at
    a 60-minute allowance a healthy board would have read as stale 45% of that
    time. So the threshold adds 600 minutes, and no gap
    measured there would have read as a failing Action.
    """
    assert bb.SCHEDULE_DELAY_ALLOWANCE == 600
    assert bb.longest_gap_minutes(WORKFLOW) == 30
    assert bb.stale_after_minutes(bb.longest_gap_minutes(WORKFLOW)) == 630


def test_the_plugin_pin_is_a_full_commit() -> None:
    """Protects the skill these tests read from moving under them.

    GitHub serves the file at a branch name or a short sha too, and either can
    come to name other text later. Only a full commit sha always names the
    same file.
    """
    assert re.fullmatch(r"[0-9a-f]{40}", PLUGIN_COMMIT)


def test_the_skill_states_every_marker_the_generator_reads() -> None:
    """Protects a session from setting a line or a label the board ignores.

    The skill tells a session what to write, and the generator decides what
    counts. Each line the generator matches has to match an example the skill
    writes in a code span, and each label it reads has to appear there by name,
    so renaming one in the generator fails here until the skill says the same.
    The data label is the caller's, so the skill names the input and the label
    its example passes.
    """
    spans = [
        s.replace("#N", "#1").replace("pass N", "pass 1")
        for s in re.findall(r"`([^`\n]+)`", _skill())
    ]
    markers = (bb.VERDICT, bb.ORDER, bb.AFTER, bb.REVIEW, bb.PART_OF, bb.BAND, bb.PASS_HEADING)
    for marker in markers:
        assert any(marker.search(s) for s in spans), marker.pattern
    for label, _ in bb.kind_labels(DATA_LABEL):
        assert label in spans, label
    for label in bb.WORKING:
        assert label in spans, label
    assert "data-label" in spans
    assert "milestone-default" in spans


def test_the_skill_quotes_the_allowance_the_script_adds() -> None:
    """Protects the skill's data table from a second copy of the allowance."""
    skill = _skill()
    assert f"a {bb.SCHEDULE_DELAY_ALLOWANCE}-minute allowance" in skill


def test_the_threshold_adds_the_named_allowance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protects the allowance from a second copy of 600 inside the formula."""
    monkeypatch.setattr(bb, "SCHEDULE_DELAY_ALLOWANCE", 7)
    assert bb.stale_after_minutes(30) == 37


def test_the_cli_writes_the_workflows_gap_and_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protects the board from carrying the threshold where the gap belongs.

    ``5,15`` puts runs 10 and 50 minutes apart, so the longest gap differs from
    any even split of the hour, and the threshold differs from the gap.
    """
    fake = FakeGitHub([issue(1)], [])
    fake.requests, fake.retries, fake.cost = 1, 0, 1
    monkeypatch.setattr(bb, "GhGraphql", lambda: fake)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    workflow = tmp_path / "board.yml"
    workflow.write_text('on:\n  schedule:\n    - cron: "5,15 * * * *"\n')
    out = tmp_path / "site"
    assert bb.main(["build", "--repo", REPO, "--workflow", str(workflow), "--out", str(out)]) == 0
    state = json.loads((out / "board.json").read_text())["state"]
    assert state["longestGapMinutes"] == 50
    assert state["staleAfterMinutes"] == 650


@pytest.mark.parametrize(
    ("cron", "gap", "stale_after"),
    [("*/15 * * * *", 15, 615), ("0 * * * *", 60, 660), ("5,15 * * * *", 50, 650)],
)
def test_the_threshold_follows_the_schedule(
    tmp_path: Path, cron: str, gap: int, stale_after: int
) -> None:
    workflow = tmp_path / "board.yml"
    workflow.write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n')
    assert bb.longest_gap_minutes(workflow) == gap
    assert bb.stale_after_minutes(gap) == stale_after


@pytest.mark.parametrize(
    "lines",
    [
        '    - cron: "0 */2 * * *"\n',
        '    - cron: "60 * * * *"\n',
        '    - cron: "0 * * * 1"\n',
        '    - cron: "7 * * * *"\n    - cron: "37 * * * *"\n',
        "",
    ],
)
def test_a_schedule_it_cannot_read_stops_the_run(tmp_path: Path, lines: str) -> None:
    workflow = tmp_path / "board.yml"
    workflow.write_text("on:\n  schedule:\n" + lines)
    with pytest.raises(bb.BoardError):
        bb.longest_gap_minutes(workflow)


# ---- The page, on what the generator wrote ----


def every_case() -> FakeGitHub:
    """A tracker holding every case above at once."""
    return FakeGitHub(
        [
            issue(10, mentioned_by=(20,)),
            issue(11, milestone=None, labels=()),
            issue(12),
            issue(13, labels=("working:build",)),
            issue(
                14,
                labels=("band:1", "decision"),
                body="Board order: 2.5\nBoard after: #15\n",
                blocked_by=((10, "OPEN"),),
            ),
            issue(
                15, labels=("band:1",), comments=(("OWNER", "Board verdict: build after 3 passes"),)
            ),
            issue(16, sub_issues=2),
        ],
        [
            pull(20, state="MERGED", body="Part of #10"),
            pull(21, closes=(11, 12), comments=(("OWNER", "## Review\n"),)),
            pull(22, body="Bumps a dependency."),
            pull(23, closes=(13,), contexts=(check("test", "TIMED_OUT"),)),
        ],
    )


def test_the_page_draws_what_the_generator_writes(tmp_path: Path) -> None:
    """Protects the join between the two halves.

    A field the generator leaves out, or writes in a shape the page refuses,
    blanks the board, and neither half's own tests would notice. So the page
    runs on the generator's output, built from a tracker holding every case
    above at once.
    """
    board, _ = build(every_case())
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids, _ = run_fetch_page(tmp_path, [served(board)])
    assert text(ids, "strip").startswith("7 open issues")
    assert ids["source"]["hidden"]
    # Issue 15's plan is finished and nothing blocks it, so it waits in flight
    # for a builder. Issue 14 is the one ranked card left for the build order.
    assert cards(ids, "flow") == {11, 12, 13, 15}
    assert "1 check failing" in text(ids, "flow")
    assert "review in progress" in text(ids, "flow")
    assert "plan complete, 3 passes" in text(ids, "flow")
    assert cards(ids, "board") == {14}


def test_the_page_draws_the_three_lines_the_generator_writes(tmp_path: Path) -> None:
    """Protects the join for the subtitle, the note and the default branch's head.

    The generator writes the note as pieces and the head as seven characters,
    and the page draws each only in the shape it checks for, so a change to
    either half's shape would leave the line off the page with no test failing.
    """
    board, _ = bb.build(
        every_case(),
        REPO,
        30,
        NOW,
        subtitle="the order of work on the lake",
        note=f"Read [the design doc]({LINK_A}) first.",
        default_branch_head="true",
    )
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids, _ = run_fetch_page(tmp_path, [served(board)])
    assert ids["sub"]["html"] == "the order of work on the lake"
    assert not ids["repnote"]["hidden"]
    assert ids["repnote"]["html"] == (
        f'Read <a href="{LINK_A}" target="_blank" rel="noopener">the design doc</a> first.'
    )
    assert text(ids, "foot").startswith("Built from GitHub against the default branch at 0a1b2c3 ")
    assert '<span class="mono">0a1b2c3</span>' in ids["foot"]["html"]


@pytest.mark.parametrize("listed", ["as written", "reversed"])
def test_an_order_of_zero_sorts_first_and_no_order_sorts_at_fifty(
    tmp_path: Path, listed: str
) -> None:
    """Protects a card at ``Board order: 0`` from sorting as if it had none.

    The generator writes ``order: 0`` for that line, and the page gives a card
    with no order 50. A fallback that treats 0 as missing puts the card at 0
    behind the one with no order. Four cards in one band, at 51, with no order,
    at 0 and at 49, also fix the default at exactly 50. The cards at 49 and 51
    sit one either side of it, so a default of 49 or 51 ties the card with no
    order to a neighbour, and the issue-number tiebreak then puts that pair the
    wrong way round. The rank chip and the column both read the same sorted
    list, so both are checked.

    The page also draws the list reversed. Which pairs a sort compares, and
    which card of a pair comes first, follows the order it is given, and the
    two engines the page runs under sort differently. On three cards at 60,
    none and 0, a fallback written wrongly on one side of the comparison sorted
    the generator's order correctly under JavaScriptCore and only the reversed
    one wrongly.
    """
    gh = FakeGitHub(
        [
            issue(1, labels=("band:1",), body="Board order: 51\n"),
            issue(2, labels=("band:1",)),
            issue(3, labels=("band:1",), body="Board order: 0\n"),
            issue(4, labels=("band:1",), body="Board order: 49\n"),
        ],
        [],
    )
    board, _ = build(gh)
    assert [(it["issue"], it.get("order")) for it in board["next"]["items"]] == [
        (1, 51),
        (2, None),
        (3, 0),
        (4, 49),
    ]
    if listed == "reversed":
        board["next"]["items"].reverse()
    chips, raw = _rank_chips(tmp_path, board)
    assert chips == {3: 1, 4: 2, 2: 3, 1: 4}
    column = raw.split('<div class="col k0')[1].split('<div class="col k')[0]
    assert [int(n) for n in re.findall(r'data-n="(\d+)"', column)] == [3, 4, 2, 1]


def test_the_build_order_sorts_by_band_then_order_then_readiness_then_number(
    tmp_path: Path,
) -> None:
    """Protects the comparator's four terms and the order it applies them in.

    Each pair of cards here differs on one term and ties on every term before
    it, so dropping, reversing or moving any term changes the chips.

    1. #1 in band 2 with no order sorts after #2 in band 1 at order 60, so band
       comes before order and a lower band lands first.
    2. #3, #4 and #5 share order 10, ahead of #6 and #7 at the default of 50
       and #2 at 60, so order comes before readiness.
    3. #5 carries a decision, so it is ready to decide rather than to plan, and
       sorts ahead of #3 and #4 at the same order.
    4. #3 sorts ahead of #4, and #6 ahead of #7, on the issue number alone.
    """
    gh = FakeGitHub(
        [
            issue(1, labels=("band:2",)),
            issue(2, labels=("band:1", "decision"), body="Board order: 60\n"),
            issue(3, labels=("band:1",), body="Board order: 10\n"),
            issue(4, labels=("band:1",), body="Board order: 10\n"),
            issue(5, labels=("band:1", "decision"), body="Board order: 10\n"),
            issue(6, labels=("band:1",)),
            issue(7, labels=("band:1",)),
        ],
        [],
    )
    board, _ = build(gh)
    chips, _ = _rank_chips(tmp_path, board)
    assert sorted(chips, key=chips.get) == [5, 3, 4, 6, 7, 2, 1]


def _rank_chips(tmp_path: Path, board: dict) -> tuple[dict[int, int], str]:
    """Each ranked card's priority chip as the page draws it, and the build order's HTML."""
    board["state"]["updatedAt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids, _ = run_fetch_page(tmp_path, [served(board)])
    raw = ids["board"]["html"]
    chip = r'data-n="(\d+)".*?<span class="rk" title="priority order">(\d+)</span>'
    return {int(n): int(rank) for n, rank in re.findall(chip, raw, re.S)}, raw


def test_a_board_with_no_open_issues_draws_nothing(tmp_path: Path) -> None:
    """Protects the page's refusal of an empty tracker, which it keeps."""
    board, _ = build(FakeGitHub([], []))
    ids, _ = run_fetch_page(tmp_path, [served(board)])
    assert "tracker section is missing fields" in text(ids, "source")
    assert_no_board_data(ids)


# ---- The workflows ----
#
# The caller, board.yml, holds the triggers, the permissions it grants and the
# concurrency group. The reusable workflow, build-board.yml, holds the build
# and deploy jobs that a seeded repository runs at the ref it pins.


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _called() -> str:
    return CALLED.read_text(encoding="utf-8")


def _declared(called: str) -> dict[str, str]:
    """Each input a text of the reusable workflow declares, in order, with its block."""
    inputs = called.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
    blocks = re.split(r"^      ([\w-]+):\n", inputs, flags=re.M)[1:]
    return dict(zip(blocks[::2], blocks[1::2], strict=True))


def _inputs() -> dict[str, str]:
    """Each input the reusable workflow declares, in order, with its block."""
    return _declared(_called())


def _scopes(block: str) -> dict[str, str]:
    """The scopes one ``permissions:`` block grants, at any indent."""
    lines = block.split("permissions:\n", 1)[1].splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    scopes = {}
    for line in lines:
        if len(line) - len(line.lstrip()) != indent or ":" not in line:
            break
        key, value = line.strip().split(":", 1)
        scopes[key] = value.strip()
    return scopes


def test_the_schedule_stays_off_the_hour() -> None:
    """Protects the scheduled runs from the top of the hour.

    The workflow's comment keeps the schedule off minute 0, because GitHub's
    documentation names the start of every hour as its busiest time. The test
    reads the minutes rather than pinning the line, so the minutes can move
    again without editing it.
    """
    crons = re.findall(r"""^\s*-\s*cron:\s*"([^"]+)"\s*$""", _workflow(), re.M)
    assert len(crons) == 1
    minute = crons[0].split()[0]
    assert not minute.startswith("*"), minute
    assert 0 not in {int(m) for m in minute.split(",")}


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        (WORKFLOW, set()),
        (
            CALLED,
            {
                "github.token",
                "inputs.title",
                "inputs.icon",
                "inputs.data-label",
                "inputs.subtitle",
                "inputs.note",
                "inputs.default-branch-head",
                "inputs.label-colors",
                "inputs.sort-labels",
                "inputs.review-heading",
                "inputs.settled-rollup",
                "inputs.milestone-default",
                "inputs.owner-body-lines",
                "inputs.ranking",
                "job.workflow_repository",
                "job.workflow_sha",
                "steps.board.outputs.updated_at",
                "steps.deployment.outputs.page_url",
                "needs.build.outputs.updated_at",
            },
        ),
    ],
    ids=["caller", "called"],
)
def test_no_step_reads_the_event_payload(path: Path, allowed: set[str]) -> None:
    """Protects the run steps from an issue title written as shell.

    Anyone can file an issue on a public repository, and CodeQL rates an event
    field expanded into a step as critical, which the ruleset refuses to merge.
    Fields such as ``github.head_ref`` carry a stranger's text without naming
    the event, so each workflow may use only the expressions listed here, none
    of which a stranger writes. Every ``inputs.`` field is written by the
    caller's own file. Each reaches the shell only through an environment
    variable, and the icon also names a file for the caller's checkout, which
    is an action's input rather than shell.
    """
    used = set(re.findall(r"\$\{\{\s*([^}]*?)\s*\}\}", path.read_text(encoding="utf-8")))
    assert used == allowed
    assert "TITLE: ${{ inputs.title }}" in _called()
    assert '--title="$TITLE"' in _called()
    data = re.findall(r"^(.*)\$\{\{\s*inputs\.data-label\s*\}\}(.*)$", _called(), re.M)
    assert [(before.strip(), after) for before, after in data] == [("DATA_LABEL:", "")]
    assert '--data-label="$DATA_LABEL"' in _called()
    for key, var in (
        ("subtitle", "SUBTITLE"),
        ("note", "NOTE"),
        ("default-branch-head", "DEFAULT_BRANCH_HEAD"),
        ("label-colors", "LABEL_COLORS"),
        ("sort-labels", "SORT_LABELS"),
        ("review-heading", "REVIEW_HEADING"),
        ("settled-rollup", "SETTLED_ROLLUP"),
        ("owner-body-lines", "OWNER_BODY_LINES"),
    ):
        uses = re.findall(rf"^(.*)\$\{{\{{\s*inputs\.{key}\s*\}}\}}(.*)$", _called(), re.M)
        assert [(before.strip(), after) for before, after in uses] == [(f"{var}:", "")]
        assert f'--{key}="${var}"' in _called()
    default = re.findall(r"^(.*)\$\{\{\s*inputs\.milestone-default\s*\}\}(.*)$", _called(), re.M)
    assert [(before.strip(), after) for before, after in default] == [("MILESTONE_DEFAULT:", "")]
    assert '--milestone-default="$MILESTONE_DEFAULT"' in _called()
    ranking = re.findall(r"^(.*)\$\{\{\s*inputs\.ranking\s*\}\}(.*)$", _called(), re.M)
    assert [(before.strip(), after) for before, after in ranking] == [("RANKING:", "")]
    assert '--ranking="$RANKING"' in _called()
    icon = re.findall(r"^(.*)\$\{\{\s*inputs\.icon\s*\}\}(.*)$", _called(), re.M)
    assert [(before.strip(), after) for before, after in icon] == [("", ""), ("ICON:", "")]


def test_the_called_workflow_checks_out_its_own_commit() -> None:
    """Protects a seeded repository's pin from reaching only half the board.

    A called workflow learns its own source from ``job.workflow_repository``
    and ``job.workflow_sha``. GitHub's contexts reference says the second is
    "The commit SHA of the workflow file that defines the current job", and
    its example checks out a reusable workflow's own source with these two.
    ``github.workflow_sha`` would name the caller's commit instead, so a
    repository pinned to an old commit would run today's generator and page.
    Both jobs check out the template that way, and nothing else.
    """
    flow = _called()
    template = (
        "path: template\n"
        "          repository: ${{ job.workflow_repository }}\n"
        "          ref: ${{ job.workflow_sha }}\n"
    )
    build_job, deploy_job = flow.split("\n  deploy:\n", 1)
    assert template in build_job
    assert template in deploy_job
    assert not re.search(r"\$\{\{\s*github\.workflow", flow)
    assert "python3 template/scripts/build_board.py build" in build_job
    assert "python3 template/scripts/build_board.py measure" in deploy_job


def test_every_input_is_an_optional_string_that_defaults_to_empty() -> None:
    """Protects every caller that sets no input.

    The template's own board passes no input, and a seeded repository sets
    only what it needs. A required input, or a default naming a file or a
    label, would fail or change every such run. An empty title gives
    ``<name> build board``, an empty icon serves the template's, an empty
    data label reads no ``data`` kind, an empty subtitle, note,
    default-branch-head, label-colors or sort-labels leaves the board as it
    was, an empty review heading keeps the shared review rule, and an empty
    settled rollup keeps the rollup as GitHub lists it. An empty
    ``owner-body-lines`` reads body lines from anyone's issue, as every run
    did before it. An empty milestone default draws no selector, and an empty
    ``ranking`` keeps the band rule. A switch such as ``settled-rollup`` is a
    string taking empty or ``true``. The README and the l3a0 plugin's
    update-build-board skill name the inputs by the keys declared here. The
    README quotes ``"true"``, because a bare ``true`` in YAML is a boolean and
    the inputs are strings. The plugin's ``with:`` form of every input is
    read by ``test_the_plugin_names_every_input_in_its_with_form``.
    """
    declared = _inputs()
    assert list(declared) == [
        "title",
        "icon",
        "data-label",
        "subtitle",
        "note",
        "default-branch-head",
        "label-colors",
        "sort-labels",
        "review-heading",
        "settled-rollup",
        "milestone-default",
        "owner-body-lines",
        "ranking",
    ]
    for name, block in declared.items():
        # Anchored to the line's start, so a ``type`` indented into the folded
        # description above it, which YAML reads as description text, fails.
        # Exactly once each, so a second ``type`` or ``default`` line, which a
        # merge that keeps both sides can leave, fails too.
        assert re.findall(r"^ {8}type:.*$", block, re.M) == ["        type: string"], name
        assert re.findall(r"^ {8}default:.*$", block, re.M) == ['        default: ""'], name
        assert "required" not in block
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "    with:\n      icon: .github/board/favicon.ico\n" in readme
    assert f"    with:\n      data-label: {DATA_LABEL}\n" in readme
    assert "    with:\n      subtitle: " in readme
    assert "\n      note: >-\n" in readme
    assert '\n      default-branch-head: "true"\n' in readme
    assert '    with:\n      label-colors: "true"\n' in readme
    assert '    with:\n      sort-labels: "true"\n' in readme
    assert "    with:\n      review-heading: Review complete\n" in readme
    assert '    with:\n      settled-rollup: "true"\n' in readme
    assert "    with:\n      milestone-default: MVP <n>\n" in readme
    assert '    with:\n      owner-body-lines: "true"\n' in readme
    assert "    with:\n      ranking: order\n" in readme
    page = _plugin("page.md")
    assert "`with: icon: <path>`" in page
    assert f"`with: data-label: {DATA_LABEL}`" in _skill()


def test_nothing_checks_out_a_pull_requests_code() -> None:
    """Protects the write token ``pull_request_target`` runs with.

    The caller's checkout takes the default ref, and only its own workflow
    file and the icon its ``icon`` input names. The template's checkouts take
    the workflow's own commit. No other ``ref:`` appears, so no step can check
    out a pull request's head.
    """
    flow = _called()
    assert flow.count("uses: actions/checkout@") == 3
    assert re.findall(r"^\s+ref:.*$", flow, re.M) == ["          ref: ${{ job.workflow_sha }}"] * 2
    assert flow.count("persist-credentials: false") == 3
    caller = flow.split("path: caller\n", 1)[1].split("\n      - ", 1)[0]
    assert (
        "sparse-checkout: |\n"
        "            .github/workflows/board.yml\n"
        "            ${{ inputs.icon }}\n"
    ) in caller
    # Anchored, so the key indented into the sparse list above it, which YAML
    # reads as a third path, fails here.
    assert re.search(r"^ {10}sparse-checkout-cone-mode: false$", caller, re.M)
    assert "repository:" not in caller
    assert "actions/checkout" not in _workflow()


def test_every_action_the_called_workflow_runs_is_pinned_to_a_commit() -> None:
    """Protects the deploy job's scopes from a tag moved to another commit.

    The deploy job holds ``pages: write`` and ``id-token: write``, and a tag can
    be moved, so an action named by tag runs whatever commit its owner points
    the tag at next. A full commit SHA cannot be moved. Each pin carries its
    release in a trailing comment, which Dependabot rewrites with the SHA.

    Every line that is not a comment and names the key ``uses:`` must hold one
    pin, so a step written in a form the pattern does not expect, such as a
    flow mapping, fails rather than going unread. The test checks the form of
    each pin. That each SHA is the commit its release names was checked
    against the action's own tags when the pins were written.
    """
    lines = [
        line
        for line in _called().splitlines()
        if re.search(r"\buses:", line) and not line.lstrip().startswith("#")
    ]
    assert lines
    for line in lines:
        assert re.fullmatch(
            r"\s+(?:- )?uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+", line
        ), line


def test_the_triggers_are_the_ones_that_can_deploy() -> None:
    """Protects the deploy, which only the default branch may make.

    ``pull_request`` and ``pull_request_review`` run on a merge ref, which the
    github-pages environment refuses. ``pull_request_target`` needs ``closed``
    and ``edited`` listed, or a merged ``Part of`` pull request and a corrected
    closing link wait for the cron run. It admits only pull requests into
    ``main``, because GitHub registers a closing link only on a pull request
    into the default branch. The reusable
    workflow takes ``workflow_call`` and nothing else, so it never runs on its
    own.
    """
    flow = _workflow()
    on = flow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    triggers = re.findall(r"^  (\w+):", on, re.M)
    assert triggers == [
        "issues",
        "issue_comment",
        "pull_request_target",
        "workflow_run",
        "schedule",
        "workflow_dispatch",
    ]
    target = on.split("  pull_request_target:\n", 1)[1].split("\n  # ", 1)[0]
    assert "branches: [main]" in target
    assert "types: [opened, synchronize, reopened, closed, edited]" in target
    assert "workflows: [CI]" in on
    assert "types: [completed]" in on
    called_on = _called().split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert re.findall(r"^  (\w+):", called_on, re.M) == ["workflow_call"]


def test_the_caller_names_the_ci_workflow_by_its_name() -> None:
    """Protects the trigger that fires when the checks settle.

    ``workflow_run`` matches a workflow by its ``name:``, so renaming CI
    without the caller would silently stop the run that brings check results
    to the board.
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^name: CI$", ci, re.M)


CALLER_USES = re.compile(
    r"^    uses: l3a0/repo-template/\.github/workflows/build-board\.yml@(\S+)$", re.M
)


def test_the_caller_calls_the_shared_workflow_by_ref() -> None:
    """Protects the line a seeded repository changes and nothing else.

    A seeded repository copies the caller and changes this ref, to a full
    commit SHA of the template, adding only a ``with:`` block for the inputs
    it sets. The template calls ``main``, so its own board
    runs the shared path through the same remote form a seeded repository
    uses. The update-build-board skill reads the ref with the same pattern.
    """
    refs = CALLER_USES.findall(_workflow())
    assert refs == ["main"]
    skill = _skill()
    sed = re.search(r"PIN=\"\$\(sed -nE 's#(.+?)#\\1#p' \.github/workflows/board\.yml\)\"", skill)
    assert sed, "the skill reads no pin from the caller"
    pattern = sed.group(1).replace("([^ ]+)", "(\\S+)").replace("^ *", "^ *")
    assert re.search(pattern, _workflow(), re.M).group(1) == "main"
    pinned = _workflow().replace("@main", "@" + "0123abcd" * 5)
    assert re.search(pattern, pinned, re.M).group(1) == "0123abcd" * 5


DISPATCH = 'gh workflow run board.yml --repo "$REPO"'

# What the generator reads that no trigger above covers, each with the words a
# moment in the skill uses for the change a session makes to it.
NO_RUN_READS = {"blockedBy": '"blocked by" link', "subIssuesSummary": "sub-issue"}

# Any wording of either change, so a moment reworded away from the words above
# still has to name the dispatch.
NO_RUN_WORDING = re.compile(r"blocked[- ]by|dependenc|sub-?issue|child issue", re.I)


def _moments() -> list[str]:
    """The numbered moments under the skill's "What a session sets, and when"."""
    skill = _skill()
    section = skill.split("\n## What a session sets, and when\n", 1)[1].split("\n## ", 1)[0]
    listed = section.split("\nNothing else needs setting.", 1)[0]
    return re.split(r"\n(?=\d+\. \*\*)", listed)[1:]


def test_a_change_that_starts_no_run_names_the_dispatch() -> None:
    """Protects the board from a link or sub-issue it would show hours late.

    A "blocked by" link and a sub-issue start no run, and the schedule that is
    their backstop fires in a fraction of its slots. So the session making
    such a change dispatches the board itself. Every moment in the skill that
    sets one names the dispatch, each of the two changes has a moment that
    names it, and the command names the caller, which keeps its dispatch
    trigger.
    """
    assert set(NO_RUN_READS) <= set(
        re.findall(r"\b(blockedBy|subIssuesSummary)\b", bb.issues_query(True))
    )
    moments = _moments()
    for words in NO_RUN_READS.values():
        assert any(words in m for m in moments), f"no moment names a {words}"
    for moment in moments:
        if NO_RUN_WORDING.search(moment):
            assert "dispatch the board" in moment.lower(), moment.split("\n", 1)[0]
    assert f"\n{DISPATCH}\n" in _skill()
    assert f"{DISPATCH} --ref" not in _plugin("SKILL.md")
    assert re.search(r"^  workflow_dispatch:\s*$", _workflow(), re.M)


def test_each_job_declares_only_the_scopes_it_uses() -> None:
    """Protects the build from a starved token and the deploy from a broad one.

    Declaring any scope sets every unlisted one to none, so the build job
    lists each scope the generator reads. A called workflow can only narrow
    what its caller grants, so the caller's job grants the union of the two
    and nothing more, and both workflows grant nothing at the top. The build
    job reads ``actions`` because a check run's workflow run, whose file tells
    the board's own checks apart, belongs to Actions. The query asks for it
    whatever the inputs, so the scope is granted whatever they are.
    """
    flow = _called()
    assert "\npermissions: {}\n" in flow
    assert "\npermissions: {}\n" in _workflow()
    jobs = flow.split("\njobs:\n", 1)[1]
    build_job, deploy_job = jobs.split("\n  deploy:\n", 1)
    build_scopes = {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
        "checks": "read",
        "statuses": "read",
        "actions": "read",
    }
    deploy_scopes = {
        "pages": "write",
        "id-token": "write",
        "contents": "read",
        "actions": "read",
    }
    assert _scopes(build_job) == build_scopes
    assert _scopes(deploy_job) == deploy_scopes
    assert "name: github-pages" in deploy_job
    caller_job = _workflow().split("\njobs:\n", 1)[1]
    assert _scopes(caller_job) == {**build_scopes, **deploy_scopes}


def test_runs_deploy_one_at_a_time_and_none_is_cancelled() -> None:
    """Protects a newer board from an older run deploying over it.

    The group sits in the caller, so every run shares it whichever event
    started it, and the reusable workflow declares no group of its own.
    """
    assert "concurrency:\n  group: pages\n  cancel-in-progress: false\n" in _workflow()
    assert "concurrency:" not in _called()


def test_every_successful_build_deploys() -> None:
    """Protects the stale warning from a skipped deploy.

    A deploy skipped because the board matched the last one would freeze its
    stamp, and the page would then call a current board stale. So the deploy
    job waits on the build and carries no condition of its own.
    """
    deploy = _called().split("\n  deploy:\n", 1)[1]
    assert "    needs: build\n" in deploy
    assert not re.search(r"^\s+if:", _called(), re.M)
    assert not re.search(r"^\s+if:", _workflow(), re.M)


def test_the_measure_step_holds_the_pages_group_for_a_minute_at_most() -> None:
    """Protects the next run from waiting on a measurement.

    The whole run holds the ``pages`` concurrency group, so the next board
    waits for the measure step to finish polling.
    """
    measure = _called().split("- name: Measure delivery", 1)[1]
    assert "--wait 60" in measure
    assert "timeout=10" in SCRIPT.read_text(encoding="utf-8")


def test_the_page_published_is_the_checked_in_one() -> None:
    """Protects the one page every board publishes, and the schedule it reads.

    The generator names the caller's workflow file a second time, as
    ``BOARD_WORKFLOW``, to tell the board's own check runs apart. The file the
    workflow hands it for the schedule has to be that same file, or a settled
    rollup keeps the board's checks it was asked to leave out.
    """
    flow = _called()
    assert "cp template/.claude/skills/update-build-board/board.html _site/index.html" in flow
    assert "--workflow caller/.github/workflows/board.yml" in flow
    assert f"--workflow caller/{bb.BOARD_WORKFLOW}" in flow
    sparse = flow.split("sparse-checkout: |\n", 1)[1]
    assert re.search(rf"^ {{12}}{re.escape(bb.BOARD_WORKFLOW)}$", sparse, re.M)


def _add_the_page(
    tmp_path: Path, icon: str, *, page: bool = True
) -> subprocess.CompletedProcess[str]:
    """Runs the step that adds the page, in a folder laid out as the runner's."""
    step = _called().split("- name: Add the page", 1)[1].split("\n      - ", 1)[0]
    script = step.split("run: |\n", 1)[1]
    skill = tmp_path / "template" / ".claude" / "skills" / "update-build-board"
    skill.mkdir(parents=True)
    if page:
        (skill / "board.html").write_text("page")
    (skill / "favicon.ico").write_bytes(b"template icon")
    (tmp_path / "caller" / ".github" / "board").mkdir(parents=True)
    (tmp_path / "caller" / ".github" / "board" / "favicon.ico").write_bytes(b"caller icon")
    (tmp_path / "caller" / ".github" / "board" / "tab icon.ico").write_bytes(b"spaced icon")
    (tmp_path / "_site").mkdir()
    return subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "ICON": icon},
        capture_output=True,
        text=True,
    )


def test_the_icon_is_published_where_the_page_links_it(tmp_path: Path) -> None:
    """Protects the board's tab from a blank icon.

    The page links its icon by a relative address, so Pages serves it only
    when the step that adds the page puts the icon in the same folder under
    that name. A step that dropped the copy, or a page that renamed the link,
    would leave a browser asking for a file that is not there. The step runs
    here as the runner runs it, under ``bash -e``, with the ``icon`` input
    empty, so the template's icon is the one served.
    """
    href = re.search(r'<link rel="icon" href="([^"]+)"', PAGE.read_text(encoding="utf-8"))
    assert href, "the page links no icon"
    assert href.group(1) == "favicon.ico"
    assert (SKILL_DIR / "favicon.ico").is_file()
    run = _add_the_page(tmp_path, "")
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "_site" / "index.html").read_text() == "page"
    assert (tmp_path / "_site" / "favicon.ico").read_bytes() == b"template icon"


@pytest.mark.parametrize(
    ("icon", "served"),
    [(".github/board/favicon.ico", b"caller icon"), (".github/board/tab icon.ico", b"spaced icon")],
    ids=["plain", "space"],
)
def test_the_callers_icon_takes_the_templates_place(
    tmp_path: Path, icon: str, served: bytes
) -> None:
    """Protects a repository's own tab icon, named by the ``icon`` input.

    One owner's boards share one origin and several are open at once, so a
    repository may give its board its own icon. The caller's file replaces the
    template's, under the name the page links. A path with a space in it is
    one file, which only a quoted ``$ICON`` keeps it.
    """
    run = _add_the_page(tmp_path, icon)
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "_site" / "favicon.ico").read_bytes() == served


def test_a_missing_page_fails_the_run(tmp_path: Path) -> None:
    """Protects the board from deploying an icon with no page beside it."""
    assert _add_the_page(tmp_path, "", page=False).returncode != 0


def test_a_missing_icon_fails_the_run(tmp_path: Path) -> None:
    """Protects the board from deploying with no icon at all.

    A path that names no file would otherwise publish a page linking an icon
    Pages cannot serve, so the step fails and the last board stays up.
    """
    run = _add_the_page(tmp_path, ".github/board/missing.ico")
    assert run.returncode != 0
    assert not (tmp_path / "_site" / "favicon.ico").exists()


# ---- The setup script ----


def test_the_label_file_creates_every_label_the_board_reads() -> None:
    """Protects a seeded repository from a board label that does not exist.

    The setup script creates the labels in ``.github/labels.json``, and a
    session cannot set a label the repository lacks. So every label the
    generator reads is there: the kind labels, both ``working:`` labels and a
    ``band:N`` for each of the first three bands.
    """
    labels = json.loads((REPO_ROOT / ".github" / "labels.json").read_text(encoding="utf-8"))
    names = {label["name"] for label in labels}
    read = {label for label, _ in bb.KIND_LABELS} | set(bb.WORKING)
    read |= {f"band:{n}" for n in (1, 2, 3)}
    assert read <= names, sorted(read - names)
    assert all(bb.BAND.match(n) for n in names if n.startswith("band:"))
    assert all(len(label["description"]) <= 100 for label in labels)


# A repository with no Pages site answers 404, and the real `gh` prints that
# error's JSON body to stdout and exits 1, skipping `--jq`. The fake does the
# same. A fake writing its error to stderr let a draft of the script pass here
# while it read that body as a source type, which a dry run against this
# repository caught.
FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_LOG"
case "$*" in
  *"repos/x/y/pages --jq .build_type"*)
    if [ -n "$PAGES_TYPE" ]; then echo "$PAGES_TYPE"; exit 0; fi
    echo '{"message":"Not Found","status":"404"}'
    echo "gh: Not Found (HTTP 404)" >&2
    exit 1 ;;
  "api repos/x/y/rulesets")
    echo '[]'; exit 0 ;;
  "api repos/x/y/environments/github-pages --jq"*)
    if [ -n "$ENV_POLICY" ]; then echo "$ENV_POLICY"; exit 0; fi
    echo '{"message":"Not Found","status":"404"}'
    exit 1 ;;
  "api repos/x/y/environments/github-pages/deployment-branch-policies --jq"*)
    if [ -n "$BRANCHES" ]; then printf '%s\\n' $BRANCHES; exit 0; fi
    echo '{"message":"Not Found","status":"404"}'
    exit 1 ;;
esac
exit 0
"""


def _run_setup(tmp_path: Path, **env_vars: str) -> tuple[subprocess.CompletedProcess, str]:
    """The setup script run against a fake ``gh``, and every call it made."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "gh"
    fake.write_text(FAKE_GH)
    fake.chmod(0o755)
    log = tmp_path / "gh.log"
    log.write_text("")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_LOG": str(log),
        "PAGES_TYPE": "",
        "BRANCHES": "",
        "ENV_POLICY": "",
        **env_vars,
    }
    done = subprocess.run(
        ["bash", str(SETUP), "x/y"], env=env, capture_output=True, text=True, check=False
    )
    return done, log.read_text()


ENV_PUT = (
    "api --method PUT repos/x/y/environments/github-pages "
    "-F deployment_branch_policy[protected_branches]=false "
    "-F deployment_branch_policy[custom_branch_policies]=true"
)
ENV_POST = (
    "api --method POST repos/x/y/environments/github-pages/deployment-branch-policies "
    "-f name=main -f type=branch"
)


@pytest.mark.parametrize(
    ("env_policy", "branches", "line", "puts", "adds"),
    [
        ("", "", "environment: allowing main", True, True),
        ("none", "", "environment: allowing main", True, True),
        ("custom", "release", "environment: allowing main", False, True),
        ("custom", "release main", "environment: main already allowed", False, False),
        ("protected", "", "deploys from protected branches only, left as it is", False, False),
    ],
    ids=["absent", "no-rule", "another-branch", "main-present", "protected-branches"],
)
def test_the_setup_script_limits_the_pages_environment_to_main(
    tmp_path: Path, env_policy: str, branches: str, line: str, puts: bool, adds: bool
) -> None:
    """Protects the site from a deploy run on any branch but ``main``.

    An environment that is absent or has no branch rule takes custom branch
    policies, sent as booleans rather than strings. One that already has a
    rule is not rewritten, because a PUT may drop reviewers or a wait timer
    the owner set. A policy for ``main`` is added unless one exists, a policy
    for another branch is left alone, and a dry run writes nothing.
    """
    done, calls = _run_setup(tmp_path, ENV_POLICY=env_policy, BRANCHES=branches)
    assert done.returncode == 0, done.stderr
    assert line in done.stdout
    assert (ENV_PUT in calls) is puts
    assert (ENV_POST in calls) is adds
    assert "DELETE" not in calls
    dry, dry_calls = _run_setup(tmp_path, ENV_POLICY=env_policy, BRANCHES=branches, DRY_RUN="1")
    assert dry.returncode == 0, dry.stderr
    assert line in dry.stdout
    assert "--method" not in dry_calls


@pytest.mark.parametrize(
    ("pages_type", "line", "write"),
    [
        ("", "pages: enabling, source GitHub Actions", "--method POST repos/x/y/pages"),
        ("legacy", "pages: left as it is, publishing from a branch (legacy).", None),
        ("workflow", "pages: already on, source GitHub Actions", None),
    ],
)
def test_the_setup_script_turns_pages_on_with_actions_as_its_source(
    tmp_path: Path, pages_type: str, line: str, write: str | None
) -> None:
    """Protects the deploy job, which has nowhere to go with Pages off.

    The script reads the site first, so a run against a repository that
    already has it set leaves it alone, and a dry run writes nothing. A site
    publishing from a branch is left alone too, with a message, because
    switching its source would take down the site it serves.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(FAKE_GH)
    fake.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_LOG": str(log),
        "PAGES_TYPE": pages_type,
    }
    done = subprocess.run(
        ["bash", str(SETUP), "x/y"], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert line in done.stdout + done.stderr
    calls = log.read_text()
    if write:
        assert f"api {write}" in calls
        assert "build_type=workflow" in calls
    else:
        assert "--method POST repos/x/y/pages" not in calls
        assert "--method PUT repos/x/y/pages" not in calls

    dry = subprocess.run(
        ["bash", str(SETUP), "x/y"],
        env={**env, "DRY_RUN": "1", "GH_LOG": str(tmp_path / "dry.log")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry.returncode == 0, dry.stderr
    assert line in dry.stdout + dry.stderr
    assert "--method" not in (tmp_path / "dry.log").read_text()


# ---- The plugin's 0.6.x text ----
#
# The release that names every input the reusable workflow declares. These
# tests read what it tells a session to run, as well as what it says.


# Each input's ``with:`` form as the plugin writes it, by the file that writes
# it. The forms ending in a space are followed by the caller's own text.
SKILL_WITH = (
    "`with: title: ",
    f"`with: data-label: {DATA_LABEL}`",
    "`with: review-heading: Review complete`",
    '`with: settled-rollup: "true"`',
    "`with: milestone-default: MVP <n>`",
    '`with: owner-body-lines: "true"`',
    "`with: ranking: order`",
)
PAGE_WITH = (
    "`with: icon: <path>`",
    "`with: subtitle: `",
    "`with: note: `",
    '`with: default-branch-head: "true"`',
    '`with: label-colors: "true"`',
    '`with: sort-labels: "true"`',
)
WITH_FORM = re.compile(r"`with:\s+([\w-]+):")


FENCE = re.compile(r"^ *(```|~~~)[^\n]*\n(.*?)^ *\1", re.S | re.M)
SHARED_USES = re.compile(r"uses:\s*[\"']?l3a0/repo-template/\.github/workflows/build-board\.yml@")
# A flow mapping's entries, split on commas outside quotes.
FLOW_ENTRY = re.compile(r"(?:[^,\"']|\"[^\"]*\"|'[^']*')+")
WITH_LINE = re.compile(r"( *)with:\s*(?:\{(.*)\})?\s*(?:#.*)?")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _siblings(lines: list[str], k: int) -> list[str]:
    """The lines of the YAML mapping that holds ``lines[k]``, at its indent."""
    indent, found = _indent(lines[k]), []
    for step in (-1, 1):
        j = k + step
        while 0 <= j < len(lines) and (not lines[j].strip() or _indent(lines[j]) >= indent):
            if lines[j].strip() and _indent(lines[j]) == indent:
                found.append(lines[j])
            j += step
    return found


def _fenced_with(text: str) -> set[str]:
    """Each input under a ``with:`` of the shared workflow inside a fenced block.

    Only a ``with:`` whose sibling ``uses:`` names the reusable workflow here
    is read, so an action's own inputs, such as ``actions/checkout``'s
    ``fetch-depth``, are not. A fence is backticks or tildes, line endings may
    be CRLF, the ``with:`` may carry a comment, its block may hold blank lines
    and comment lines, and the flow form ``with: {a: x}`` is read too. The
    ``uses:`` value and each key may be quoted, and a quoted flow value may
    hold a comma.
    """
    names = set()
    for _, fence in FENCE.findall(text.replace("\r\n", "\n")):
        lines = fence.split("\n")
        for k, line in enumerate(lines):
            m = WITH_LINE.fullmatch(line)
            if not m or not any(SHARED_USES.match(s.strip()) for s in _siblings(lines, k)):
                continue
            if m.group(2) is not None:
                names |= {_key(p) for p in FLOW_ENTRY.findall(m.group(2)) if p.strip() and ":" in p}
                continue
            inner = None
            for below in lines[k + 1 :]:
                if not below.strip() or below.strip().startswith("#"):
                    continue
                if _indent(below) <= len(m.group(1)):
                    break
                inner = _indent(below) if inner is None else inner
                if _indent(below) == inner and ":" in below:
                    names.add(_key(below))
    return names


def _key(entry: str) -> str:
    """The key of one ``key: value`` entry, without the quotes YAML allows round it."""
    return entry.strip().split(":", 1)[0].strip().strip("\"'")


def test_the_plugin_names_every_input_in_its_with_form() -> None:
    """Protects a caller from copying an input's form the workflow does not read.

    Each form is read where the plugin writes it, and between them they name
    every input the workflow declares, so a new input fails here until the
    plugin says how to pass it. Every other ``with:`` form in either file has
    to name a declared input too, so a misspelt one fails, and so does every
    input under the shared workflow's ``with:`` inside a fence. Those are read
    in the whole file, the list of pinned strings included, so no text can
    hide there. ``page.md`` also names the key the milestone selector stores
    its choice under.
    """
    skill = _skill()
    page = _plugin("page.md")
    for form in SKILL_WITH:
        assert form in skill, form
    for form in PAGE_WITH:
        assert form in page, form
    assert "`board-ms:<owner/repo>`" in page
    named = {WITH_FORM.match(t).group(1) for t in SKILL_WITH + PAGE_WITH}
    assert named == set(_inputs())
    raw = _plugin("SKILL.md")
    written = set(WITH_FORM.findall(raw)) | set(WITH_FORM.findall(page))
    written |= _fenced_with(raw) | _fenced_with(page)
    assert written <= set(_inputs()), written - set(_inputs())


def test_the_skill_table_lists_every_input_the_workflow_declares() -> None:
    """Protects the skill's table of inputs from missing one or naming a dead one."""
    section = _skill().split("\n### The inputs a caller passes\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    listed = [name.strip("` ") for row in rows for name in row.split(" | ")[0][2:].split(", ")]
    assert sorted(listed) == sorted(_inputs())


MINIMUM_PINS = "| Input | First declared at |\n| --- | --- |\n"
PIN_TO_USE = re.compile(r"`([0-9a-f]{7,40})` is the pin to use")


def test_the_skill_names_the_first_commit_for_every_input() -> None:
    """Protects a caller from pinning a commit that lacks an input it passes.

    The table of first declarations names each input the workflow declares
    once, in code spans, so a new input fails here until the table carries
    it, and a deleted row fails too. The rows' commits are not checked, since
    that needs each commit's parent as well.
    """
    skill = _skill()
    assert skill.count(MINIMUM_PINS) == 1, "the skill carries no single table of first pins"
    table = skill.split(MINIMUM_PINS, 1)[1].split("\n\n", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    named = [n for row in rows for n in re.findall(r"`([\w-]+)`", row.split(" | ")[0])]
    assert sorted(named) == sorted(_inputs())


def test_the_pin_to_use_declares_every_input() -> None:
    """Protects a caller from copying a pin GitHub refuses or that lacks an input.

    The whole file names exactly one commit as the pin to use, so a second
    one hidden in the list of pinned strings fails too. The reusable workflow
    at that commit, read from GitHub, has to declare every input declared
    here, each typed as a string. At ``4c546fc`` the ``default-branch-head``
    input carries no type, and GitHub refuses the workflow. Any later commit
    that declares every input passes, so this cannot tell the pin the plugin
    should name from an older one that also works.
    """
    pins = PIN_TO_USE.findall(_plugin("SKILL.md"))
    assert len(pins) == 1, pins
    assert not "4c546fc".startswith(pins[0][:7]), pins[0]
    declared = _declared(_template_at(pins[0], ".github/workflows/build-board.yml"))
    for name in _inputs():
        assert name in declared, f"{name} is not declared at {pins[0]}"
        assert re.findall(r"^ {8}type:.*$", declared[name], re.M) == ["        type: string"], name


# The table of each repository's pin and inputs.
BOARD_ROWS = "| Repository | Pin | Inputs |\n| --- | --- | --- |\n"


# The table under "Generator compatibility" that repeats each repository's pin.
COMPAT_ROWS = (
    "| Repository | Pinned at | Formats that pin reads | Caller read at |\n"
    "| --- | --- | --- | --- |\n"
)


def _rows(raw: str, header: str) -> list[list[str]]:
    """The cells of each row of the one table under ``header``."""
    assert raw.count(header) == 1, f"the skill carries no single table under {header!r}"
    rows = raw.split(header, 1)[1].split("\n\n", 1)[0].splitlines()
    assert rows
    return [row.strip("| ").split(" | ") for row in rows]


def test_the_board_table_names_declared_inputs_and_no_refused_pin() -> None:
    """Protects a session from copying a repository's row that GitHub would refuse.

    Every input a row names in a code span has to be one the workflow
    declares, and no row pins ``4c546fc``. The compatibility table repeats
    each repository's pin, so it pins no ``4c546fc`` either, and names the
    same pin for each repository. The whole file is read.
    """
    raw = _plugin("SKILL.md")
    pins = {}
    for repo, pin, inputs in _rows(raw, BOARD_ROWS):
        pins[repo] = re.findall(r"`([^`]+)`", pin)
        assert not any(p.startswith("4c546fc") for p in pins[repo]), repo
        assert set(re.findall(r"`([\w-]+)`", inputs)) <= set(_inputs()), repo
    compat = {}
    for repo, pin, *_ in _rows(raw, COMPAT_ROWS):
        compat[repo] = re.findall(r"`([^`]+)`", pin)
        assert not any(p.startswith("4c546fc") for p in compat[repo]), repo
    assert compat == pins


def test_the_skill_states_the_digit_limit_once() -> None:
    """Protects the skill from a second copy of ``MAX_DIGITS`` that drifts.

    The whole file is read too, so a copy in the list of pinned strings fails.
    """
    phrase = f"at most {bb.MAX_DIGITS} digits"
    assert _skill().count(phrase) == 1
    assert _plugin("SKILL.md").count(phrase) == 1


def _tool(name: str) -> str:
    """The path of a command the test runs, or a skip where it is missing off CI."""
    found = shutil.which(name)
    if found:
        return found
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        raise AssertionError(f"{name} is missing on CI")
    pytest.skip(f"{name} is not installed")


# A caller that passes every input the workflow declares, each as YAML text
# and the value the generator should receive. A bare ``true`` or ``false`` is
# a YAML boolean, which the build command has to pass as the string ``true``
# or ``false``. The real generator refuses ``false``, since an on-or-off input
# takes only empty or ``true``, but the recording generator below stops before
# that check, so ``false`` here tests only that the command passes what the
# caller wrote. A literal block keeps its newline, a folded one, the form
# l3a0/marketlake's caller writes for ``note``, joins its lines with spaces,
# and an input written with no value is empty.
CALLER_WITH = {
    "title": ("", ""),
    "icon": (".github/board/favicon.ico", None),
    "data-label": (DATA_LABEL, DATA_LABEL),
    "subtitle": (
        ">-\n        the order of work\n        on the lake",
        "the order of work on the lake",
    ),
    "note": (
        "|\n        Read [the design](https://example.com/design).\n        Then the plan.",
        "Read [the design](https://example.com/design).\nThen the plan.\n",
    ),
    "default-branch-head": ("true", "true"),
    "label-colors": ('"true"', "true"),
    "sort-labels": ("true", "true"),
    "review-heading": ("Review complete", "Review complete"),
    "settled-rollup": ("false", "false"),
    "milestone-default": ("MVP <n>", "MVP <n>"),
    "owner-body-lines": ('"true"', "true"),
    "ranking": ("order", "order"),
}

# Three callers: one passing every input, one with no ``with:`` block, which
# is this repository's own, and one whose ``with:`` is left empty.
CALLERS = {
    "every input": "    with:\n"
    + "\n".join(f"      {k}: {v}".rstrip() for k, (v, _) in CALLER_WITH.items())
    + "\n",
    "no with block": "",
    "an empty with": "    with:\n",
}

# A generator that records the arguments its build would have run with, and
# exits as ``BOARD_EXIT`` says, so a test can see the command's own status.
RECORDING_GENERATOR = """
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("build_board", os.environ["BOARD_SCRIPT"])
bb = importlib.util.module_from_spec(spec)
sys.modules["build_board"] = bb
spec.loader.exec_module(bb)
def record(args):
    with open(os.environ["BOARD_RECORD"], "w") as f:
        json.dump({k: v for k, v in vars(args).items() if k != "func"}, f)
bb.cmd_build = record
status = bb.main(sys.argv[1:])
sys.exit(int(os.environ.get("BOARD_EXIT", status)))
"""


def test_every_input_has_a_value_in_the_stand_in_caller() -> None:
    """Protects the build-command test from skipping an input the workflow adds."""
    assert set(CALLER_WITH) == set(_inputs())


def _build_block() -> str:
    """The skill's command that builds the board into a scratch directory."""
    blocks = re.findall(r"```bash\n(.*?)```", _skill(), re.S)
    found = [b for b in blocks if "rm -f <scratch>/board.json" in b]
    assert len(found) == 1, "the skill carries no single build command"
    return found[0]


def _run_build_block(
    block: str, tmp_path: Path, caller_with: str = CALLERS["every input"], status: str = ""
) -> tuple[dict | None, subprocess.CompletedProcess, Path]:
    """What the generator received when ``block`` ran in a caller, the run, and the output.

    ``template`` serves files from a stand-in template whose
    ``scripts/build_board.py`` is the recording generator, so nothing reads
    GitHub and a command fetching any other path fetches nothing.
    """
    bash, _ = _tool("bash"), _tool("uv")
    caller = tmp_path / "caller"
    (caller / ".github" / "workflows").mkdir(parents=True)
    (caller / ".github" / "workflows" / "board.yml").write_text(
        "on:\n  workflow_dispatch:\njobs:\n  board:\n"
        "    uses: l3a0/repo-template/.github/workflows/build-board.yml@main\n" + caller_with,
        encoding="utf-8",
    )
    root = tmp_path / "template"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "build_board.py").write_text(RECORDING_GENERATOR, encoding="utf-8")
    record = tmp_path / "record.json"
    out = tmp_path / "out"
    out.mkdir()
    script = f'REPO={REPO}\ntemplate() {{ cat "$TEMPLATE_ROOT/$1"; }}\n' + block.replace(
        "<scratch>", str(out)
    )
    env = {
        **os.environ,
        "BOARD_SCRIPT": str(SCRIPT),
        "BOARD_RECORD": str(record),
        "TEMPLATE_ROOT": str(root),
    }
    env.pop("VIRTUAL_ENV", None)
    env.pop("BOARD_EXIT", None)
    if status:
        env["BOARD_EXIT"] = status
    done = subprocess.run(
        [bash, "-c", script], cwd=caller, env=env, capture_output=True, text=True, timeout=300
    )
    got = json.loads(record.read_text()) if record.exists() else None
    left = sorted(str(p.relative_to(caller)) for p in caller.rglob("*") if p.is_file())
    if left != [".github/workflows/board.yml"]:
        done.stderr += f"\nthe command left files in the caller: {left}"
    return got, done, out


def _input_problems(
    got: dict | None, done: subprocess.CompletedProcess, out: Path, want: dict[str, str]
) -> list[str]:
    """Each way a run of the build command differs from what the caller asked for."""
    if got is None:
        return [f"the generator never reached its build: {done.stderr[-2000:]}"]
    problems = []
    if done.returncode != 0:
        problems.append(f"exit status {done.returncode}: {done.stderr[-2000:]}")
    if "left files in the caller" in done.stderr:
        problems.append(done.stderr.rsplit("\n", 1)[-1])
    if got.get("repo") != REPO or got.get("workflow") != ".github/workflows/board.yml":
        problems.append(f"repo or workflow: {got.get('repo')!r} {got.get('workflow')!r}")
    if got.get("out") != str(out):
        problems.append(f"out: {got.get('out')!r}, not {str(out)!r}")
    if "icon" in got:
        problems.append("icon reached the generator")
    for name, value in want.items():
        if got.get(name.replace("-", "_")) != value:
            problems.append(f"{name}: {got.get(name.replace('-', '_'))!r}, not {value!r}")
    return problems


def _every_input() -> dict[str, str]:
    return {k: v for k, (_, v) in CALLER_WITH.items() if v is not None}


def _no_input() -> dict[str, str]:
    return {k: "" for k in _inputs() if k != "icon"}


@pytest.mark.parametrize("caller", list(CALLERS))
def test_the_skill_build_command_passes_every_input(caller: str, tmp_path: Path) -> None:
    """Protects a local build from reading a different board than the Action.

    A status round reads the board the skill's command builds, not the
    published one. A command that drops the caller's inputs builds the
    defaults, so under ``ranking: order`` it ranks nothing and under
    ``review-heading`` it counts the wrong reviews, with nothing failing. A
    caller with no inputs, such as this repository's own, has to reach the
    generator with every input empty rather than stop the command.
    """
    got, done, out = _run_build_block(_build_block(), tmp_path, CALLERS[caller])
    want = _every_input() if caller == "every input" else _no_input()
    assert _input_problems(got, done, out, want) == [], done.stderr


def test_the_skill_build_command_passes_the_generators_failure_on(tmp_path: Path) -> None:
    """Protects a round from reading an old board after the build failed."""
    got, done, _ = _run_build_block(_build_block(), tmp_path, status="1")
    assert got is not None, done.stderr
    assert done.returncode != 0, done.stderr


def test_the_build_command_names_an_exact_version_of_each_package() -> None:
    """Protects every round from reading the caller with a different parser.

    The command fetches PyYAML for the run, and a version left open lets each
    machine resolve its own, so a round and these tests could parse the same
    caller differently.
    """
    withs = re.findall(r"--with\s+\S+", _build_block())
    assert withs, "the build command fetches no package"
    for w in withs:
        assert re.fullmatch(r"--with [\w.-]+==\d+(\.\d+)*", w), w


def test_the_skill_template_line_fetches_at_the_pin(tmp_path: Path) -> None:
    """Protects every command that reads the template from reading another commit.

    The setup block's ``template`` runs ``gh api`` for a file of the template.
    A stand-in ``gh`` prints what it was asked for, so the test sees the whole
    call, whose path has to name the commit ``$PIN`` holds and whose header
    asks for the file's raw text.
    """
    bash = _tool("bash")
    lines = [x for x in _skill().splitlines() if x.startswith("template() {")]
    assert len(lines) == 1, "the skill carries no single template() line"
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    (stub / "gh").chmod(0o755)
    pin = "0123abcd" * 5
    done = subprocess.run(
        [bash, "-c", f"PIN={pin}\n{lines[0]}\ntemplate scripts/build_board.py"],
        env={**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    asked = done.stdout.splitlines()
    assert asked == [
        "api",
        f"repos/l3a0/repo-template/contents/scripts/build_board.py?ref={pin}",
        "-H",
        "Accept: application/vnd.github.raw",
    ]


def _setup_sed_line() -> str | None:
    """The setup block's line printing the caller's ``with:`` block, found by what it reads."""
    return next(
        (
            x
            for x in _skill().splitlines()
            if x.startswith("sed ") and "/^    with:$/" in x and "board.yml" in x
        ),
        None,
    )


def test_the_skill_setup_block_prints_every_input(tmp_path: Path) -> None:
    """Protects the setup block's list of the caller's inputs from missing one."""
    bash = _tool("bash")
    line = _setup_sed_line()
    assert line, "the skill's setup block prints no with: block"
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "board.yml").write_text(
        "on:\n  workflow_dispatch:\njobs:\n  board:\n"
        "    uses: l3a0/repo-template/.github/workflows/build-board.yml@main\n"
        + CALLERS["every input"]
        + "concurrency:\n  group: pages\n",
        encoding="utf-8",
    )
    done = subprocess.run([bash, "-c", line], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    printed = re.findall(r"^      ([\w-]+):", done.stdout, re.M)
    assert printed == list(CALLER_WITH), done.stdout


# Four ways the build command can stop passing the caller's inputs, each as
# the text it replaces in the block and what it puts there.
BUILD_MUTANTS = {
    "passes --icon": ('if k != "icon"', "if True"),
    "writes the flags with underscores": ('f"--{k}=', "f\"--{k.replace('-', '_')}="),
    "drops the flags": (", *flags])", "])"),
    "passes a bare true as True": ("str(v).lower() if isinstance(v, bool) else v", "v"),
}


@pytest.mark.parametrize("mutant", list(BUILD_MUTANTS))
def test_the_build_command_check_fails_a_broken_command(mutant: str, tmp_path: Path) -> None:
    """Protects the check above from passing a command that loses the inputs.

    The clean command runs first, so an offline run, where every command
    fails to reach the generator, cannot make a mutant look caught.
    """
    old, new = BUILD_MUTANTS[mutant]
    block = _build_block()
    clean = tmp_path / "clean"
    clean.mkdir()
    got, done, _ = _run_build_block(block, clean)
    assert got is not None, f"the clean command never reached the generator: {done.stderr}"
    assert block.count(old) == 1, (
        f"the mutant {mutant!r} no longer matches the skill's command once; "
        "re-aim it at the rewritten block"
    )
    broken = tmp_path / "broken"
    broken.mkdir()
    assert _input_problems(*_run_build_block(block.replace(old, new), broken), _every_input())


# A jq call on a board, with its options, either a quoted or a bare filter,
# and the file it reads. ``--jq``, which reads gh's output rather than a
# board, is not one.
JQ_CALL = re.compile(r"(?<![-\w])jq(?: -[a-z]+)* (?:'([^']+)'|(\.[\w.]+))(?: ([^\s`]+))?")
# Any jq command at all, a code span's included, which the count of calls
# above has to equal, so a call the pattern cannot read, such as a
# double-quoted filter or one with ``--arg``, fails. Both are counted only in
# fences and code spans, since a jq in plain prose is a word, not a command.
LOOSE_JQ = re.compile(r"(?<![-\w])jq\s")
# An inline code span, of any number of backticks.
SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
# Where every jq call reads the board, the file the build command writes.
JQ_FILE = "<scratch>/board.json"
# The review read moment 5 gives, which the fallback in sync-prune-next reuses.
REVIEWED_READ = ".prs.items[] | select(.pr == <n>) | .reviewed"
# The pull request the review read asks about, which the golden holds.
JQ_PR = 30


def _jq_expected(board: dict) -> dict[str, dict[str, list]]:
    """What each filter of each skill should print for ``board``, read in Python."""

    def items(section: str) -> list:
        return board[section]["items"]

    reviewed = [p["reviewed"] for p in items("prs") if p["pr"] == JQ_PR]
    return {
        "update-build-board": {REVIEWED_READ: reviewed},
        "sync-prune-next": {
            ".working.items[]": items("working"),
            REVIEWED_READ: reviewed,
            ".state.updatedAt": [board["state"]["updatedAt"]],
        },
    }


def _code(text: str) -> list[str]:
    """The text of each fenced block and each code span in ``text``."""
    text = text.replace("\r\n", "\n")
    fences = [body for _, body in FENCE.findall(text)]
    return fences + [span for _, span in SPAN.findall(FENCE.sub("", text))]


def _jq_file(file: str) -> str:
    """The file a jq call reads, less a trailing ``)`` and one pair of quotes."""
    file = file.removesuffix(")")
    if len(file) > 1 and file[0] == file[-1] and file[0] in "\"'":
        file = file[1:-1]
    return file


def _wide_board() -> dict:
    """The golden with a second working label and a second entry for ``JQ_PR``.

    The golden holds one of each, so a filter reading only the first item
    prints the same there. The second entry is reviewed, and the golden's is
    not, so a filter that prints false whatever it reads differs too.
    """
    board = json.loads(MARKERS_GOLDEN.read_text(encoding="utf-8"))
    board["working"]["items"].append({"n": 99, "kind": "build"})
    first = next(p for p in board["prs"]["items"] if p["pr"] == JQ_PR)
    board["prs"]["items"].append({**first, "issue": 99, "reviewed": True})
    return board


def _collapse(f: str) -> str:
    """A filter with each run of whitespace read as one space."""
    return " ".join(f.split())


def _jq(jq: str, f: str, path: Path) -> list:
    done = subprocess.run(
        [jq, "-c", f.replace("<n>", str(JQ_PR)), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, (f, done.stderr)
    return [json.loads(line) for line in done.stdout.splitlines()]


def test_each_jq_filter_in_the_skills_reads_a_board(tmp_path: Path) -> None:
    """Protects a status round from a filter that reads the wrong thing.

    Each skill's filters are compared on their own, so a read dropped from
    one skill fails even while the other carries the same filter. Every jq
    command in a fence or a code span has to be a call the pattern reads, and
    every call reads the file the build command writes. Each filter runs against a board
    the generator wrote, a golden here, and against a wider copy that
    ``_wide_board`` describes, and has to print what each holds, read in
    Python. Filters compare with whitespace collapsed, so a plugin release
    that only re-spaces one passes, while one that rewords a filter needs an
    ``_jq_expected`` edit when ``PLUGIN_COMMIT`` moves.
    """
    jq = _tool("jq")
    golden = json.loads(MARKERS_GOLDEN.read_text(encoding="utf-8"))
    wide = _wide_board()
    assert _jq_expected(wide)["update-build-board"][REVIEWED_READ] == [False, True]
    assert len(_jq_expected(wide)["sync-prune-next"][".working.items[]"]) == 2
    wide_path = tmp_path / "wide.json"
    wide_path.write_text(json.dumps(wide), encoding="utf-8")
    for skill, outputs in _jq_expected(golden).items():
        code = _code(_plugin("SKILL.md", skill))
        calls = [call for part in code for call in JQ_CALL.findall(part)]
        commands = sum(len(LOOSE_JQ.findall(part)) for part in code)
        assert commands == len(calls), f"{skill} has a jq command the pattern cannot read"
        for quoted, bare, file in calls:
            assert _jq_file(file) == JQ_FILE, (skill, quoted or bare, file)
        filters = {_collapse(quoted or bare) for quoted, bare, _ in calls}
        want = {_collapse(f): v for f, v in outputs.items()}
        assert filters == set(want), (
            f"add each new filter's expected output to _jq_expected[{skill!r}]: "
            f"{filters ^ set(want)}"
        )
        wider = {_collapse(f): v for f, v in _jq_expected(wide)[skill].items()}
        for f in filters:
            assert _jq(jq, f, MARKERS_GOLDEN) == want[f], (skill, f)
            assert _jq(jq, f, wide_path) == wider[f], (skill, f)


# Two commits in a stand-in answer, by oid, with their dates.
HEAD_OID, OTHER_OID = "b" * 40, "a" * 40
COMMIT_DATES = {HEAD_OID: "2026-10-28T19:40:29Z", OTHER_OID: "2026-09-01T00:00:00Z"}


def test_the_fallback_reads_the_head_commits_date(tmp_path: Path) -> None:
    """Protects a round from trusting a review the head commit came after.

    ``sync-prune-next``'s fallback reads a pull request whose head commit is
    later than the published board as unknown. ``gh pr view --json commits``
    lists only the first 100 commits, so its last is not always the head. The
    skill's command asks for the last commit and keeps it only when its oid
    is the head's. Its filter runs on stand-in answers holding two commits,
    the head first and then last, and has to print the head's date both
    times, and the sentence after it has to read a later date as unknown.
    """
    jq = _tool("jq")
    raw = _plugin("SKILL.md", "sync-prune-next")
    lines = [
        x
        for x in raw.splitlines()
        if x.startswith("gh api graphql") and "headRefOid" in x and "committedDate" in x
    ]
    assert len(lines) == 1, "the fallback carries no single head-date command"
    assert "commits(last:1)" in lines[0], "the command does not ask for the last commit"
    found = re.search(r"--jq '([^']+)'", lines[0])
    assert found, "the command carries no --jq filter"
    for order in ([OTHER_OID, HEAD_OID], [HEAD_OID, OTHER_OID]):
        nodes = [{"commit": {"oid": o, "committedDate": COMMIT_DATES[o]}} for o in order]
        answer = {
            "data": {
                "repository": {"pullRequest": {"headRefOid": HEAD_OID, "commits": {"nodes": nodes}}}
            }
        }
        path = tmp_path / "answer.json"
        path.write_text(json.dumps(answer), encoding="utf-8")
        done = subprocess.run([jq, "-r", found.group(1), str(path)], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        assert done.stdout.splitlines() == [COMMIT_DATES[HEAD_OID]], order
    assert re.search(r"dated later than the file's `state\.updatedAt` reads as unknown", raw)


SHARED = "uses: l3a0/repo-template/.github/workflows/build-board.yml@main"


def _fence(body: str, mark: str = "```") -> str:
    return f"{mark}yaml\n{body}\n{mark}\n"


HELPER_CASES = [
    (
        "block",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:\n      title: T\n      ranking: order"),
        {"title", "ranking"},
    ),
    (
        "with before uses",
        _fenced_with,
        _fence(f"    with:\n      title: T\n    {SHARED}"),
        {"title"},
    ),
    (
        "trailing comment",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:  # inputs\n      title: T"),
        {"title"},
    ),
    (
        "blank lines",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:\n      title: T\n\n      ranking: order"),
        {"title", "ranking"},
    ),
    (
        "comment lines",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:\n      # a note\n      title: T"),
        {"title"},
    ),
    (
        "a folded value",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:\n      note: >-\n        Read: this.\n      title: T"),
        {"note", "title"},
    ),
    ("tildes", _fenced_with, _fence(f"    {SHARED}\n    with:\n      title: T", "~~~"), {"title"}),
    (
        "CRLF",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:  # inputs\n      title: T").replace("\n", "\r\n"),
        {"title"},
    ),
    (
        "four backticks",
        _fenced_with,
        _fence(f"    {SHARED}\n    with:\n      title: T", "````"),
        {"title"},
    ),
    (
        "a fence in a list item",
        _fenced_with,
        f"1. Item\n\n   ```yaml\n   jobs:\n     board:\n       {SHARED}\n       with:\n"
        "         title: T\n   ```\n",
        {"title"},
    ),
    (
        "flow",
        _fenced_with,
        _fence(f"    {SHARED}\n    with: {{title: T, ranking: order}}"),
        {"title", "ranking"},
    ),
    (
        "actions/checkout",
        _fenced_with,
        _fence("      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0"),
        set(),
    ),
    (
        "a quoted uses",
        _fenced_with,
        _fence(
            '    uses: "l3a0/repo-template/.github/workflows/build-board.yml@main"\n'
            "    with:\n      title: T"
        ),
        {"title"},
    ),
    (
        "flow with a comma in quotes",
        _fenced_with,
        _fence(f'    {SHARED}\n    with: {{title: "a, b", ranking: order}}'),
        {"title", "ranking"},
    ),
    ("a quoted key", _fenced_with, _fence(f'    {SHARED}\n    with:\n      "title": T'), {"title"}),
    (
        "an item continued at three spaces",
        lambda t: bool(_pinned_list_problems(t)),
        f"\n{PINNED_OPENER} More.\n\n1. One.\n   continued.\n2. Two.\n",
        False,
    ),
    (
        "a paragraph nested at four spaces",
        lambda t: bool(_pinned_list_problems(t)),
        f"\n{PINNED_OPENER} More.\n\n1. One.\n2. Two.\n\n    Nested.\n",
        False,
    ),
    (
        "an unindented paragraph",
        lambda t: bool(_pinned_list_problems(t)),
        f"\n{PINNED_OPENER} More.\n\n1. One.\n2. Two.\n\nLoose.\n",
        True,
    ),
    (
        "a paragraph at two spaces",
        lambda t: bool(_pinned_list_problems(t)),
        f"\n{PINNED_OPENER} More.\n\n1. One.\n2. Two.\n\n  Two spaces.\n",
        True,
    ),
    ("a bare file", _jq_file, "<scratch>/board.json", "<scratch>/board.json"),
    ("a double-quoted file", _jq_file, '"<scratch>/board.json"', "<scratch>/board.json"),
    ("a single-quoted file", _jq_file, "'<scratch>/board.json'", "<scratch>/board.json"),
    ("a file ending a $( )", _jq_file, "<scratch>/board.json)", "<scratch>/board.json"),
]


@pytest.mark.parametrize(
    ("helper", "given", "want"),
    [pytest.param(h, g, w, id=name) for name, h, g, w in HELPER_CASES],
)
def test_the_helpers_that_read_the_plugin_read_what_they_say(helper, given, want) -> None:
    """Protects the plugin checks above from a helper that quietly reads nothing.

    Each check rests on a helper. A helper that returned nothing, or read
    every block, would leave its check passing on any text, so each one runs
    on cases built here, both ones it must read and ones it must not.
    """
    assert helper(given) == want
