"""Build the build board's data from GitHub, for the page on GitHub Pages.

The build board is a page answering what is in flight and what to take next.
A board written by hand costs session turns on every change and misses any
change no session saw. This script reads every figure from GitHub and writes
them as one ``board.json`` beside the page. The reusable workflow
``.github/workflows/build-board.yml`` runs it, and each repository's caller,
``.github/workflows/board.yml``, starts that workflow on every change and on a
schedule. No Claude runs at any step. The judgement the board shows, such as
which session holds a card and how the owner ranks the work, lives on GitHub
as labels, links and marker lines.

Provenance: ported from ``scripts/build_board.py`` in l3a0/quantitative-trading
at commit ``6da0ee3``, landed here by the pull request that closes
l3a0/repo-template#24. On the way the ``blocked-on-data`` kind was cut, the
board gained ``state.repo`` and ``state.title`` so the page names no
repository, and comments citing that repository's issues were restated as the
rules they record. The pull request that closes l3a0/repo-template#40 brought
the kind back behind ``--data-label``, which names the label a repository
marks such issues with, so a repository that never names one reads no ``data``
kind at all. The pull request that closes l3a0/repo-template#47 ported
l3a0/marketlake's review rule and its rollup from
``.claude/skills/sync-prune-next/build_board.py`` at commit ``cc9d3432``,
behind ``--review-heading`` and ``--settled-rollup``, so a repository that
names neither reads pull requests as before.

It writes the six sections the page reads.

1. ``state``, with the repository, the board's title, the open issue count, the
   time GitHub was read, the longest gap between two scheduled runs, and the
   age after which the page calls the board stale.
2. ``tracker``, one card per open issue. Its title, milestone and labels come
   from the issue. ``kind`` comes from labels and sub-issues, ``needs`` from
   native "blocked by" links, and ``after`` from a ``Board after:`` line in the
   body.
3. ``prs``, one item per pull request and each issue in this repository it
   names, with its state, its checks at the current head, whether GitHub
   registered a closing link to that issue, and whether the owner posted a
   review. A caller that names a review heading counts only that heading
   posted since the head commit, and a caller that asks for a settled rollup
   leaves the board's own checks out of it.
4. ``working``, one item per issue carrying a ``working:build`` or
   ``working:decompose`` label, which a session sets while it holds the card.
5. ``planned``, one item per issue with an owner comment carrying a
   ``Board verdict:`` line, which a decompose loop writes when it exits.
6. ``next``, one item per issue carrying a ``band:N`` label, ordered within its
   band by a ``Board order:`` line in the body.

The ``update-build-board`` skill in the ``l3a0`` Claude Code plugin states each
format and when a session sets it.

The page refuses a whole section when one item lacks a field it reads, so
every item carries every such field. A missing milestone is an empty string
rather than a null, and a pull request that names no open issue gets no item
rather than a null issue.

Two labels can disagree, such as two ``band:N`` labels on one issue. The run
takes the lowest band, or ``build`` for both ``working:`` labels, and lists the
conflict in the job summary rather than failing, because one stray label would
otherwise freeze the whole board.

Two of its rules exist because the repository is public.

1. ``reviewed`` reads a comment opening with ``## Review``, or under a
   caller's review heading a comment or a submitted review opening with it,
   and ``planned`` a comment carrying a ``Board verdict:`` line, only when its
   author association is ``OWNER``. Anyone
   can comment, and a stranger's comment would otherwise move a card. Labels
   and links need triage access, so they need no such filter.
2. Nothing here reads the event that started the run. Every fact comes from
   the API, so an issue title never reaches a shell, and two runs started by
   different events build the same board from the same state.

It fails closed. A failed call, a GraphQL error, or a count that disagrees
with the pages read on every one of ``LIST_READS`` reads stops the run, and
the last good board stays up. Treating an error as an empty list would publish
a board with no pull requests that reads as correct. The one failure tried
again first is a call GitHub answered with a server error or never received,
which ``RETRY_WAITS`` bounds. In one 35-minute stretch, 11 of 16 runs failed
on a 502 or 504, and a query that had just timed out three times in a row
returned in under a second minutes later. One such answer says nothing about
the read.

It reads through a few nested GraphQL queries rather than one REST call per
issue. ``GITHUB_TOKEN`` allows 1,000 REST requests an hour per repository, and
a busy hour can start 30 runs, so a call per open issue would run out.
``tests/test_build_board_generator.py`` pins how many requests one run makes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = 1

# A `Part of` reference, read the way GitHub reads a closing keyword: anywhere
# in a pull request's body, with `#` and the number right after it, and never
# inside a code span or a fenced code block. Sessions write the phrase
# mid-paragraph, and a rule that read only a line opening with it dropped those
# without saying so. The one difference from GitHub, which reads a keyword in
# any case, is that the reference has to be capitalised, because lowercase
# prose such as "merged in PR 488, part of 458" names another pull request's
# issue and is not one. A sentence mentioning the phrase in passing counts
# unless a code span holds it, as a closing keyword does. `pr_items` strips the
# code before matching.
PART_OF = re.compile(r"\bPart of #(\d+)\b")

# A review comment opens with a line reading `## Review`, which the l3a0
# plugin's update-build-board skill states as the convention. "## Reviewer" is not one.
REVIEW = re.compile(r"## Review\b")
# The same heading as the rule with no caller's heading reads it: after any
# leading whitespace, posted at any time.
ANY_REVIEW = re.compile(r"\s*" + REVIEW.pattern)


def review_rule(heading: str) -> re.Pattern[str] | None:
    """The first line that closes a review under the caller's heading, or None for none.

    A caller that names a heading, such as ``Review complete``, counts a review
    only when the whole first line of an owner's comment or submitted review is
    ``## Review complete``. So ``## Review round 1, lenses running``, posted
    before the lenses report, and ``## Review completeness check`` are not
    one. The input takes the heading's text rather than the line, because YAML
    reads an unquoted ``## Review complete`` as a comment and the input would
    then be empty with nothing saying so. A heading that spans lines, or that
    starts with ``#`` and so writes a deeper heading, could never match the
    way its caller meant, so the run refuses it before reading anything.
    """
    if not heading:
        return None
    if "\n" in heading or "\r" in heading:
        raise BoardError(f"the review heading {heading!r} spans more than one line")
    if heading.startswith("#"):
        raise BoardError(f"the review heading {heading!r} starts with #, so name it without its ##")
    return re.compile(r"\A## " + re.escape(heading) + r"\r?(?:\n|\Z)")


def review_words(heading: str) -> tuple[str, str]:
    """What the card's line prints for a pull request reviewed and not, under a heading.

    ``Review complete`` gives ``review complete`` and ``no Review complete
    marker since the head commit``. There is no in-progress wording, because a
    review that has not posted its heading reads the same whoever holds the
    card.
    """
    return heading[:1].lower() + heading[1:], f"no {heading} marker since the head commit"


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def review_complete(
    entries: list[dict],
    rule: re.Pattern[str],
    stamp_field: str | None = None,
    head_date: datetime | None = None,
) -> bool:
    """Whether the owner posted an entry opening with ``rule``, after the head when timed.

    Every review rule reads only the owner's entries, because anyone can
    comment on a public repository. With no ``stamp_field`` the entry counts
    whenever it was posted, which is the rule with no caller's heading. With
    one, it counts only when posted after ``head_date``. A comment's time is
    its ``createdAt`` and a submitted review's its ``submittedAt``. A review
    still pending has no ``submittedAt``, and a head commit with no
    ``committedDate`` cannot be compared, so either reads as no review.

    The time check has one gap. ``committedDate`` is when the commit says it
    was made, which whoever makes it sets, and not when it was pushed. So a
    commit made before the heading, or dated before it on purpose, and pushed
    after it reads as reviewed. Sessions post the heading after their last
    push, which is what closes the gap for a comment. A submitted review names
    the commit it reviewed, so ``pr_items`` counts only a review of the head.
    """
    for entry in entries:
        if entry.get("authorAssociation") != "OWNER":
            continue
        if not rule.match(entry.get("body") or ""):
            continue
        if stamp_field is None:
            return True
        posted = _when(entry.get(stamp_field))
        if posted is not None and head_date is not None and posted > head_date:
            return True
    return False


# The file the board's own runs come from. The shared workflow already reads
# the caller's board under this path, for its sparse checkout and its cron
# line. A pull_request_target run attaches its check runs to the pull request's
# head, so a reviewed branch would read as still running while the board
# rebuilds, and a failed board run as a failed check. The check runs' names do
# not say where they came from: the same file's jobs have been named
# `board / build`, `build` and `board-build`, and a CI job may be named
# `board / build` too. The workflow file names the source exactly.
BOARD_WORKFLOW = ".github/workflows/board.yml"


def settled(settled_rollup: str) -> bool:
    """Whether the caller asked for a settled rollup, refusing any other value."""
    if settled_rollup not in ("", "true"):
        raise BoardError(f"settled-rollup takes true or nothing, not {settled_rollup!r}")
    return settled_rollup == "true"


# The lines and labels a session sets for the judgement the page draws. Each
# line is anchored at the start of a line, so prose quoting one mid-sentence is
# not one. A verdict reads "Board verdict: build after 5 passes", or "decide"
# for a loop that ended on a question only the owner can answer.
VERDICT = re.compile(
    r"^[ \t]*Board verdict: (build|decide) after (\d+) pass(?:es)?\.?[ \t]*$", re.MULTILINE
)
ORDER = re.compile(r"^[ \t]*Board order: (-?\d+(?:\.\d+)?)[ \t]*$", re.MULTILINE)
AFTER = re.compile(r"^[ \t]*Board after:(.*)$", re.MULTILINE)
BAND = re.compile(r"^band:(\d+)$")
WORKING = {"working:build": "build", "working:decompose": "decompose"}

# A fenced code block, opened by three or more backticks or tildes and closed
# by the same run, or left open to the end of the text. A comment quoting the
# verdict format inside a fence would otherwise read as a verdict.
FENCE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)", re.MULTILINE | re.DOTALL
)


def unfenced(text: str) -> str:
    """The text with every fenced code block removed, so no line in one is read."""
    return FENCE.sub("", text)


# A run of backticks, which opens an inline code span, and the blank line that
# ends a paragraph. A span closes only at the next run of exactly as many
# backticks inside the same paragraph, and a run nothing closes is literal
# text. That approximates CommonMark rather than implementing it. Only a blank
# line ends a paragraph here, so a heading or a list item with no blank line
# after it is no boundary, and a backslash-escaped backtick still opens a span.
# In those rare shapes a stray backtick pairs with the wrong partner. A span
# can then run on and swallow a reference, or close early and leave a quoted
# one outside code, so the approximation can drop a reference or credit one.
TICKS = re.compile(r"`+")
PARAGRAPH = re.compile(r"\n[ \t]*\n")


def _spans_out(paragraph: str) -> str:
    """One paragraph with each code span replaced by a NUL character."""
    kept, start, pos = [], 0, 0
    while opener := TICKS.search(paragraph, pos):
        width = len(opener.group())
        closer = next(
            (m for m in TICKS.finditer(paragraph, opener.end()) if len(m.group()) == width), None
        )
        if closer is None:
            pos = opener.end()
            continue
        kept.append(paragraph[start : opener.start()])
        start = pos = closer.end()
    kept.append(paragraph[start:])
    # A NUL rather than nothing or a space. Nothing would join the text either
    # side of a span, so "Part`x`of #482" would read as the phrase although
    # GitHub shows code between the words, and a space would do the same. A
    # NUL is no word character, so `\b` still matches beside it, and it is not
    # the space the phrase needs, so it can never complete "Part of #".
    return "\0".join(kept)


def outside_code(text: str) -> str:
    """The text with every fenced code block and inline code span removed.

    GitHub does not read a closing keyword written inside either, so a ``Part
    of`` reference written inside one does not count here either.
    """
    # GitHub's web editor saves `\r\n`, which the fence's `$` and the blank
    # line between paragraphs would otherwise never match.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n\n".join(_spans_out(p) for p in PARAGRAPH.split(unfenced(text)))


# Which label sets a card's kind, in the order that wins when an issue carries
# more than one. A parent is read from sub-issues instead, ahead of both. Only
# kinds every repository calling the shared workflow uses are here, and a
# repository that needs another adds it as an input to the workflow.
KIND_LABELS = (("deferred", "deferred"), ("decision", "decision"))


def kind_labels(data_label: str) -> tuple[tuple[str, str], ...]:
    """The kind labels a run reads, with the caller's data label first if it names one.

    A card waiting on data that has to be bought or captured takes the kind
    ``data`` ahead of ``deferred`` and ``decision``, because no session's time
    frees it, whatever else is said about it. Only a repository that names the
    label reads the kind, so an empty one leaves ``KIND_LABELS`` as it is. A
    label the board already reads for something else would be read twice, and
    every card carrying it would report a conflict, so the run refuses it.
    """
    if not data_label:
        return KIND_LABELS
    taken = {label for label, _ in KIND_LABELS} | set(WORKING)
    if data_label in taken or BAND.match(data_label):
        raise BoardError(f"the data label {data_label!r} is a label the board already reads")
    return ((data_label, "data"), *KIND_LABELS)


# GitHub reports a check as an uppercase enum, and the page knows five
# lowercase words, of which this map writes four. Passed through as they come,
# every state reads as green, because the page counted only `failure`,
# `running` and `neutral`. So each state is mapped, and each failure-like one
# is `failure`. A check run that has
# not completed is `running` whatever its conclusion field says.
CHECK_WORD = {
    # Check run conclusions.
    "SUCCESS": "success",
    "NEUTRAL": "neutral",
    "SKIPPED": "neutral",
    "STALE": "neutral",
    "FAILURE": "failure",
    "TIMED_OUT": "failure",
    "CANCELLED": "failure",
    "ACTION_REQUIRED": "failure",
    "STARTUP_FAILURE": "failure",
    # Status context states. `SUCCESS` and `FAILURE` are shared with the above.
    "ERROR": "failure",
    "PENDING": "running",
    "EXPECTED": "running",
}

# The words under a settled rollup. A skipped job is one whose condition kept
# it from running, such as a job that runs only on the default branch, and the
# page reads `skipped` as settled where it reads `neutral` as neither way. A
# cancelled run and one waiting on an action read as neither way rather than
# as failures, as l3a0/marketlake's board read them. Every other state reads
# as above.
SETTLED_CHECK_WORD = {
    **CHECK_WORD,
    "SKIPPED": "skipped",
    "CANCELLED": "neutral",
    "ACTION_REQUIRED": "neutral",
}

PAGE_INFO = "pageInfo{hasNextPage endCursor}"

# What a submitted review is read for, and what a check run adds for the
# workflow file it came from. Each is selected only for a caller that sets the
# input reading it. A caller that sets neither sends the query it sent before
# either input existed, so it pays no point for them, and a field its token
# cannot read cannot stop its board.
REVIEW_SELECTION = "authorAssociation body submittedAt commit{oid}"
RUN_FILE = "checkSuite{workflowRun{file{path}}}"


def pr_fields(heading: bool = False, settle: bool = False) -> str:
    """The pull request fragment, with what ``review-heading`` and ``settled-rollup`` read."""
    comment = " createdAt" if heading else ""
    reviews = (
        f"\n  reviews(first:100){{{PAGE_INFO} nodes{{{REVIEW_SELECTION}}}}}" if heading else ""
    )
    head = "oid committedDate " if heading else ""
    run = f" {RUN_FILE}" if settle else ""
    return f"""
fragment pr on PullRequest {{
  id number state body isCrossRepository
  closingIssuesReferences(first:100){{{PAGE_INFO} nodes{{number repository{{nameWithOwner}}}}}}
  comments(first:100){{{PAGE_INFO} nodes{{authorAssociation body{comment}}}}}{reviews}
  commits(last:1){{nodes{{commit{{{head}statusCheckRollup{{id
    contexts(first:100){{{PAGE_INFO} nodes{{__typename
      ... on CheckRun{{name status conclusion{run}}}
      ... on StatusContext{{context state}}}}}}}}}}}}}}
}}
"""


PR_FIELDS = pr_fields()

ISSUES_QUERY = f"""
query($owner:String!, $name:String!, $after:String) {{
  rateLimit{{cost}}
  repository(owner:$owner, name:$name) {{
    issues(states:OPEN, first:100, after:$after, orderBy:{{field:CREATED_AT, direction:ASC}}) {{
      totalCount {PAGE_INFO}
      nodes {{
        id number title body
        milestone{{title}}
        labels(first:100){{{PAGE_INFO} nodes{{name}}}}
        blockedBy(first:100){{{PAGE_INFO} nodes{{number state repository{{nameWithOwner}}}}}}
        subIssues{{totalCount}}
        issueComments: comments(first:100){{{PAGE_INFO} nodes{{authorAssociation body}}}}
        closedByPullRequestsReferences(first:100, includeClosedPrs:true){{
          {PAGE_INFO} nodes{{number repository{{nameWithOwner}}}}}}
        timelineItems(itemTypes:[CROSS_REFERENCED_EVENT], first:100){{{PAGE_INFO} nodes{{
          ... on CrossReferencedEvent{{source{{
            ... on PullRequest{{number repository{{nameWithOwner}}}}}}}}}}}}
      }}
    }}
  }}
}}
"""


def open_prs_query(fields: str = PR_FIELDS) -> str:
    """The query for the open pull requests, with the fragment ``fields`` gives."""
    return f"""
query($owner:String!, $name:String!, $after:String) {{
  rateLimit{{cost}}
  repository(owner:$owner, name:$name) {{
    pullRequests(states:OPEN, first:50, after:$after) {{
      totalCount {PAGE_INFO}
      nodes{{...pr}}
    }}
  }}
}}
{fields}
"""


OPEN_PRS_QUERY = open_prs_query()

# Pull requests fetched by number, for the merged and closed ones an open issue
# still names. Fifty a query keeps one response small.
BATCH = 50

# How the nested lists that can outgrow one page are read again from where the
# first page stopped. Each is keyed by the name the response carries it under,
# and names the type that holds the list, the field that name stands for, the
# list's arguments and what to select from each entry. An issue's comments and
# a pull request's are both `comments` on GitHub, so the issue's go under an
# alias to keep the two apart.
NESTED = {
    "labels": ("Issue", "labels", "", "name"),
    "blockedBy": ("Issue", "blockedBy", "", "number state repository{nameWithOwner}"),
    "issueComments": ("Issue", "comments", "", "authorAssociation body"),
    "closedByPullRequestsReferences": (
        "Issue",
        "closedByPullRequestsReferences",
        "includeClosedPrs:true",
        "number repository{nameWithOwner}",
    ),
    "timelineItems": (
        "Issue",
        "timelineItems",
        "itemTypes:[CROSS_REFERENCED_EVENT]",
        "... on CrossReferencedEvent{source{... on PullRequest{number repository{nameWithOwner}}}}",
    ),
    "closingIssuesReferences": (
        "PullRequest",
        "closingIssuesReferences",
        "",
        "number repository{nameWithOwner}",
    ),
    "comments": ("PullRequest", "comments", "", "authorAssociation body"),
    "reviews": ("PullRequest", "reviews", "", REVIEW_SELECTION),
    "contexts": (
        "StatusCheckRollup",
        "contexts",
        "",
        "__typename ... on CheckRun{name status conclusion} ... on StatusContext{context state}",
    ),
}


def nested(heading: bool = False, settle: bool = False) -> dict:
    """``NESTED`` with what each input reads on a later page, as ``pr_fields`` selects it."""
    table = dict(NESTED)
    if heading:
        table["comments"] = ("PullRequest", "comments", "", "authorAssociation body createdAt")
    if settle:
        table["contexts"] = (
            "StatusCheckRollup",
            "contexts",
            "",
            f"__typename ... on CheckRun{{name status conclusion {RUN_FILE}}}"
            " ... on StatusContext{context state}",
        )
    return table


Gql = Callable[[str, dict], dict]

# How many reads of one list, each from its first page, it takes for a count that
# disagrees to stop the run. An issue filed or a pull request opened between two
# pages makes one read disagree, and the next read usually finds it unchanged.
# Each read starts at once, because the list need only hold still while one
# read runs.
LIST_READS = 3


# A call `gh` reports as a server error, as `gh: HTTP 504` or, when the body
# carries a top-level message, as that message followed by `(HTTP 502)`. Or a
# call that never got an answer, which `gh` prints as `error connecting to
# <host>` or as Go's `Post "https://...": <cause>`. A 4xx such as
# `gh: Bad credentials (HTTP 401)` and a GraphQL error such as
# `gh: Field 'x' doesn't exist` match none of these, because trying them again
# gets the same answer. GitHub's GraphQL timeout also arrives as an entry in
# the body's `errors` list, which `gh` prints with no status, so it fails at
# once too. None of the failed runs on record when this was written showed it.
TRANSIENT = re.compile(
    r'^(?:gh: (?:HTTP 5\d\d\b|.*\(HTTP 5\d\d\)$)|error connecting to |Post "https?://)',
    re.MULTILINE,
)

# Seconds to wait before each further attempt at a call that failed with one
# of those, so a call gets three attempts. GitHub stops a GraphQL query at 10
# seconds and answers 502 or 504, so a call that keeps timing out costs about
# 11 seconds an attempt, and three of them stay well inside the job's
# `timeout-minutes`.
RETRY_WAITS = (5, 20)


class BoardError(RuntimeError):
    """A read that cannot be trusted, which stops the run."""


class GhGraphql:
    """Runs GraphQL through ``gh api graphql`` and counts what it spends.

    Every attempt is one request, and ``retries`` counts the attempts made
    after a server or connection error. ``cost`` sums the points GitHub
    charged, read from the ``rateLimit`` field each top-level query asks for.
    """

    def __init__(self) -> None:
        self.requests = 0
        self.retries = 0
        self.cost = 0

    def __call__(self, query: str, variables: dict) -> dict:
        args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            if value is None:
                continue
            flag = "-F" if isinstance(value, int) else "-f"
            args += [flag, f"{key}={value}"]
        for wait in (*RETRY_WAITS, None):
            self.requests += 1
            done = subprocess.run(args, capture_output=True, text=True, check=False)
            if done.returncode == 0 or wait is None or not TRANSIENT.search(done.stderr):
                break
            self.retries += 1
            print(
                f"build_board: {done.stderr.strip().splitlines()[0]}, trying again in {wait} s",
                file=sys.stderr,
            )
            time.sleep(wait)
        if done.returncode != 0:
            raise BoardError(f"gh api graphql failed: {done.stderr.strip() or done.stdout}")
        try:
            body = json.loads(done.stdout)
        except json.JSONDecodeError as e:
            raise BoardError(f"gh api graphql returned no JSON: {e}") from e
        if body.get("errors"):
            raise BoardError(f"GraphQL errors: {json.dumps(body['errors'])}")
        data = body.get("data")
        if not isinstance(data, dict):
            raise BoardError("GraphQL returned no data")
        self.cost += int((data.get("rateLimit") or {}).get("cost") or 0)
        return data


def _all_nodes(gql: Gql, node_id: str, field: str, conn: dict, table: dict = NESTED) -> list:
    """Every entry of a nested list, reading further pages as ``table`` says."""
    nodes = list(conn["nodes"])
    page = conn["pageInfo"]
    typename, real, args, selection = table[field]
    head = f"{args}, " if args else ""
    while page["hasNextPage"]:
        query = (
            "query($id:ID!, $after:String) { node(id:$id) { ... on "
            f"{typename} {{ {field}: {real}({head}first:100, after:$after) "
            f"{{ {PAGE_INFO} nodes{{ {selection} }} }} }} }} }}"
        )
        data = gql(query, {"id": node_id, "after": page["endCursor"]})
        node = data.get("node")
        if not node or field not in node:
            raise BoardError(f"{typename} {node_id} vanished while reading its {field}")
        conn = node[field]
        nodes += conn["nodes"]
        page = conn["pageInfo"]
    return nodes


def _top_pages(gql: Gql, query: str, owner: str, name: str, field: str) -> list[dict]:
    """Every node of a repository-level list, checked against its total."""
    for attempt in range(1, LIST_READS + 1):
        nodes: list[dict] = []
        after = None
        total = None
        while True:
            data = gql(query, {"owner": owner, "name": name, "after": after})
            conn = data["repository"][field]
            if total is None:
                total = conn["totalCount"]
            nodes += conn["nodes"]
            if not conn["pageInfo"]["hasNextPage"]:
                break
            after = conn["pageInfo"]["endCursor"]
        # A list that changed between pages reads more or fewer entries than its
        # count, and the count is the only sign of it. So the loop reads the whole
        # list again from its first page, and a list that disagrees on every read
        # stops the run. GitHub's pages continue after the last entry read, so a
        # change cannot repeat one, and the check on distinct numbers guards
        # against a page that repeats one anyway.
        if len(nodes) == total and len({n["number"] for n in nodes}) == total:
            return nodes
        if attempt < LIST_READS:
            print(
                f"build_board: read {len(nodes)} {field} against a total of {total}, "
                f"reading the list again (read {attempt + 1} of {LIST_READS})",
                file=sys.stderr,
            )
    raise BoardError(f"read {len(nodes)} {field} against a total of {total} on {LIST_READS} reads")


def card_kinds(
    labels: list[str], sub_issues: int, kinds_read: tuple[tuple[str, str], ...] = KIND_LABELS
) -> list[str]:
    """Every kind an issue's sub-issues and labels claim, the winning one first.

    An issue with any sub-issue is a parent, whether or not its children have
    closed, because they carry its work. After that the kind labels follow in
    the order ``kind_labels`` gives. More than one entry is a conflict the run
    reports.
    """
    kinds = ["parent"] if sub_issues else []
    return kinds + [kind for label, kind in kinds_read if label in labels]


def card_kind(
    labels: list[str], sub_issues: int, kinds_read: tuple[tuple[str, str], ...] = KIND_LABELS
) -> str:
    """A card's kind, the first that ``card_kinds`` finds, or ready for none."""
    return (card_kinds(labels, sub_issues, kinds_read) or ["ready"])[0]


def check_word(context: dict, unknown: set[str], words: dict[str, str] = CHECK_WORD) -> str:
    """The page's word for one check run or status context, from ``words``."""
    if context.get("__typename") == "CheckRun":
        if context.get("status") != "COMPLETED":
            return "running"
        state = context.get("conclusion")
    else:
        state = context.get("state")
    word = words.get(state or "")
    if word is None:
        # A state GitHub adds later is reported neither way rather than as a
        # pass, and the job summary names it so the map can learn it.
        unknown.add(str(state))
        return "neutral"
    return word


def is_board_check(context: dict) -> bool:
    """Whether a check run came from the board's own workflow file."""
    run = ((context.get("checkSuite") or {}).get("workflowRun") or {}).get("file") or {}
    return context.get("__typename") == "CheckRun" and run.get("path") == BOARD_WORKFLOW


def _rollup(gql: Gql, pr: dict, unknown: set[str], settle: bool = False) -> list[list[str]]:
    """The head's checks as ``[name, word]`` pairs, in GitHub's order.

    Under ``settle`` the board's own checks are left out, the words come from
    ``SETTLED_CHECK_WORD``, and the pairs are sorted by name, then word.
    """
    commits = pr["commits"]["nodes"]
    rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
    if not rollup:
        return []
    contexts = _all_nodes(gql, rollup["id"], "contexts", rollup["contexts"], nested(settle=settle))
    words = SETTLED_CHECK_WORD if settle else CHECK_WORD
    out = []
    for c in contexts:
        if settle and is_board_check(c):
            continue
        label = c.get("name") if c.get("__typename") == "CheckRun" else c.get("context")
        out.append([str(label), check_word(c, unknown, words)])
    return sorted(out) if settle else out


def in_repo(node: dict | None, repo: str) -> bool:
    """Whether an issue or pull request GitHub listed belongs to ``repo``.

    A closing link, a cross-reference or a "blocked by" link can name an issue
    or pull request in another repository, whose number means nothing here.
    Read as this repository's, it would fetch an unrelated pull request of the
    same number, stop the run when there is none, or draw a branch on the
    wrong card.

    A null entry, or one with no repository, reads as another repository's.
    That does not break the rule that the run fails closed. ``GhGraphql``
    stops the run on any response carrying GraphQL errors, so a null here is
    one GitHub sent with no error, an entry the token cannot read. The build
    job's token reads every issue and pull request in the caller's repository,
    so such an entry is never this repository's, and dropping it loses
    nothing from the board.
    """
    return bool(node) and (node.get("repository") or {}).get("nameWithOwner") == repo


def pr_items(
    gql: Gql,
    pr: dict,
    open_issues: set[int],
    repo: str,
    unknown: set[str],
    working: frozenset[int] = frozenset(),
    *,
    review_heading: str = "",
    settled_rollup: str = "",
) -> list[dict]:
    """One item per open issue the pull request names, or none at all.

    A pull request names an issue through a closing link to an issue in this
    repository, or through a ``Part of`` reference anywhere in its body outside
    a code span or a fenced code block. One that names no open issue gets no
    item, because a branch with no card has nowhere to be drawn and a null
    issue would make the page refuse the whole section. One that closes two
    issues gets two items, because the page keys pull requests by issue.

    A pull request opened from a fork gets no item either. Anyone can open one
    on a public repository, and its ``Part of`` reference or closing keyword
    would otherwise draw a branch on the card and take it off the free list.
    Reading the author's association instead would drop Dependabot, which
    GitHub marks ``CONTRIBUTOR``, so the test is where the branch lives.

    ``linked`` is always the opposite of ``partOf`` here, because an issue
    named only by a ``Part of`` reference is the one case with no closing link.
    So the page carries no warning about a closing link GitHub did not
    register, since it could never fire. A pull request whose keyword sits in
    a code span names no issue GitHub can see, and gets no item at all.

    ``review`` is the word the card's line prints. With no review posted it
    says one is in progress while a session holds the card, which ``working``
    names, and that none is posted otherwise.

    ``review_heading``, when named, replaces that rule. The pull request is
    reviewed when an owner's comment or submitted review opens with the whole
    line ``## <heading>`` and was posted after the head commit, as
    ``review_complete`` reads it, and ``review`` takes ``review_words``.
    ``settled_rollup`` set to ``true`` reads the checks as ``_rollup`` says.
    """
    if pr.get("isCrossRepository"):
        return []
    closing = {
        n["number"]
        for n in _all_nodes(gql, pr["id"], "closingIssuesReferences", pr["closingIssuesReferences"])
        if in_repo(n, repo)
    }
    part_of = {int(m) for m in PART_OF.findall(outside_code(pr.get("body") or ""))}
    named = sorted((closing | part_of) & open_issues)
    if not named:
        return []
    rule = review_rule(review_heading)
    table = nested(heading=rule is not None)
    comments = _all_nodes(gql, pr["id"], "comments", pr["comments"], table)
    if rule is None:
        reviewed = review_complete(comments, ANY_REVIEW)
    else:
        commits = pr["commits"]["nodes"]
        head = commits[0]["commit"] if commits else {}
        head_date = _when(head.get("committedDate"))
        # A review started on an older commit and submitted after a push
        # reviewed code the head no longer holds, so only a review of the head
        # itself counts.
        oid = head.get("oid")
        reviews = [
            r
            for r in _all_nodes(gql, pr["id"], "reviews", pr["reviews"], table)
            if oid is not None and (r.get("commit") or {}).get("oid") == oid
        ]
        reviewed = review_complete(comments, rule, "createdAt", head_date) or review_complete(
            reviews, rule, "submittedAt", head_date
        )
    state = {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}[pr["state"]]
    rollup = _rollup(gql, pr, unknown, settled(settled_rollup))
    items = []
    for issue in named:
        if rule is not None:
            done, owed = review_words(review_heading)
            review = done if reviewed else owed
        elif reviewed:
            review = "review posted"
        else:
            review = "review in progress" if issue in working else "no review posted"
        item = {
            "pr": pr["number"],
            "issue": issue,
            "state": state,
            # Never false without `partOf`, so the page does not read it, as
            # the docstring says. It is still written for anyone reading
            # board.json.
            "linked": issue in closing,
            "reviewed": reviewed,
            "review": review,
            "rollup": rollup,
        }
        if issue not in closing:
            item["partOf"] = True
        items.append(item)
    return items


def _referenced_prs(gql: Gql, issue: dict, repo: str) -> set[int]:
    """The pull requests in this repository that link to or mention an issue."""
    numbers = {
        n["number"]
        for n in _all_nodes(
            gql,
            issue["id"],
            "closedByPullRequestsReferences",
            issue["closedByPullRequestsReferences"],
        )
        if in_repo(n, repo)
    }
    for event in _all_nodes(gql, issue["id"], "timelineItems", issue["timelineItems"]):
        source = (event or {}).get("source")
        if in_repo(source, repo) and "number" in source:
            numbers.add(source["number"])
    return numbers


def _prs_by_number(
    gql: Gql, owner: str, name: str, numbers: list[int], fields: str = PR_FIELDS
) -> list[dict]:
    found = []
    for i in range(0, len(numbers), BATCH):
        chunk = numbers[i : i + BATCH]
        aliases = " ".join(f"p{n}: pullRequest(number:{n}){{...pr}}" for n in chunk)
        query = (
            "query($owner:String!, $name:String!) { rateLimit{cost} "
            f"repository(owner:$owner, name:$name) {{ {aliases} }} }}\n{fields}"
        )
        data = gql(query, {"owner": owner, "name": name})
        for n in chunk:
            pr = data["repository"].get(f"p{n}")
            if pr is None:
                raise BoardError(f"pull request {n} could not be read")
            found.append(pr)
    return found


def tracker_card(
    gql: Gql,
    issue: dict,
    names: list[str],
    open_issues: set[int],
    repo: str,
    conflicts: list[str],
    kinds_read: tuple[tuple[str, str], ...] = KIND_LABELS,
) -> dict:
    """One open issue as the card the page draws.

    A blocker that has closed no longer holds the card, and a number that is
    no open issue has no card to draw, so ``needs`` and ``after`` keep only open
    issues. A "blocked by" link can name an issue in another repository, whose
    number means nothing here, so it is dropped too. ``after`` is left out when
    it names none, as the page reads it as optional. The board's own labels are
    drawn as the rank chip and the busy stripe, so they are left off the card's
    label chips. An issue claiming two kinds takes the first and is reported.
    """
    n = issue["number"]
    blockers = _all_nodes(gql, issue["id"], "blockedBy", issue["blockedBy"])
    kinds = card_kinds(names, issue["subIssues"]["totalCount"], kinds_read)
    if len(kinds) > 1:
        conflicts.append(f"#{n} reads as {' and '.join(kinds)}, read as {kinds[0]}")
    card = {
        "n": n,
        "ms": (issue.get("milestone") or {}).get("title") or "",
        "label": issue["title"],
        "kind": (kinds or ["ready"])[0],
        "needs": sorted(
            {b["number"] for b in blockers if in_repo(b, repo) and b["state"] == "OPEN"}
            & open_issues
        ),
        "labels": [x for x in names if not BAND.match(x) and x not in WORKING],
    }
    lines = AFTER.findall(unfenced(issue.get("body") or ""))
    after = {int(m) for line in lines for m in re.findall(r"#(\d+)\b", line)}
    after = sorted((after & open_issues) - {n})
    if after:
        card["after"] = after
    return card


def latest_verdict(comments: list[dict]) -> tuple[str, int] | None:
    """The newest decompose verdict among the owner's comments on an issue.

    A loop run again on the same issue writes a new verdict, so the last one
    wins. GitHub lists comments oldest first.
    """
    found = None
    for c in comments:
        if c.get("authorAssociation") != "OWNER":
            continue
        for ready, passes in VERDICT.findall(unfenced(c.get("body") or "")):
            found = (ready, int(passes))
    return found


def rank_entry(
    n: int,
    names: list[str],
    body: str,
    kind: str,
    verdict: tuple[str, int] | None,
    conflicts: list[str],
) -> dict | None:
    """The card's place in the priority order, or None when it has none.

    ``ready`` has no home of its own. A finished plan says whether it is ready
    to build or waits on the owner, a card whose kind is a decision waits on
    the owner, and any other card still needs a plan.
    """
    bands = sorted(int(m.group(1)) for x in names if (m := BAND.match(x)))
    if not bands:
        return None
    if len(bands) > 1:
        conflicts.append(f"#{n} carries {len(bands)} band labels, read as band:{bands[0]}")
    entry: dict = {
        "issue": n,
        "band": bands[0],
        "ready": verdict[0] if verdict else ("decide" if kind == "decision" else "plan"),
    }
    orders = ORDER.findall(unfenced(body))
    if orders:
        if len(set(orders)) > 1:
            conflicts.append(f"#{n} carries {len(orders)} order lines, read as {orders[0]}")
        value = float(orders[0])
        entry["order"] = int(value) if value.is_integer() else value
    return entry


# Minutes added to the longest gap between two scheduled runs before the page
# calls the board stale. GitHub's documentation says only that a scheduled run
# "can be delayed during periods of high loads" and that its queued jobs "may
# be dropped", and bounds neither. One measurement put the longest gap between
# two scheduled runs at 603 minutes over 185 hours, with the schedule firing in
# about 11% of its slots, so the allowance is ten hours and no gap measured
# there would read as a failing Action. An allowance of 60 would have called a
# healthy board stale 45% of that time, and twice the gap assumes the schedule
# runs on time.
SCHEDULE_DELAY_ALLOWANCE = 600


def longest_gap_minutes(workflow: Path) -> int:
    """The longest gap between two scheduled runs, read from the workflow.

    It is read from the cron line rather than written beside it, because a
    second copy of the interval drifts the first time the schedule changes.
    Only the forms the workflow uses are understood: a minute list or step,
    with every other field ``*``. Anything else stops the run rather than
    guessing.
    """
    crons = re.findall(r"""^\s*-\s*cron:\s*["']([^"']+)["']""", workflow.read_text(), re.M)
    if len(crons) != 1:
        raise BoardError(f"{workflow} carries {len(crons)} cron lines, expected 1")
    fields = crons[0].split()
    if len(fields) != 5 or any(f != "*" for f in fields[1:]):
        raise BoardError(f"cron {crons[0]!r} is not an hourly minute list")
    minute = fields[0]
    if minute.startswith("*/"):
        minutes = list(range(0, 60, int(minute[2:])))
    else:
        minutes = sorted({int(m) for m in minute.split(",")})
    if not minutes or any(not 0 <= m < 60 for m in minutes):
        raise BoardError(f"cron {crons[0]!r} has no usable minutes")
    gaps = [(b - a) for a, b in zip(minutes, minutes[1:], strict=False)]
    gaps.append(minutes[0] + 60 - minutes[-1])
    return max(gaps)


def stale_after_minutes(longest_gap: int) -> int:
    """The age in minutes past which the page calls the board stale.

    ``longest_gap`` is the longest gap between two scheduled runs. The
    threshold adds ``SCHEDULE_DELAY_ALLOWANCE`` to it, so a run GitHub starts
    late or drops does not read as a failing Action.
    """
    return longest_gap + SCHEDULE_DELAY_ALLOWANCE


def build(
    gql: Gql,
    repo: str,
    longest_gap: int,
    now: datetime,
    title: str = "",
    data_label: str = "",
    *,
    review_heading: str = "",
    settled_rollup: str = "",
) -> tuple[dict, dict]:
    """The board, and what the job summary reports about the read.

    ``longest_gap`` is the longest gap in minutes between two scheduled runs,
    which ``longest_gap_minutes`` reads from the workflow. ``title`` heads the
    page, and an empty one gives ``<name> build board``. The repository goes
    into the board too, because the page builds every issue and pull request
    link from it and names no repository of its own. ``data_label`` is the
    label that marks a card waiting on data, and an empty one reads no such
    kind. ``review_heading`` names the heading that closes a review, and
    ``settled_rollup`` set to ``true`` settles the rollup, as ``pr_items``
    says. An empty one keeps the rule from before either existed. All three
    are checked before anything is read from GitHub.
    """
    kinds_read = kind_labels(data_label)
    fields = pr_fields(review_rule(review_heading) is not None, settled(settled_rollup))
    owner, name = repo.split("/", 1)
    issues = _top_pages(gql, ISSUES_QUERY, owner, name, "issues")
    open_issues = {i["number"] for i in issues}

    tracker = []
    working = []
    planned = []
    ranked = []
    conflicts: list[str] = []
    data_carried = 0
    referenced: set[int] = set()
    for issue in sorted(issues, key=lambda i: i["number"]):
        n = issue["number"]
        names = [lb["name"] for lb in _all_nodes(gql, issue["id"], "labels", issue["labels"])]
        card = tracker_card(gql, issue, names, open_issues, repo, conflicts, kinds_read)
        data_carried += bool(data_label) and data_label in names
        tracker.append(card)

        held = [WORKING[x] for x in names if x in WORKING]
        if held:
            if len(held) > 1:
                conflicts.append(f"#{n} carries both working labels, read as build")
            working.append({"n": n, "kind": "build" if "build" in held else held[0]})

        comments = _all_nodes(gql, issue["id"], "issueComments", issue["issueComments"])
        verdict = latest_verdict(comments)
        if verdict:
            planned.append({"n": n, "passes": verdict[1], "ready": verdict[0]})

        entry = rank_entry(n, names, issue.get("body") or "", card["kind"], verdict, conflicts)
        if entry:
            ranked.append(entry)

        referenced |= _referenced_prs(gql, issue, repo)

    open_prs = _top_pages(gql, open_prs_query(fields), owner, name, "pullRequests")
    seen = {p["number"] for p in open_prs}
    others = _prs_by_number(gql, owner, name, sorted(referenced - seen), fields)

    unknown: set[str] = set()
    prs = []
    left_out = []
    busy = frozenset(w["n"] for w in working)
    for pr in open_prs + others:
        items = pr_items(
            gql,
            pr,
            open_issues,
            repo,
            unknown,
            busy,
            review_heading=review_heading,
            settled_rollup=settled_rollup,
        )
        if not items and pr["state"] == "OPEN":
            left_out.append(pr["number"])
        prs += items
    prs.sort(key=lambda p: (p["issue"], p["pr"]))

    board = {
        "state": {
            "schema": SCHEMA,
            "repo": repo,
            "title": title or f"{name} build board",
            "updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "issues": {"open": len(issues)},
            "source": "github",
            "longestGapMinutes": longest_gap,
            "staleAfterMinutes": stale_after_minutes(longest_gap),
        },
        "prs": {"schema": SCHEMA, "items": prs},
        "working": {"schema": SCHEMA, "items": working},
        "planned": {"schema": SCHEMA, "items": planned},
        "next": {"schema": SCHEMA, "items": ranked},
        "tracker": {"schema": SCHEMA, "items": tracker},
    }
    report = {
        "open_issues": len(issues),
        "open_prs": len(open_prs),
        "other_prs_read": len(others),
        "pr_items": len(prs),
        "open_prs_left_out": sorted(left_out),
        "unknown_check_states": sorted(unknown),
        "label_conflicts": conflicts,
        "data_label": data_label,
        "data_carried": data_carried,
        "review_heading": review_heading,
        "reviewed_items": sum(p["reviewed"] for p in prs),
    }
    return board, report


def _summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines) + "\n"
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def _output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def cmd_build(args: argparse.Namespace) -> None:
    gql = GhGraphql()
    now = datetime.now(UTC)
    board, report = build(
        gql,
        args.repo,
        longest_gap_minutes(Path(args.workflow)),
        now,
        args.title,
        args.data_label,
        review_heading=args.review_heading,
        settled_rollup=args.settled_rollup,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "board.json").write_text(
        json.dumps(board, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    updated = board["state"]["updatedAt"]
    _output("updated_at", updated)
    _summary(
        [
            "## Board build",
            "",
            "| Measure | Value |",
            "| --- | --- |",
            f"| GitHub read at | {updated} |",
            f"| GraphQL requests | {gql.requests} |",
            f"| GraphQL requests tried again after a server or connection error | {gql.retries} |",
            f"| GraphQL points | {gql.cost} |",
            f"| Open issues | {report['open_issues']} |",
            f"| Open pull requests | {report['open_prs']} |",
            f"| Merged or closed pull requests read | {report['other_prs_read']} |",
            f"| Pull request items written | {report['pr_items']} |",
            "| Open pull requests naming no open issue | "
            f"{', '.join(f'#{n}' for n in report['open_prs_left_out']) or 'none'} |",
            "| Check states mapped to neither way | "
            f"{', '.join(report['unknown_check_states']) or 'none'} |",
            f"| Labels or lines that disagree | {'; '.join(report['label_conflicts']) or 'none'} |",
            # A misspelt data label matches nothing and fails no read, so the
            # count is what shows the caller's input reached the issues.
            "| Data label | "
            + (
                f"`{report['data_label']}` on {report['data_carried']} open issues"
                if report["data_label"]
                else "none named"
            )
            + " |",
            # A misspelt heading marks nothing reviewed and fails no read, so
            # the count is what shows it, as the data label's does.
            "| Review heading | "
            + (
                f"`## {report['review_heading']}` on {report['reviewed_items']} of "
                f"{report['pr_items']} pull request items"
                if report["review_heading"]
                else "none named"
            )
            + " |",
        ]
    )


def _get(url: str) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except Exception as e:
        return 0, {"error": str(e)}, b""


def _stamp(body: bytes) -> str | None:
    try:
        return json.loads(body)["state"]["updatedAt"]
    except Exception:
        return None


def cmd_measure(args: argparse.Namespace) -> None:
    """Record how long a run's board takes to reach a reader, and through what.

    Two numbers about a board's delivery need a deployed board, so this runs
    after every deploy and writes them to the job summary.

    1. The time from the run being created, which is when GitHub queued the
       event, to the new board being served.
    2. Whether a plain fetch gets past Pages' ``cache-control: max-age=600``,
       against a fetch carrying a query string as the page's own does.

    It never fails the run. A measurement that times out says so in the
    summary, and the board it measures is already deployed.
    """
    created = None
    done = subprocess.run(
        ["gh", "api", f"repos/{args.repo}/actions/runs/{args.run_id}", "--jq", ".created_at"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 0 and done.stdout.strip():
        created = datetime.fromisoformat(done.stdout.strip().replace("Z", "+00:00"))
    base = args.page_url if args.page_url.endswith("/") else args.page_url + "/"
    start = time.monotonic()
    busted_at = None
    while time.monotonic() - start < args.wait:
        _, _, body = _get(f"{base}board.json?t={time.time_ns()}")
        if _stamp(body) == args.updated_at:
            busted_at = datetime.now(UTC)
            break
        time.sleep(5)
    status, headers, body = _get(f"{base}board.json")
    plain_new = _stamp(body) == args.updated_at
    lines = ["## Board delivery", "", "| Measure | Value |", "| --- | --- |"]
    lines.append(f"| Run created | {created.isoformat() if created else 'unknown'} |")
    lines.append(f"| Board built from GitHub at | {args.updated_at} |")
    if busted_at and created:
        secs = round((busted_at - created).total_seconds())
        lines.append(f"| Created to served, with a query string | {secs} s |")
    else:
        lines.append(
            f"| Created to served, with a query string | not served within {args.wait} s |"
        )
    lines.append(f"| Plain fetch served the new board | {'yes' if plain_new else 'no'} |")
    for key in ("cache-control", "age", "x-cache", "x-served-by"):
        value = next((v for k, v in headers.items() if k.lower() == key), "")
        lines.append(f"| Plain fetch `{key}` | {value or 'absent'} |")
    lines.append(f"| Plain fetch status | {status} |")
    _summary(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="read GitHub and write board.json")
    b.add_argument("--repo", required=True)
    b.add_argument("--workflow", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--title", default="", help="the page's heading, <name> build board if empty")
    b.add_argument(
        "--data-label", default="", help="the label marking a card waiting on data, none if empty"
    )
    b.add_argument(
        "--review-heading",
        default="",
        help="the heading, without its ##, that closes a review since the head commit",
    )
    b.add_argument(
        "--settled-rollup",
        default="",
        help="true to leave the board's own checks out and read skipped as settled",
    )
    b.set_defaults(func=cmd_build)
    m = sub.add_parser("measure", help="time how long a deployed board takes to be served")
    m.add_argument("--repo", required=True)
    m.add_argument("--run-id", required=True)
    m.add_argument("--page-url", required=True)
    m.add_argument("--updated-at", required=True)
    m.add_argument("--wait", type=int, default=60)
    m.set_defaults(func=cmd_measure)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except BoardError as e:
        print(f"build_board: {e}", file=sys.stderr)
        # A run that stops on its caller's own input stops the same way on
        # every run until someone edits the caller, so the reason goes where
        # the run's page shows it rather than only into the step log.
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            _summary(["## Board run failed", "", f"build_board: {e}"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
