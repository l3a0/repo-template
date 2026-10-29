---
name: update-build-board
description: Keep this repository's build board true by setting, on GitHub, the labels, links and lines it reads. Run it when a decompose loop starts or exits, when a build session starts on a card or hands its pull request over, when a review is posted, when an issue is filed, gains or loses a sub-issue, or its priority or what it waits on changes, and when the board's page, generator or pinned version changes. A GitHub Action rebuilds the board from GitHub on every change, so nothing here writes the board itself. Answering what to take next is a read of the board's board.json.
---

# Update the build board

This skill comes from `.claude/skills/update-build-board/SKILL.md` in l3a0/quantitative-trading at commit `6da0ee3`, and landed here at the commit of the pull request that closes [l3a0/repo-template#24](https://github.com/l3a0/repo-template/issues/24). On the way the board became a reusable workflow in l3a0/repo-template that each repository calls at a pinned ref, a card kind and build-order column that only the source repository used were dropped, and the source repository's own issues, incidents and dates were cut, keeping the rule each one taught.

The build board is a page answering what is in flight and what to take next. Each open issue appears on it as a card. A GitHub Action rebuilds the page's data from GitHub on every issue, comment and pull request change and on a schedule, and no Claude runs at any step.

So a session never writes the board. What a session does is set the judgement the board reads, on GitHub: a label, a native "blocked by" link, a line in an issue body, or a line in a comment. The facts GitHub already records, such as a pull request opening, its checks settling or an issue closing, reach the board with nothing set by anyone.

## Where the board lives

For a repository `<owner>/<name>`, the pieces sit here.

| What | Where |
| --- | --- |
| The page | `https://<owner>.github.io/<name>/` |
| Its data | `board.json` beside the page |
| The caller | `.github/workflows/board.yml` in this repository |
| The build and deploy jobs | `.github/workflows/build-board.yml` in l3a0/repo-template, at the ref the caller pins |
| What builds the data | `scripts/build_board.py` in l3a0/repo-template |
| The page's source | `.claude/skills/update-build-board/board.html` in l3a0/repo-template |
| The page's tab icon and test stub | `favicon.ico` and `dom-stub.js` beside that page |

The caller is short. It holds the triggers, the `permissions`, and `concurrency: group: pages`, which makes runs deploy one at a time so an older snapshot never replaces a newer one. Its one job is `uses: l3a0/repo-template/.github/workflows/build-board.yml@<ref>`. In l3a0/repo-template itself the ref is `main`. A seeded repository pins a full commit SHA, so its board changes only when that repository moves the pin.

The called workflow checks out the generator and the page from the template at its own commit, which it reads from `job.workflow_repository` and `job.workflow_sha`. Inside a called workflow the `github` context still describes the caller, so `github.workflow_sha` would name the wrong commit. It also checks out the caller's `.github/workflows/board.yml`, because the generator reads the schedule from it.

A seeded repository keeps no copy of the generator or the page. It keeps the caller and two skills, this one and `sync-prune-next`. So every command here that runs the generator or the page fetches it from the template at the pinned ref, with these three lines run from the repository root.

```bash
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
PIN="$(sed -nE 's#^ *uses: l3a0/repo-template/\.github/workflows/build-board\.yml@([^ ]+).*#\1#p' .github/workflows/board.yml)"
template() { gh api "repos/l3a0/repo-template/contents/$1?ref=$PIN" -H "Accept: application/vnd.github.raw"; }
```

Each Bash tool call starts a new shell, so run the three lines in the same call as any command below that uses `$REPO`, `$PIN` or `template`. Check that `$PIN` is not empty before trusting anything `template` returns, because an empty pin means the `uses:` line did not match.

A change reaches the page once a run of the Action finishes. A label, a body edit and a comment each start a run. A "blocked by" link and a sub-issue start none, because GitHub Actions lists no trigger for either. So the session that makes one dispatches the board itself once its changes are in, using the `gh` login it made them with. The moments below say where.

```bash
gh workflow run board.yml --repo "$REPO"
```

The dispatch runs on the default branch. Never pass `--ref`. The `github-pages` environment lets only `main` deploy, so GitHub refuses the deploy of a run from any other branch.

The caller's triggers are these.

1. `issues`, for any change to an issue.
2. `issue_comment`, for any comment.
3. `pull_request_target` into `main`, with the types `opened`, `synchronize`, `reopened`, `closed` and `edited`. Without `closed` a merged pull request that closes nothing would read as open until the next run, and without `edited` so would a corrected closing link.
4. `workflow_run` of `CI`, which is the only event that fires when the checks settle.
5. `schedule`, with the line `cron: "8,38 * * * *"`.
6. `workflow_dispatch`, for the command above.

The `cron` line catches a change made with a workflow's own token, which starts no run, and a dispatch a session forgot. Nothing can rely on it. GitHub delays a scheduled run under load or drops it, and its documentation bounds neither. One measurement of this same schedule saw about 11% of its slots fire over 185 hours, with up to 603 minutes between two runs. Pages also tells a browser to cache `board.json` for ten minutes, and the page asks for a fresh copy every two minutes to get round it.

To read the board, as step 3 of `sync-prune-next` does, build it from GitHub rather than fetching the published copy, because the build reads GitHub as it stands rather than as the last run saw it. Run this from the repository root, after the three lines above, with a scratch directory as the output, never the repository.

```bash
template scripts/build_board.py > <scratch>/build_board.py && uv run --no-project --python '>=3.12' <scratch>/build_board.py build --repo "$REPO" --workflow .github/workflows/board.yml --out <scratch>
```

The generator needs Python 3.12 or later, and a bare `python3` can be an older one, such as the 3.9 macOS ships, which fails on import. `uv run --python '>=3.12'` finds or fetches a version that works.

It prints what it read to the terminal and writes `<scratch>/board.json`. A run that fails says why and writes nothing, because the script stops on any read it cannot trust rather than writing a board that reads as correct.

## What a session sets, and when

Each moment below is one where the page's answer changes and nothing GitHub records on its own says so. A session that reaches one and leaves has made the board wrong, and nothing else notices.

1. **A decompose loop starts.** Add `working:decompose` to the issue.
2. **A decompose loop exits.** Take `working:decompose` off, and post the verdict as a comment carrying one line in this form, alone on its line.

   ```text
   Board verdict: build after 5 passes
   ```

   Write `decide` in place of `build` when the loop ended on a question only the owner can answer. The newest such comment wins, so a loop run again writes a new one rather than editing the old. A loop with passes and no exit writes no verdict, because the card's plan marker means the loop exited.
3. **A build session starts on a card.** Add `working:build` to the issue. It stays after the pull request opens, because until the hand-over it is the only thing on the page saying the branch is still moving.
4. **A session hands its pull request over.** That means the review is posted, its fixes are pushed, the checks are green at the current head, and nothing more is coming. Take `working:build` off. Until then the card stays under "Waiting on my review", whatever its review and checks say.
5. **A review lands on a pull request.** Post it as a comment whose first line reads `## Review`. A review headed anything else counts as none, and its card sits in "Waiting on my review" until somebody notices.
6. **An issue is filed.** Add `deferred` or `decision` where one applies. These are the labels the board reads for a card's `kind`, as the table below says. They are separate from the label `CLAUDE.md`'s `## Pull requests` asks every filed issue for, saying what kind of work it is, such as `bug` or `documentation`. The card prints that one among its labels and decides nothing by it. Add a `band:N` label if it joins the priority order, because a card with no band is left out of the board's default view. Add a native "blocked by" link for each open issue it cannot start before, and a `Board after:` line for an ordering nothing enforces. If it set any link, dispatch the board once everything is set, because a link starts no run.
7. **A card's priority changes.** Move its `band:N` label, and add, change or remove its `Board order:` line.
8. **What a card waits on changes.** Add or remove its "blocked by" link, then dispatch the board, because the link starts no run.
9. **An issue gains or loses a sub-issue.** Dispatch the board once the sub-issues are set, because they start no run. A split in a decompose loop is the usual case, and an issue with any sub-issue draws as a parent.

Nothing else needs setting. A pull request opening, merging or closing, its checks settling, and an issue closing, retitled or relabelled all reach the board from GitHub.

Only the owner's comments count, for a verdict as for a review. The generator reads a comment only when GitHub reports its author association as `OWNER`. Anyone can comment on a public repository, and a stranger's comment would otherwise move a card. A session running `gh` as the owner posts comments that count. Labels and links need triage access, so they need no such filter.

The commands, with `<n>` the card's issue and `<b>` the issue it waits on, run after the three lines above.

```bash
gh issue edit <n> --add-label working:build
gh issue edit <n> --remove-label working:build
gh api --method POST "repos/$REPO/issues/<n>/dependencies/blocked_by" \
  -F issue_id="$(gh api "repos/$REPO/issues/<b>" --jq .id)"
gh api --method DELETE \
  "repos/$REPO/issues/<n>/dependencies/blocked_by/$(gh api "repos/$REPO/issues/<b>" --jq .id)"
gh workflow run board.yml --repo "$REPO"
```

A "blocked by" link takes the blocker's database id, which `--jq .id` reads, rather than its number. A body line is added by editing the issue's body, and goes on a line of its own, which is what the script reads.

```text
Board order: 14.5
Board after: #51, #83
```

The order takes a decimal, so a card can go between two others without renumbering either. A line quoted inside a sentence, a code span or a fenced code block is not read, and neither is a verdict line in a fence.

A branch that closes no issue gets no card at all, because the page is built from the tracker. Check `closingIssuesReferences` when a pull request opens, and if it is empty and the branch means to close something, fix the body before going further. A pull request into any branch but `main` is the exception. GitHub reads closing keywords only on a pull request into the default branch, so a stacked one shows an empty list until its base moves to `main`. That query is also eventually consistent. It has reported nothing seconds after a body gained its closing keyword and reported the link on the next call, so read it a second time before concluding the keyword failed.

A session that ends without taking its `working:` label off leaves its card under "Waiting on my review" or "Building" until somebody removes it. That fails safe, because it delays a merge rather than inviting one too early. A label is owed its removal by the session that set it, so report a stale one rather than removing another session's.

## The data, and where each field comes from

The page loads each section of `board.json` into the variable of the same name in capitals, so `prs` becomes `PRS`, and the rest of this file uses those names. Change what GitHub holds. Never hand-write a sentence in the page stating a number the data already carries, because that sentence outlives the number.

| Section | Field | Comes from |
| --- | --- | --- |
| `STATE` | `repo`, `title` | the repository the run read, from `--repo`, and the board's title, from the reusable workflow's `title` input, which defaults to `<name> build board`. The page builds every issue and pull request link from `repo`, so nothing in the page names a repository |
| `STATE` | `updatedAt`, `issues.open`, `longestGapMinutes`, `staleAfterMinutes` | the time GitHub was read, the open issue count, the longest gap in the caller's schedule, and that gap plus a 600-minute allowance for a scheduled run GitHub starts late or drops |
| `TRACKER` | `n`, `ms`, `label`, `labels` | each open issue's number, milestone, title and labels, less the board's own `band:N` and `working:` labels, which the page draws as the rank chip and the busy stripe |
| `TRACKER` | `kind` | `parent` for an issue with any sub-issue, then `deferred` for `deferred` and `decision` for `decision`, in that order where an issue carries more than one, and `ready` otherwise |
| `TRACKER` | `needs` | the issue's native "blocked by" links, keeping only blockers that are open issues in this repository |
| `TRACKER` | `after` | the issue's `Board after:` line, keeping only open issues |
| `PRS` | `pr`, `issue`, `state`, `linked`, `partOf`, `rollup` | each pull request naming an open issue through a closing link or a `Part of #N` reference anywhere in its body outside code, with its checks at the current head |
| `PRS` | `reviewed`, `review` | an owner's comment opening with `## Review`. Without one, `review` reads "review in progress" while the card carries a `working:` label, and "no review posted" otherwise |
| `WORKING` | `n`, `kind` | the `working:build` and `working:decompose` labels |
| `PLANNED` | `n`, `passes`, `ready` | the newest owner comment carrying a `Board verdict:` line |
| `NEXT` | `issue`, `band`, `order` | the `band:N` label and the `Board order:` line |
| `NEXT` | `ready` | the card's verdict where it has one, `decide` for a card whose kind is `decision`, and `plan` otherwise |

The page's constants live in its code rather than in the data.

| Constant | Holds |
| --- | --- |
| `FLOW` | the five in-flight stages and the test that assigns a card to one |
| `LABEL_HUE` | one colour for each kind and work label the template creates: `bug`, `documentation`, `enhancement`, `test`, `deferred`, `question` and `decision`. Any other label renders in the faint ink |
| `COLS` | the three build-order column headings and their subtitles, which are rendered prose |
| `KINDWORD` | the phrase a card prints for its `kind`, such as "deferred on purpose". A new kind prints no phrase until a code change adds one |
| `READY_RANK` | the order `build`, `decide` and `plan` sort in, read by the ranking sort |

`NEXT_SORTED` is `NEXT` put in order, by band, then order with 50 where a card has none, then readiness, then number. It is derived on every load.

Three of the fields carry judgement rather than measurement, so they are where the thinking goes.

1. **`needs` against `after`.** `needs` is a hard blocker and moves a card into a deeper column. `after` is an ordering somebody measured that nothing enforces, so it leaves the card where it is and sorts it below what it names. Use `after` when one card can be built first but is better built second, such as a fix that leaves the suite red until another issue lands. A "blocked by" link there would say something false. A link and an issue's `## Depends on` prose say the same thing twice. The link wins, because it is what the board reads, and the prose keeps the reason the wait exists.
2. **A verdict means a decompose loop exited**, on a pass that did not reduce the body. Not that a body looks thorough. Read the pass count as a cost rather than a depth.
3. **`band`** is priority. What each band means is this repository's call, under the ranking directive in its own `CLAUDE.md`. The template creates `band:1`, `band:2` and `band:3`, and a lower number ranks first.

`question` is not `decision`. An issue can carry `question` while it waits on research rather than on the owner, so the board reads only `decision` as needing the owner rather than a session.

### When two labels disagree

An issue carrying two `band:N` labels, both `working:` labels, two kinds, or two different `Board order:` lines has no single value. The script takes the lowest band, the `build` kind, the kind the table above puts first and the first line, and lists each conflict in the run's job summary rather than failing, because one stray label would otherwise freeze the whole board. Read the summary of a run after setting either, and fix the label the conflict names.

## What the page is made of

A heading, a strip and three sections, top to bottom. The heading and the browser tab show `STATE.title`. The strip renders two `STATE` figures: the open issue count, and the stamp drawn from `updatedAt`.

Keep the strip to figures that say what to take next. A test count, for one, costs a full suite run per build, and a merge during that run makes the count describe a commit that is no longer `main`.

The sections are these.

1. **In flight**, five columns running most finished on the left: waiting on your review, waiting on my review, building, planned with no builder, and being planned. A card here is drawn once and left out of the build order. Two of the five hold a card only because a session is on it, and the kind of `working:` label is what separates a build session from a decompose loop. A third, waiting on my review, also holds a card whose branch is open and whose session has not handed it over.
2. **Build order**, three columns by how many steps along a chain of open blockers a card sits. By default they hold the ranked cards, and with Show all they hold everything not in flight. Within a column, cards sort by readiness, then by the priority order, then by a measured `after`, then by number, except that a card whose `kind` is `deferred` is forced last whatever the rest says. Under it sits a chain bar, which holds a hint until a card is picked and then says what that card waits on and what waits on it.

   By default the section draws only the cards `NEXT` ranks, and a line above the columns counts the rest and carries a **Show all** button. On the board this page came from, drawing every open issue ran the first column past fifty cards, with the ranked ones scattered through it. The choice is kept in the viewer's browser under `board-all:<owner/repo>` and nowhere else. Every board an owner publishes is served from the one origin `<owner>.github.io`, so a key shared by all of them would let one board's toggle flip another's. A card whose `kind` is `deferred` stays hidden even when it carries a band, because `rankMark` drops it. So a card in the build-order columns shows by default exactly when it carries a `band:N` label and its `kind` is not `deferred`. A card in flight shows either way. A band label is how a card gets onto the short view, and that view is what the owner reads first.
3. **One paragraph**, saying how the board is built and that every figure on it dates from the stamp. Do not grow it into a footer that retells what the cards say.

Between the strip and the first section sits a banner. Over a current board it is empty. It warns when the stamp is older than `staleAfterMinutes`, because a failed run leaves the last board up and a board hours stale looks like a fresh one. It also speaks when the page has no board to show, or has stopped taking fresh copies, and says which and how old any data on screen is. With no board data the page hides both sections and the footer and draws only the banner, so a missing or unreadable `board.json` never reads as an empty board.

## Change the page or the generator

A change to the page, the stub, the icon or the generator happens in l3a0/repo-template, never in a seeded repository, because a seeded repository runs the template's copies at its pin and any local copy would run nowhere. Change it only when the rendering has to change. Edit the file in the template, run its `tests/test_build_board.py` and `tests/test_build_board_generator.py` and the harness below, and open the pull request there. The board run that the merge starts publishes the template's own board from `main`.

A seeded repository picks the change up by moving its pin. Edit the ref on the `uses:` line in its `.github/workflows/board.yml` to the template commit that carries the change, and in the same pull request re-copy this skill and `sync-prune-next` from the template at that commit. The skills and the generator share the label names, the line formats and the list of changes that start no run, so a pin moved without the skills leaves a repository following one version's rules on another version's board.

The page links its tab icon as `favicon.ico`, and the reusable workflow copies `favicon.ico` from beside the page into the same folder. Renaming the icon means changing the page's link, that copy and the tests that check them together.

A change to what the page reads is a change to the generator as well. Add the field to `scripts/build_board.py`, and to `ITEM_OK` in the page if the renderer reads it without a guard, because the page refuses a whole section when one item lacks a field it reads.

## Verify by executing, never by reading

A parse check is not enough, because a comma dropped inside a nested array still parses. `tests/test_build_board.py` in the template runs the page against an invented fixture, which catches a page that throws, draws a section from the wrong document, or mislabels an empty board. It cannot read live data, so running the page on a board built from GitHub is still the check on what a viewer will see.

The harness runs the page's script under `osascript`, which has no fetch, so it hands the page a fake one serving a `board.json` built as "Where the board lives" says. First put the page and the stub beside that `board.json`. From the repository root, after the three lines above:

```bash
template .claude/skills/update-build-board/board.html > <scratch>/board.html &&
template .claude/skills/update-build-board/dom-stub.js > <scratch>/dom-stub.js
```

In l3a0/repo-template, when the change under test is the page itself, copy the two files from the working tree instead, because the change is on no pinned ref yet. Then run this from the scratch directory.

```bash
python3 -c "
import json,re,sys
t=open(sys.argv[1]).read()
open('board.js','w').write(re.search(r'<script>(.*?)</script>', t, re.S).group(1))
open('serve.js','w').write('var fetch=function(){return Promise.resolve({ok:true,status:200,'
  'text:function(){return Promise.resolve('+json.dumps(open('board.json').read())+');}});};\n')
" board.html
cat > print.js <<'JS'
(async function(){ for (var i=0;i<50;i++) { await null; }
function s(x){return String(x).replace(/<[^>]+>/g," ").replace(/\s+/g," ").trim();}
var o=[];
o.push("STRIP: "+s(store.strip.innerHTML));
store.flow.innerHTML.split('<div class="col f-').slice(1).forEach(function(c){
  var h=c.match(/<span class="t">([^<]+)<\/span><span class="c">(\d+)<\/span>/);
  var ids=(c.match(/data-n="(\d+)"/g)||[]).map(function(m){return "#"+m.match(/\d+/)[0];});
  var d=c.match(/<span class="d">([^<]*)<\/span>/);
  o.push("flow  "+h[1]+"="+h[2]+": "+(ids.join(" ")||"(empty)"));
  o.push("  sub "+(d?d[1]:"(none)"));
  var wk=(c.match(/<div class="wk">[^<]*<\/div>/g)||[]).map(s);
  o.push("  wk  "+(wk.join(" | ")||"(none)"));});
store.board.innerHTML.split('<div class="col k').slice(1).forEach(function(c){
  var h=c.match(/<span class="t">([^<]+)<\/span><span class="c">(\d+)<\/span>/);
  var ids=(c.match(/data-n="(\d+)"/g)||[]).map(function(m){return "#"+m.match(/\d+/)[0];});
  var d=c.match(/<span class="d">([^<]*)<\/span>/);
  o.push("board "+h[1]+"="+h[2]+": "+ids.join(" "));
  o.push("  sub "+(d?d[1]:"(none)"));
  var wk=(c.match(/<div class="wk">[^<]*<\/div>/g)||[]).map(s);
  o.push("  wk  "+(wk.join(" | ")||"(none)"));});
o.push("FLOWNOTE: "+s(store.flownote.innerHTML));
o.push("BOARDNOTE: "+s(store.boardnote.innerHTML));
o.push("KEY: "+s(store.key.innerHTML));
o.push("FLOWKEY: "+s(store.flowkey.innerHTML));
store.foot.innerHTML.split("<p>").slice(1).forEach(function(x,i){
  o.push("FOOT["+(i+1)+"] "+s(x));});
// Anything the page wrote to that the lines above do not format. Listing the
// surfaces by hand is what let one surface go unread and a dead probe go
// unnoticed, so the sweep is what keeps that list honest. It sees load-time
// `innerHTML` only: not `stamp`, which only a timer writes, not any
// `aria-label`, since the tag-stripper deletes attributes, and not the
// chain bar's picked state, which needs a click. It cannot see code that
// renders nothing either, which wants a grep rather than a read.
var shown = {strip:1, flow:1, board:1, flownote:1, boardnote:1, key:1, flowkey:1, foot:1};
Object.keys(store).sort().forEach(function(id){
  if (!shown[id]) o.push("OTHER["+id+"] "+s(store[id].innerHTML));});
console.log(o.join("\n")); })();
JS
cat dom-stub.js serve.js board.js print.js > run.js
osascript -l JavaScript run.js
```

The page fetches on load and draws once the answer arrives, which is after the script's last line, so the printing waits for it rather than running at once.

That run draws the default view, which hides every card `NEXT` does not rank. Run it a second time with the Show all view, because most of the columns and most of the board note only render there. The stub has no `localStorage`, so one line before the script supplies a stored choice. It answers "1" for any key starting with `board-all:` and nothing for any other, so a page reading a key outside that prefix draws the short view and the run shows it.

```bash
(cat dom-stub.js serve.js
 echo 'var localStorage={getItem:function(k){return String(k).indexOf("board-all:")===0?"1":null;},setItem:function(){}};'
 cat board.js print.js) > run-all.js
osascript -l JavaScript run-all.js
```

`osascript -l JavaScript` is JavaScriptCore, and it is what runs this where no `node` is installed. It is macOS only. Anywhere else, run the same files with whatever JavaScript engine is present, because the stub is plain ES5 and assumes nothing about its host.

Print every surface the page renders into, not only the interesting ones. A harness that skips a surface cannot see a defect on it, and three gaps of this kind have each hidden one.

1. **The footer, the key and the flow key.** The footer is the largest prose block on the page. With it unprinted, a false figure planted in it left the output byte-identical.
2. **The column subtitles.** With only each column's title and count printed, a rewritten subtitle could be reverted without the output moving. Each column now prints a `sub` line.
3. **The session phrase under a card.** With no card's lines printed, a page that stopped drawing a phrase gave the same output as one that still drew it. Each column now prints a `wk` line listing the session phrases its cards drew, and `(none)` where they drew none. The page draws no such phrase today, so every `wk` line reads `(none)`, and a phrase showing up on any of them is that line coming back.

**Much of the page is dark when no branch is open and no session holds a card**, which is the state it is in between batches. The flow note collapses to a sentence, the flow legend loses two entries, and the footer's decay clause disappears. That clause is where check 5's conjunction lives, so on an empty board the sentence it warns about cannot be read at all. Where a change touches that code, add a `prs` or `working` entry to a scratch copy of `board.json`, rebuild `serve.js` from it, run the harness and read the output.

**Read the output rather than checking that it ran.** Many of the defects this page has shipped were sentences that rendered perfectly and said something false. Six checks catch most of them.

1. **The totals reconcile.** In-flight cards plus board cards plus the hidden count on the `OTHER[more]` line equals open issues, and every card carries its labels. In the Show all run nothing is hidden, so the number on that run's `OTHER[more]` line must equal the board cards, and in-flight plus board cards alone must equal open issues.
2. **No sentence contradicts another.** The free-card list must not name a card that a later sentence says nobody should start.
3. **Every count matches its own list.** A sentence saying four cards and then naming three is the prose and the data disagreeing.
4. **No figure is typed into a sentence.** Every number the page renders should come from the data, so that changing the data changes the page. The page once carried a long hand-written footer, and one update left four stale figures in it at once. Deleting that prose is what made this check cheap, so the thing to watch for is prose growing back.
5. **Every joined sentence says what it means.** A computed sentence joins clauses that each drop out on their own, so a "too" or an "and" can outlive the clause it referred back to. One read that a card "is planned too" with nothing before it, because the card it was agreeing with had merged. A conjunction can also be present and be the wrong word: a set of alternatives joined by "and" reads as one card doing all of them at once. So read what a joined sentence claims rather than only checking that both halves are there, and read the sentences rather than only the counts.
6. **Nothing a card says contradicts where the card sits.** A marker, a line of text and a position are three claims about one issue, and a rule added to any of them can disagree with the other two. A chip once read 6 on a card the sort had forced to the bottom. Read each card's own marks against its place in the column.

One class the six cannot reach. Every check above reads what the page rendered, so none of them sees code that renders nothing. Defect 13 below is that class, and what catches it is a grep rather than a read.

## What goes wrong, from the record

Each of these shipped on this page or was caught at the last moment. They are written down because the next one will be a variant rather than something new. Defects 13 and 14 were made and caught inside one session. From defect 9 on, the rest were found by reading the published page or in review rather than by the harness, which is what makes them the failures this page invites.

1. **A sentence outliving its data.** A hard-coded "everything in the third column waits on the same two issues" survived the column emptying. Compute the sentence from the array, including the branch where the array is empty.
2. **A fixed list of reasons.** The note offered three reasons a card might not be free, for one card that was simply deferred. Build the list from the cards actually present.
3. **Hard-coded indices.** The in-flight note read positions three and two, so reversing the columns silently swapped what it said. Walk the columns.
4. **Counting something twice.** A card carrying an open pull request was listed as free to pick up, two sentences before the page said nobody should start it. Subtract everything already carried, not only the case that came to mind.
5. **Two sorts that agree today.** The grid sorted by issue number while a ranking section sorted by a measured argument, so the page put one card ahead of another in one place and behind it in another. There is now one `cardOrder` comparator, and every column that draws cards calls it. Keep it that way.
6. **A legend describing cards that are not under it.** It began as a fixed list advertising states that had moved to another section. Computing it was not enough either: the in-flight legend still offered "ready to hand to a builder" for a card whose pull request had retired that marker. The data is the source of truth and the marker is a function of the data plus one suppression rule, and the defect was that the rule existed in two places. There is now one `planMarker` that both the card and the legend call. **A legend calls whatever decides the marker, never a second copy of the rule.** The inverse shipped too: the in-flight legend explained a plan marker and a pull request while saying nothing about the session marker every card in that render drew. A legend accounts for each marker its own cards drew, and for no marker they did not.
7. **Declaration order.** `planOf` was read by a sort that ran before its declaration, which throws on load rather than degrading quietly. The stub catches this immediately.
8. **Pluralisation.** `plu` appended a bare letter s, giving a count of passes that read "19 passs". It now handles a word already ending in one.
9. **A second list of the same cards.** The page carried a ranking section listing cards the build order already drew, so every card had two homes, and the two ordered one pair differently, which is defect 5. The section is gone and its order drives the grid instead. Do not add a list that restates the cards.
10. **Reasoning duplicated onto a card that links to the issue holding it.** When the ranking section went, its argument for each position moved onto the cards, and the longest rendered several times the height of its neighbours for text one click away. The argument belongs on the issue, and the card carries the position as a number.
11. **A plan line under work already under way.** A card with an open branch said its plan was ready to be written, directly above a line saying it was written. A build session is the same hand-over before a branch exists, so the marker now goes for either. The sort still reads `PLANNED`, so the card keeps its position whether or not the marker is drawn. A decompose loop keeps its marker, because it revises the plan rather than carrying it out, and that difference is why `WORKING` carries `kind`. A suppression rule is a second consumer of the field, so it goes in one function every reader calls rather than being written out wherever it is needed.
12. **Two fixes that each worked, contradicting each other.** A priority chip was added to the cards, and separately the sort was changed to force a deferred card last. Together they gave one card a chip reading 6 above a position reading last, which is two answers to one question. The chip is dropped on a deferred card, because the dashed border and the kind word already say it is deliberately not being done. Check 6 above is what catches the next one, so a rule added to a card is read against the card's own position rather than only against the data it came from.
13. **Bindings left behind when the sentence they fed moved.** The board note once described the cards a session was on. That sentence moved to the in-flight note, and the bindings that computed it stayed, one of them building the whole paragraph and assigning it to a variable nothing reads. The harness cannot see this, because it prints what the page rendered and dead code renders nothing. So when a sentence is deleted or moved, grep the script for the names that fed it. A leftover here is not inert. It is a finished sentence about live data, beside a surface that would print it, under a rule that has since changed.
14. **A set of alternatives joined with "and".** The board note lists the reasons a first-column card is not free, and `andlist` joined them, so it read that a card can need a decision rather than a session and be deferred on purpose. The reasons are collected from different cards, so joining them with "and" hands all of them to one card. The join now takes its conjunction as an argument, and `andlist` and `orlist` are two names for it.
15. **A column test reading half of what its heading claims.** "Waiting on your review" asked only whether a review had been posted, so a branch with checks still running sat under a heading saying the next move was the owner's. `CLAUDE.md` says a pull request is not handed over until its checks have run and settled, so the page invited a merge of a branch that could still go red. The first attempt kept the card there and added a clause to the note, which is the note working around a wrong test, and it put the rule in a second place. One `handedOver` came to decide it instead. Three states stay on the reviewer's side, and the third is the one to remember: a check still running, a check that failed, and no checks reported at all. A conflicting pull request gets no run, so an empty rollup is a branch nothing built rather than a branch with nothing wrong.
16. **A heading that named one kind of session for two.** Adding decompose loops to `WORKING` put them under a column reading "Building", which is what a loop is not. A loop ends in a sharper plan and a builder ends in a branch, so they now have different columns, and the column test reads `kind`.
17. **A column test that could not see the session still working.** A card sat under "Waiting on your review" with a review posted and every check green, so both halves defect 15 asks for were done. Its session was not. It pushed a merge of `main` minutes later and was still rewriting files. `handedOver` read the review and the checks and nothing about the session. The fix reuses `WORKING`: a build session's `working:build` label stays until it hands the pull request over. The page's `owed` returns the first thing a branch still owes, which is a review, its session or its checks. The column test and the flow note both call it, so the reason a card gives for sitting on the reviewer's side is the rule that put it there. The price is a card left under "Waiting on my review" when its session ends without taking its label off. That fails safe, because it delays a merge rather than inviting one too early.
18. **A merged pull request read as a branch.** Two cards each had a pull request merged as `Part of`, with the issue left open for the rest. The board note left both out of the free list, saying a card can "already be written and waiting on a review", which neither was. The note asked whether `PRS` held any entry for the card, while the In flight section asked whether it held an open one. One function, `openBranches`, now answers that for every reader. Freeing every merged entry would have gone past the defect. A pull request merged with no `Part of` was meant to close its issue, so its card is held back as needing only closing by hand, and `closesByHand` decides that for the free list, the plan marker, the kind word, the "Planned, no builder" column and the chain bar. A closed entry's line now says closed rather than repeating its old review text.
19. **One sentence carrying two facts.** A card gained two open blockers, neither waiting on anything. The board note's branch for a graph with no third column was fixed text saying nothing sat "behind more than one thing", which meant no chain ran two steps and read as no card waiting on two issues. The second column's subtitle made the same claim. That is defect 1 surviving inside a computed sentence, because only its other branch read the data. The note now reads the longest chain from the depth map, names any card waiting on several open issues in a clause of its own, and says nothing about depth when no card waits on anything. The columns are headed by steps along a chain rather than by things to land. The chain bar had the same fault, saying "waits on 2" for a card whose own line named one issue, because it counted the whole chain. So when a phrase can be read as either of two quantities, check it against data where the two differ.
20. **A free claim that read only the links.** Picking a card with no open `needs` either way gave fixed text saying it could be taken on its own. So the chain bar called a card free whose kind word said not to start it, or whose session or open branch said somebody was carrying it, while the board note's free list held those cards back. A card whose `after` line tied it to another issue was also called linked to nothing. One table, `HOLDS`, now lists the reasons a card is not free, and `takeable` passes ordinary work that no row of it holds. The free list, the bar and the In flight note's sentence for "Planned, no builder" all read them. `kindShown` decides whether a kind reason applies, because an open branch hides the card's kind word. A plan whose one open question is the owner's has a row that reads `planMarker`, so it fires only where the card draws that marker. The "Planned, no builder" column's own test still reads no kind, so a held card with a finished plan stays under that heading, and the note beside it says why it is held.
21. **Two pointers reading a list that ties at zero.** `most` is the largest number of cards any one card frees, and `unblocks` held every card that freed that many. When nothing waits on anything, `most` is 0 and every card ties at it, so the list held the whole board, and the note named every card as though each one freed the most. That is defect 1's lesson in a list of maxima. Such a list is never empty while the board holds a card, so the branch to compute is the one where it ties at zero. `unblocks` is now empty when `most` is 0.
22. **Two more places deciding on their own whether a card is free.** The plan marker's suffix, its label sentence and the legend's gloss read only `needs`, so a deferred card with a `build` verdict read "deferred on purpose" directly above "ready to build". `buildable` now asks `takeable` and an open `needs` together, and all three call it. Separately, the "Waiting on your review" sentence was fixed text ending "waiting on nothing else", read beside a card whose own line said it waits on an open issue. That sentence now names what the card's `needs` and `after` name, in the card's words. Both cards keep their columns, because both halves of each heading are true of them, and the note says why each is held.

Most of these share one shape: a rule written in two places, which drift apart. Before adding a rule to the page, find the function that already decides it and call that.

## Writing the prose

The repository's own writing rules govern the page's prose. Impersonal voice, no first person, no em dashes or semicolons, short complete sentences, a counted set written as a list rather than inlined, and the price of a choice named rather than hidden.

One exception is deliberate. The in-flight column headings say "Waiting on my review" and "Waiting on your review", and the whole point of those two columns is whose move it is. "My" is the session's and "your" is the owner's. Applying the impersonal rule to them deletes the distinction the section exists to draw. Keep the first and second person there, and nowhere else.

Two further conventions are specific to this page.

1. **Say what the page cannot know.** The in-flight section is the most perishable thing on it, because a session ends without telling anyone and a review posted a minute after the stamp still reads as owed. The footer says so, and it keeps saying so.
2. **A comment explains why a rule exists, not what the line does.** The script's comments carry the measurements behind its choices, which is what stops the next session undoing one by accident.

## Which copy wins where this file and the page overlap

Several things are reasoned about twice, once in a comment beside the line it governs and once here. The duplication is deliberate and its price is named rather than hidden, because nothing checks the two against each other.

The split is by question. A comment in the page or the generator answers why that line is the way it is, and it is authoritative about the code it sits on, because it travels with the code through any rewrite. This file answers how to run an update and what has gone wrong before, and it is authoritative about the procedure and the record.

So when the two disagree about a mechanism, the comment is right and this file is what gets corrected. When they disagree about what a session should do, this file is right. A session changing the page's behaviour updates the comment on the line it edits, and checks here for a sentence describing the same mechanism.

## Finishing

Report in the same reply that sets anything.

1. Each label, link and line set or removed, and on which issue.
2. Any conflict the next run's job summary listed, and what fixed it.
3. Any sentence the harness caught, and what replaced it, when the page's code changed.

A run of the Action that fails leaves the last board up, and the page's banner says so once the stamp passes `staleAfterMinutes`. Read the failed run's log rather than re-running it, because a second run of the same read fails the same way unless the failure was GitHub's.

### An update reports idle cards and offers nothing

Offering a build task for every card in "Planned, no builder", and a decompose task for every free card in the first build-order column, was tried and withdrawn. Two things went wrong, and neither depends on how many cards are idle.

1. **The offer is larger than the queue.** The list of pending offers holds fewer entries than one update offered, so older offers dropped out while new ones were still being made.
2. **A drop is not always reported.** A dropped offer sometimes left no notice, and a diff of the pending list cannot tell a dropped offer from one the owner started. A reader who takes the pending list for the whole set is misled by exactly the entries nobody was told about.

So an update reports what it found in those two states and stops. What to start, and how many at once, is the owner's call.

One fact about the page belongs here. The "Planned, no builder" test in `FLOW` asks five things of the state `flightCols` builds for a card.

1. `s.plan`: a `PLANNED` entry exists.
2. `!s.pr`: no open pull request carries the card.
3. `!s.busy`: no session is on it.
4. `!s.blocked`: nothing in its `needs` is still open.
5. `!s.landed`: no pull request merged against it with no `Part of`.

A plan-complete card behind an open blocker therefore stays on the build order under its own "waits on" line, and a card whose pull request merged with no `Part of` has no builder to wait for, per defect 18.
