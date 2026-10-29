#!/usr/bin/env bash
#
# Apply this template's GitHub-side policy to a repository.
#
# Five things live on GitHub rather than in tracked files, so a fresh clone of
# the template carries none of them.
#
# 1. The branch ruleset that makes `main` require a pull request, read from
#    .github/rulesets/default.json.
# 2. The label set that the triage rule in CLAUDE.md and the build board
#    expect to exist, read from .github/labels.json.
# 3. CodeQL's default setup, which the ruleset's code scanning rule waits on.
# 4. GitHub Pages, with GitHub Actions as its source, which the build board's
#    reusable workflow deploys to.
# 5. The github-pages environment, limited to deploying from `main`.
#
# Reading the first two from the repo's own files keeps those files the source
# of truth.
#
# It is idempotent. Running it twice updates in place rather than duplicating.
#
# Usage:
#   scripts/setup-repo.sh l3a0/new-repo
#   DRY_RUN=1 scripts/setup-repo.sh l3a0/new-repo
#
# The ruleset requires two status checks by name, `test` and `docs`, which are
# the two jobs in .github/workflows/ci.yml. Renaming a job means editing the
# ruleset JSON and re-running this script, or the required check goes missing
# and a pull request reports a short rollup rather than a failure.
#
# `strict_required_status_checks_policy` is off, so a branch merges without
# being brought up to date with `main` first. What that setting buys is one
# thing: a run is computed against one merge ref, a later merge to the base
# replaces it, and a rollup can read green after the branch underneath it has
# gone stale. What it costs is charged to every branch rather than to the stale
# ones, because any merge to `main` sends all the open branches back for another
# round of checks.
#
# The staleness is real and is handled by reading rather than by blocking.
# CLAUDE.md already requires a session to re-read a rollup whenever the base has
# moved, and that rule does the work this setting was doing, on the branches
# where it matters rather than on all of them.

set -euo pipefail

repo="${1:-}"
if [[ -z "$repo" ]]; then
  echo "usage: $(basename "$0") <owner/repo>" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ruleset_file="$root/.github/rulesets/default.json"
labels_file="$root/.github/labels.json"

for file in "$ruleset_file" "$labels_file"; do
  if [[ ! -f "$file" ]]; then
    echo "missing $file" >&2
    exit 1
  fi
done

dry_run="${DRY_RUN:-}"

# The dry-run line goes to stderr. Every call site redirects this function's
# stdout to /dev/null to hide gh's own output, and that redirection swallowed
# the announcement too, so a preview run was indistinguishable from a live one.
run() {
  if [[ -n "$dry_run" ]]; then
    echo "[dry-run] $*" >&2
    return 0
  fi
  "$@"
}

echo "== $repo =="

# --- Ruleset -----------------------------------------------------------------
# Read the rulesets before anything else, because this is the first call that
# proves the repo resolves and that the token carries admin scope. `gh api`
# writes an error body to stdout, so a discarded exit status puts a 404
# document into the id and the script reports "updating ruleset (id {...})"
# before dying on the next call, half applied.
if ! rulesets_json="$(gh api "repos/$repo/rulesets" 2>/dev/null)"; then
  echo "cannot read rulesets for $repo." >&2
  echo "Check the name is right and that your token has admin access." >&2
  exit 1
fi

# Match on the name rather than an id, since an id belongs to one repository
# and this file is copied between them. Repository rulesets only: an org can
# hand down an inherited ruleset of the same name, and writing to its id fails.
read -r ruleset_name existing_id <<<"$(
  python3 - "$ruleset_file" "$rulesets_json" <<'PY'
import json
import sys

name = json.load(open(sys.argv[1]))["name"]
rulesets = json.loads(sys.argv[2])
ids = [
    str(ruleset["id"])
    for ruleset in rulesets
    if ruleset.get("name") == name and ruleset.get("source_type", "Repository") == "Repository"
]
print(name, ids[0] if ids else "")
PY
)"

if [[ -n "$existing_id" ]]; then
  echo "updating ruleset '$ruleset_name' (id $existing_id)"
  run gh api --method PUT "repos/$repo/rulesets/$existing_id" --input "$ruleset_file" >/dev/null
else
  echo "creating ruleset '$ruleset_name'"
  run gh api --method POST "repos/$repo/rulesets" --input "$ruleset_file" >/dev/null
fi

# --- Labels ------------------------------------------------------------------
# The records land in a temp file rather than arriving through a pipe or a
# process substitution. Neither of those is covered by `set -o pipefail` on the
# reading side, so a labels file that failed to parse printed a traceback,
# created nothing, and still exited 0.
#
# Fields are NUL-separated because a tab-separated read collapses runs of tabs
# and splits on a newline inside a description, which silently turns one label
# into two and invents a second with an empty colour.
labels_stream="$(mktemp)"
trap 'rm -f "$labels_stream"' EXIT

python3 - "$labels_file" >"$labels_stream" <<'PY'
import json
import sys

for label in json.load(open(sys.argv[1])):
    for field in ("name", "color", "description"):
        sys.stdout.write(label[field])
        sys.stdout.write("\0")
PY

# `gh label create --force` updates an existing label rather than failing, so
# the same call covers both cases. Labels the repo already has and this file
# does not name are left alone, because deleting one detaches it from every
# issue that carries it.
label_count=0
while IFS= read -r -d '' name \
  && IFS= read -r -d '' color \
  && IFS= read -r -d '' description; do
  echo "label: $name"
  run gh label create "$name" \
    --repo "$repo" \
    --color "$color" \
    --description "$description" \
    --force >/dev/null
  label_count=$((label_count + 1))
done <"$labels_stream"

if [[ "$label_count" -eq 0 ]]; then
  echo "no labels were applied. $labels_file parsed to nothing." >&2
  exit 1
fi

# --- Code scanning -----------------------------------------------------------
# The ruleset carries a code_scanning rule naming CodeQL, and that rule needs
# CodeQL to actually run. Without default setup enabled, the rule waits on a
# tool that never reports. `actions` is in the language list because the
# workflows are part of the attack surface, not only the Python.
echo "code scanning: CodeQL default setup"
if ! run gh api --method PATCH "repos/$repo/code-scanning/default-setup" \
  --raw-field state=configured \
  --raw-field query_suite=default \
  --raw-field threat_model=remote \
  --raw-field 'languages[]=actions' \
  --raw-field 'languages[]=python' >/dev/null 2>&1; then
  echo "  could not configure CodeQL. It needs code pushed and a language" >&2
  echo "  GitHub recognises, so re-run this script after the first push." >&2
fi

# --- Pages -------------------------------------------------------------------
# The build board's reusable workflow publishes the board on GitHub Pages
# through the github-pages environment, and its deploy job has nowhere to go
# until Pages is on with GitHub Actions as its source rather than a branch.
# The site is read first, so a repository already set that way is left alone
# and one publishing from a branch is switched.
#
# The exit status decides whether a site exists, not the output. A repository
# with no site answers 404, and `gh` prints that error's JSON body to stdout,
# where `--jq` never runs, so the output alone would read as a source type.
if ! pages_type="$(gh api "repos/$repo/pages" --jq .build_type 2>/dev/null)"; then
  pages_type=""
fi
if [[ -z "$pages_type" ]]; then
  echo "pages: enabling, source GitHub Actions"
  run gh api --method POST "repos/$repo/pages" -f build_type=workflow >/dev/null
elif [[ "$pages_type" != "workflow" ]]; then
  echo "pages: switching source from $pages_type to GitHub Actions"
  run gh api --method PUT "repos/$repo/pages" -f build_type=workflow >/dev/null
else
  echo "pages: already on, source GitHub Actions"
fi

# --- The github-pages environment --------------------------------------------
# The board's triggers all run on `main`, and a run from any other branch must
# not reach the site. GitHub creates the environment when Pages first deploys,
# so the script creates it here instead, limits it to custom branch policies,
# and adds a policy for `main` unless one exists. A policy already there for
# another branch is left alone, because removing one is the owner's call.
echo "environment: github-pages, deploys from main"
run gh api --method PUT "repos/$repo/environments/github-pages" \
  -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true' >/dev/null
if ! branch_policies="$(gh api "repos/$repo/environments/github-pages/deployment-branch-policies" \
  --jq '.branch_policies[] | select(.type == "branch") | .name' 2>/dev/null)"; then
  branch_policies=""
fi
if grep -qx main <<<"$branch_policies"; then
  echo "environment: main already allowed"
else
  echo "environment: allowing main"
  run gh api --method POST "repos/$repo/environments/github-pages/deployment-branch-policies" \
    -f name=main -f type=branch >/dev/null
fi

# --- Reserved human steps ----------------------------------------------------
# A pointer rather than a copy. This script is kept and re-run by every repo
# seeded from the template, so a list written out here goes stale the moment a
# repo renames its package, and then tells its owner to rename a directory
# that no longer exists.
cat <<'NOTES'

Done with the GitHub side. The rest is in README.md, under
"Starting a repo from it". Nothing here can guess those.
NOTES
