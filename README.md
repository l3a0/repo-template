# repo-template

A starting point for a new repository: the agent instructions, the CI, and the
GitHub-side policy that the [marketlake](https://github.com/l3a0/marketlake)
and [trading-strategies](https://github.com/l3a0/trading-strategies)
repositories converged on, in one place a new repo can start from.

Those two repos grew the same rules twice, in different words, and drifted. One
example: they gave opposite committing instructions, because a directive
written to replace the other never reached the second repo. This template is
the merged version, so the next repo starts from the settled rule rather than
from whichever copy it was cloned off.

## What it carries

- **[CLAUDE.md](CLAUDE.md)** is the agent instruction file. Scope authority,
  how to rank work, plan audits, writing style, markdown hygiene, secrets,
  committing, pull request review and the build board. It has template slots,
  marked as HTML comments, for what only the new repo can say, such as its
  premise and what each band on its board means.
- **[.github/workflows/ci.yml](.github/workflows/ci.yml)** runs two jobs. `test`
  runs ruff, a format check, and pytest under uv. `docs` runs markdownlint.
  The ruleset requires both by name.
- **[.github/rulesets/default.json](.github/rulesets/default.json)** makes
  `main` require a pull request, a squash merge, linear history, CodeQL, and
  both status checks. It is the ruleset both sibling repos run, with the
  required checks retargeted and, since 2026-09-18, marketlake's setting for
  `strict_required_status_checks_policy` rather than trading-strategies'. It is
  off, so a branch merges without being brought current with `main` first.
  Requiring it stopped a green run computed against a stale merge ref from
  carrying a branch through, and it charged every open branch another round of
  checks whenever anything else merged. Re-reading a rollup once the base has
  moved, which `CLAUDE.md` already requires, covers the same failure on the
  branches where the base actually matters.
- **[.github/labels.json](.github/labels.json)** is the label set the triage
  rule in CLAUDE.md and the build board expect to exist.
- **[.github/dependabot.yml](.github/dependabot.yml)** groups minor and patch
  bumps, keeps majors separate, and keeps ruff on its own so a new lint rule
  never turns an unrelated pull request red.
- **[scripts/setup-repo.sh](scripts/setup-repo.sh)** applies the ruleset, the
  labels, CodeQL default setup, GitHub Pages and the `github-pages`
  environment to a repository. It is idempotent and takes `DRY_RUN=1`.
- **The build board** is a page on GitHub Pages saying what is in flight and
  what to take next, rebuilt from GitHub by a reusable workflow that every
  seeded repo calls. The section below explains it.
- **[docs/design.md](docs/design.md)** is the skeleton for the design doc
  CLAUDE.md refers to by name.
- **[docs/optional-policies.md](docs/optional-policies.md)** holds two policy
  modules that only some repos need, ready to move into CLAUDE.md.
- **[tests/test_markdown_hygiene.py](tests/test_markdown_hygiene.py)** runs the
  prose checks CLAUDE.md names, so they fail the suite rather than waiting
  for someone to remember the command.

## Starting a repo from it

```bash
gh repo create l3a0/new-repo --public --template l3a0/repo-template --clone
cd new-repo
scripts/setup-repo.sh l3a0/new-repo
```

Then do the six things nothing can guess.

1. Fill the premise slot at the top of `CLAUDE.md` and the premise section in
   `docs/design.md`. Every later ranking decision appeals to it, so it comes
   first.
2. Replace `README.md` wholesale. This one describes the template, not your
   project, and a seeded repo that keeps it tells its readers to create a repo
   from the repo they are already looking at.
3. Rename `src/project/`, and update `packages`, `name` and `description` in
   `pyproject.toml`.
4. Create the first slice on the tracker, in the three parts
   `docs/design.md`'s `## How work is cut and ordered` lists, and link its
   parent issue in that section's slot.
5. Decide on both modules in `docs/optional-policies.md`, move what applies
   into the **Repo-specific policy** heading in `CLAUDE.md`, and delete the
   file.
6. Pin the build board, delete the template's copy of it, and install the
   `l3a0` plugin, as the next section says.

Then check the work is finished. Every remaining hit is a slot nobody filled:

```bash
git grep -nE 'PROJECT_NAME|OWNER/REPO|TEMPLATE:|TODO|src/project'
```

## The build board

The board answers what is in flight and what to take next, from labels,
"blocked by" links and marker lines on GitHub, so no session writes it by
hand. It came from
[quantitative-trading](https://github.com/l3a0/quantitative-trading), which
built it first. One copy lives here rather than one per repo, because the
generator and the page run to about 2,900 lines that still change often, and
copies of them drift.

The pieces are these.

- **[.github/workflows/build-board.yml](.github/workflows/build-board.yml)** is
  the reusable workflow. It builds `board.json` with
  [scripts/build_board.py](scripts/build_board.py) and publishes it on Pages
  beside the page,
  [.claude/skills/update-build-board/board.html](.claude/skills/update-build-board/board.html).
  It checks both out from this repo at the commit the caller pinned. The page,
  its test stub and its icon stay in that folder although no skill lives there
  any more. The reusable workflow publishes the page and the icon from that
  path, and the plugin's harness fetches the page and the stub from it.
- **[.github/workflows/board.yml](.github/workflows/board.yml)** is the caller.
  It holds the triggers, the permissions and the concurrency group, and calls
  the reusable workflow. This repo calls it at `main`, so its own board runs
  the shared path first.
- **The two skills**, `update-build-board` and `sync-prune-next`, tell a
  session what to set on GitHub and how to read the board. They live in the
  [`l3a0` Claude Code plugin](https://github.com/l3a0/claude-plugins) from
  0.5.0 on, not in this repo. `CLAUDE.md`'s `## Keep the build board current`
  gives the commands that install it.

A seeded repo keeps only the caller, and runs everything else from here at the
commit it pins. So after seeding, pin the caller to a full commit SHA of this
repo's `main`, delete the template's copy of the board, and install the plugin
at 0.5.0 or later.

```bash
sha="$(gh api repos/l3a0/repo-template/commits/main --jq .sha)"
sed -i.bak "s#build-board.yml@main#build-board.yml@$sha#" .github/workflows/board.yml && rm .github/workflows/board.yml.bak
git rm -r .github/workflows/build-board.yml scripts/build_board.py \
  .claude/skills/update-build-board/board.html \
  .claude/skills/update-build-board/dom-stub.js \
  .claude/skills/update-build-board/favicon.ico \
  tests/test_build_board.py tests/test_build_board_generator.py \
  tests/fixtures/build_board
```

A seeded repository can give its board its own tab icon. Commit an `.ico`
file, for example at `.github/board/favicon.ico`, and name it in the caller's
job. Left out, the board shows the template's icon. The caller's pin has to
be at or after the template commit that added the `icon` input, because a
caller passing an input the called workflow does not declare fails.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      icon: .github/board/favicon.ico
```

A repository whose issues can wait on data that has to be bought or captured
can name the label it marks them with. Its cards then take the kind `data`
and draw in a fourth column, "Waiting on data", which the depth sentence
leaves out because no session's time frees them. Left out, the board reads no
such label and keeps three columns. The pin has to be at or after the
template commit that added the `data-label` input, for the reason the icon
gives.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      data-label: blocked-on-data
```

The run's job summary names the data label and counts the open issues
carrying it, so a misspelt label shows up as a count of zero. To move the pin
back before that commit, remove the `data-label` line in the same change.

A seeded repository can also give the board three lines of its own. Each
needs a pin at or after the template commit that added it, for the reason the
icon gives.

1. `subtitle` replaces the line under the heading, "what is in flight, and
   what to take next".
2. `note` adds one paragraph below the strip, such as a sentence pointing at
   the design doc. It is plain text, and `[words](https://...)` is its only
   markup. Runs of whitespace read as one space, so a folded `>-` block reads
   as written. Use one whenever the note holds a colon followed by a space,
   which a plain YAML value refuses. A link to anything but an `https://`
   address fails the run, and the job summary says why.
3. `default-branch-head`, set to `"true"`, names the commit the default branch
   stands at in the footer and in the "Live updates stopped" banner. It costs
   one more GraphQL request a run.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      subtitle: the order of work on the first release
      note: >-
        What each deliverable is for lives in
        [the design doc](https://github.com/OWNER/REPO/blob/main/docs/design.md).
        The order below follows the ranking rule: what the premise protects
        first.
      default-branch-head: "true"
```

To move the pin back before that commit, remove those lines in the same
change.

The page draws each label chip in a colour of its own, and a label it does not
know draws faint. A repository with labels of its own can have each chip
filled with the colour GitHub stores for that label instead, lettered in black
or white, whichever reads better on it. A recoloured label shows at the
board's next run, because editing a label starts none. The value is quoted
because a bare `true` in YAML is a boolean, and the input is a string.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      label-colors: "true"
```

GitHub returns an issue's labels in the order they were added. A repository
that wants each card's chips in name order can ask for it.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      sort-labels: "true"
```

Each of the two takes empty or `"true"`, and any other value fails the run
with its reason in the job summary. Both need a pin at or after the template
commit that added them, for the reason the icon gives.

A repository can name the heading that closes a review. A pull request then
reads as reviewed only when the owner posts a comment or a pull request review
whose whole first line is two `#` signs, a space and that heading, after the
branch's head commit. A pull request review counts only when it names the
head commit. So a heading such as `## Review round 1, lenses running`, posted
while a review is still under way, does not count, and a commit made after the
review sends the branch back for another. Write the heading without its two
`#` signs and the space after them, because YAML reads an unquoted `#` after a
space as the start of a comment and would leave the input empty. Left out, any
owner comment opening with `## Review` counts, whenever it was posted.

Two limits come with the heading.

1. A comment reaches the board at once, because a comment starts a board run.
   A pull request review reaches it on the board's next run of any other kind,
   because no event the board listens to fires when a review is submitted.
2. The head commit's time is the date the commit carries, which whoever makes
   the commit sets, and not when it was pushed. A commit dated before the
   comment and pushed after it keeps the branch reviewed. Post the heading
   after the last push. A pull request review names the commit it reviewed, so
   it has no such gap.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      review-heading: Review complete
```

The job summary counts the pull request items the heading marked reviewed, so
a misspelt heading shows up as a count of zero.

A repository can also ask for a settled rollup. The board's own checks, the
ones from `.github/workflows/board.yml`, then leave each pull request's
rollup, so a branch does not read as still running while the board rebuilds.
A skipped check reads as settled, a cancelled one as neither way, and the
checks are sorted by name. Left out, the rollup lists every check as GitHub
reports it.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      settled-rollup: "true"
```

Both inputs need a pin at or after the template commit that added them, for
the reason the icon gives.

Anyone can open an issue on a public repository, and by default a
`Board order:` or `Board after:` line in any issue's body counts. Such a line
places only the stranger's own card, because a card ranks only with a
`band:N` label, which needs triage access. A stranger's after line also adds
a sentence to the detail of each card it names, saying the stranger's card
should land after it. A repository that wants those lines read
only from issues its owner opened sets `owner-body-lines`. A stranger's lines
then set nothing, and the job summary lists them as refused. The input takes
`"true"` or nothing, and any other value fails the run. The pin has to be at
or after the template commit that added the input, for the reason the icon
gives.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      owner-body-lines: "true"
```

A repository that works toward one milestone at a time can open its board on
that milestone. Name it in the caller's job, with `<n>` standing for a
number. The page then draws a milestone selector above the board and opens on
the lowest-numbered open milestone the name matches, so `MVP <n>` opens on
`MVP 4` while `MVP 4` has open issues and on `MVP 5` once it closes. Each
milestone's title is cut at its first comma, so "MVP 4, serve the bars" is
listed as `MVP 4`. A reader's own choice is kept per browser. Left out, the
board draws no selector and keeps whole titles. The pin has to be at or after
the template commit that added the `milestone-default` input, for the reason
the icon gives.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      milestone-default: MVP <n>
```

The run's job summary names the milestone the board opens on, or says the
name matches no open milestone, which is where a misspelt name shows up.

A repository that ranks its work by `Board order:` lines and keeps no
`band:N` labels sets `ranking` to `order`. A card then ranks by its order
line alone, and a card is a parent only while one of its sub-issues is open.
An order on a parent is dropped, and so is a verdict on a parent or on a
deferred card, and the job summary lists each drop. When nothing in view is
ranked, the page draws every card and says why, rather than an empty build
order. Since the order line alone ranks a card there, a stranger's issue
could put itself first, so `order` also reads those lines only from issues
the owner opened, whatever `owner-body-lines` says. The input takes `order`
or nothing, and any other value fails the run. The pin has to be at or after
the template commit that added the input, for the reason the icon gives.

```yaml
    uses: l3a0/repo-template/.github/workflows/build-board.yml@<sha>
    with:
      ranking: order
```

To take a later fix, move the SHA in the caller. The skills and the generator
share the label names and line formats, so a skill newer or older than the
pinned generator tells a session to set something the board does not read.
The plugin's `update-build-board` skill therefore names, under
`## Generator compatibility`, the generator commits its formats were checked
against. When a regex, a label list or a query field in
`scripts/build_board.py` changed between the old pin and the new one, move the
pin only once a plugin release names the new commit there. A seeded repo keeps
no test between its pin and the plugin, so this comparison is a step to take by
hand. The template's own suite reads the skill at a pinned plugin commit.

## Running the checks locally

```bash
uv sync --dev
uv run ruff check
uv run ruff format --check
uv run pytest
```

markdownlint has no Python package, so it runs in CI rather than locally. The
prose checks it cannot do run in the test suite.

## Why the checks are required rather than advisory

A ruleset that lists no required status check leaves a red job blocking
nothing, and a rollup with no failures in it reads the same as a rollup that
passed, so nothing on the pull request page says the gate is open.

marketlake ran that way for its whole life until 2026-09-17, when it added a
required check. 199 of its 209 merged pull requests landed before that, none
of them having to pass anything. This template requires both checks from the
first commit instead.
