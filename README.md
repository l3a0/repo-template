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
  committing, and pull request review. It has template slots for the premise
  and for repo-specific policy, marked as HTML comments.
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
  rule in CLAUDE.md expects to exist.
- **[.github/dependabot.yml](.github/dependabot.yml)** groups minor and patch
  bumps, keeps majors separate, and keeps ruff on its own so a new lint rule
  never turns an unrelated pull request red.
- **[scripts/setup-repo.sh](scripts/setup-repo.sh)** applies the ruleset, the
  labels, CodeQL default setup, GitHub Pages and the `github-pages`
  environment to a repository. It is idempotent and takes `DRY_RUN=1`.
- **The build board** is a page on GitHub Pages saying what is in flight and
  what to take next, rebuilt from GitHub by a reusable workflow that every
  seeded repo calls. The section below explains it.
- **[docs/design.md](docs/design.md)** and
  **[docs/build-plan.md](docs/build-plan.md)** are skeletons for the two docs
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

Then do the five things nothing can guess.

1. Fill the premise slot at the top of `CLAUDE.md` and the premise section in
   `docs/design.md`. Every later ranking decision appeals to it, so it comes
   first.
2. Replace `README.md` wholesale. This one describes the template, not your
   project, and a seeded repo that keeps it tells its readers to create a repo
   from the repo they are already looking at.
3. Rename `src/project/`, and update `packages`, `name` and `description` in
   `pyproject.toml`.
4. Create one milestone per slice, named as `docs/build-plan.md` names them.
5. Decide on both modules in `docs/optional-policies.md`, move what applies
   into the **Repo-specific policy** heading in `CLAUDE.md`, and delete the
   file.
6. Pin the build board and delete the template's copy of it, as the next
   section says.

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
  It checks both out from this repo at the commit the caller pinned.
- **[.github/workflows/board.yml](.github/workflows/board.yml)** is the caller.
  It holds the triggers, the permissions and the concurrency group, and calls
  the reusable workflow. This repo calls it at `main`, so its own board runs
  the shared path first.
- **The two skills**, `update-build-board` and `sync-prune-next` under
  `.claude/skills/`, tell a session what to set on GitHub and how to read the
  board.

A seeded repo keeps the caller and the two skills, and runs everything else
from here at the commit it pins. So after seeding, pin the caller to a full
commit SHA of this repo's `main`, and delete the template's copy of the board.

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

To take a later fix, move the SHA in the caller and copy the two skills from
the same commit in the same pull request. The skills and the generator share
the label names and line formats, so a skill newer or older than the pinned
generator tells a session to set something the board does not read.

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
