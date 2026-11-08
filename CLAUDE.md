# CLAUDE.md — PROJECT_NAME

<!-- TEMPLATE: replace this paragraph with the repo's premise. Say what the
     project is, what it is for, and where the reasoning lives. Two or three
     sentences. The premise is what every later ranking decision appeals to,
     so write it before writing anything else. -->

PROJECT_NAME is TODO. Status: TODO. Code lives in `src/`, with tests under `tests/`.

**The tracker is authoritative for scope.** An unbuilt deliverable's issue is the source of truth for what it is and what it must do. The design doc at [docs/design.md](docs/design.md) carries the reasoning, the premise, and the considered-and-rejected register, and it links to the issue rather than competing with it. The design doc's `## How work is cut and ordered` carries the rules behind the order, meaning how a slice is cut and how the next one is picked. The slice itself lives on the tracker, in the three parts that section lists. Read an unbuilt deliverable's issue before proposing a change to it. Read the design doc for everything else, which includes every built deliverable and the reasoning behind all of them.

The price of this is named rather than hidden: the same substance now exists in an issue and in the doc that reasons about it, so the two can drift. The issue wins. When they disagree, the doc is what gets corrected.

## Rank work by what makes the product usable

Whatever the premise names as the thing that must not fail ranks first, and the tracker carries what each deliverable and each slice waits on, in its "blocked by" links. This directive decides what to take next from the work those two allow, and what decides it is not severity. Before proposing an order, name what is missing from the shortest path to a product someone can use, and put that first.

Then ship it, use it, and let what breaks set the order after that. Evidence from real use outranks any ranking made in advance, including this one.

For everything else in the product's own code, ask how many times the path has run, and give the count. Zero means defer the work, and write the deferral on its issue so the next reader finds it rather than only the next message.

Three exceptions come from the same reasoning.

1. A path that can lose or corrupt data the project cannot recapture is never deferred. That data is gone forever, while everything computed downstream is regenerable.
2. An alarm reads zero while it is healthy, so the count says nothing about it. Dead-man checks, watchdogs, canaries, and backups sit outside this rule. Count the cycles they watched, not the times they fired.
3. A guard whose price is paid by building it late is not cheaper deferred. A read path that must exclude quarantined records is inert until something writes a verdict, and adding the exclusion afterwards leaves a second read path that skips it.

Three measurements in the sibling `marketlake` repository produced this rule, and they are cited here as the evidence behind it rather than as facts about this repo.

1. Its daemon slice stood at 43 issues closed and 32 open while its read-layer slice stood at 0 closed.
2. Its lake held 9,839,816 rows captured on a single day and no supported way to read any of them.
3. Several rounds of work hardened an overflow column that was non-null on zero of 9,846,266 sealed rows.

Ranking by severity never runs out of work, because any path with no test behind it can be called a failure waiting to happen. That is how three rounds of hardening reached one capture path while the data stayed unreadable.

Cut a large deliverable down to the part that runs against what the project already holds. Its issue stays the source of truth for what the deliverable is, so the cut is proposed there first. The shipping pull request then writes `Part of`, and the issue keeps the remainder, per the closing rule below.

The price of this is named rather than hidden. Shipping the usable path first leaves gaps open on paths nothing has exercised, and one of them will eventually cost something. That is accepted on purpose, inside the three exceptions above. A product nobody can use produces no evidence about which hardening mattered, so the deferred work is also the work with the least evidence behind it.

## Audit an issue's plan before starting work on it

An issue is where a plan lives, and a plan is a hypothesis about work that has not happened yet. What usually makes one wrong is that the files it names moved after it was written. So the trigger is narrow rather than universal. Run `git log` on the files an issue names, bounded by the issue's own date, and audit the plan when they have changed. A plan written against files that have sat still is a plan nothing has invalidated. The session that spawns the work runs the audit before it spawns, since that is the last moment a correction can reach the issue ahead of the reader who acts on it.

Two checks have each already caught something in the sibling repository this rule came from.

1. Check the issue's stated blocker against the current code. One issue said pruning a read down to one record would rest on the writer's incidental row ordering. Parquet skips only the row groups whose statistics prove they cannot match, so ordering decides how many groups are skipped and never which rows come back. A fixture written in deliberately shuffled order returned every row a full read returned, the writer was never involved, and the work stayed in the reader.
2. Read what the code already decided in writing. One module's docstring ended by stating that nothing in it read a config file, which was a deliberate decision. A session meeting that sentence mid-change either deletes it quietly or stops to ask. The issue body had already answered it in advance, so the work arrived knowing what the sentence was protecting and corrected it rather than deleting it.

An audit is a plan too, so it names the commit it was derived against. One audit cited a line number and a call-site count that a merge thirty minutes later moved. Pin line numbers to a named commit and tell the reader to re-sweep for the class rather than trust the list.

A correction goes on the issue, because a spawned session reads the issue and reads none of the conversation that started it. An audit that found nothing reports that to whoever asked for it and writes nothing, since an issue padded with empty notes is harder to read, which is what writing to the issue was meant to protect.

Where the audit finds the code contradicting the issue, the issue still decides what the deliverable is, per the tracker directive above. What changes is that the code's stated reason becomes something the issue answers in advance rather than something the work runs into halfway through.

The price is a pass over the files before work starts, paid on issues whose files have moved. The same evidence that sets the trigger also bounds it. In the repo the rule came from, two audits found something, both on issues naming code that was still moving that day, and seventy closed issues before them are not cited.

## Writing style

The owner's global `~/.claude/CLAUDE.md` is the source for these rules. This section repeats them because the repo is public and a reader or an agent may arrive without that file. The price is that the two copies can drift. The global file wins, and this section is what gets corrected.

Clarity comes first. Write plain sentences a reader understands on one read. Prefer short, complete sentences, but never at the cost of clarity. Do not chop an idea into cryptic one-idea fragments. When a short sentence turns hard to parse, write the clear sentence instead, even if it runs a little longer. Explain as you go, like teaching, so the reader follows without backtracking. Avoid em dashes and semicolons. This applies to every prose surface: this file, the design doc, commit messages, pull request bodies, chat replies, and the words in an architecture or design diagram.

**Impersonal voice.** Write without the first person. No "I," "my," or "mine." The subject is the process, the mechanism, or the finding, not the author. "Running the script reproduced the result" beats "I ran the script to reproduce it." Keep it active, not passive: "The check reads the config," never "the config is read." Direct advice stays as an imperative. Drop the explicit "you" and "your" where it reads cleaner.

**Explain every concept on first use.** Coined vocabulary, borrowed tools, and non-obvious behaviors get their gloss where they first appear, not in a glossary. If a reader must ask "what is X," the writing failed at X's first appearance.

**Drop the jargon rather than glossing it.** Given the choice between defining an in-group term and deleting it, delete it. The test: when a sentence names a concept where it could say what happens, say what happens. "No test covers it" beats "it is unheld." A gloss works once, at first use, while the term keeps reappearing and costs the reader attention every time. Being native to a repo does not save a term. Cut the whole family at once, since the same idiom usually survives under a second word. One exemption: the design doc's pinned vocabulary, which carries exact definitions and is reused on purpose.

**List a counted set. Do not inline it.** When a sentence names a count of items, like "four seams" or "three tests," the items follow as a list, not a run-on of sentences. Number the list when the prose states the count. Use a bulleted list for an unordered set with no count.

**Lead with why it matters, show the reasoning, and name the price.** Establish why something matters before explaining what it is. State the claim, then walk through why. When a choice carries a cost, name it outright, as in "the price for X is Y." When weighing two options, hand over the metric that decides between them instead of gesturing at "tradeoffs."

**Cut what carries nothing.** Throat-clearing, significance-announcing pivots, self-effort asides, hedging, redundancy, decorative modifiers that survive the subtraction test, unsubstantiated superlatives, reversal scaffolding, reassurance tags, and a closing moral that restates the heading. The global file carries the worked examples for each.

**A diagram's words follow the rules a blog post follows (owner directive, 2026-11-06).** A reader takes a diagram as the short version of the text beside it, so a label written as shorthand fails the reader the way a cryptic sentence does. So these rules govern every label, note, edge and legend in an architecture or design diagram.

1. A label says what happens, in a plain phrase with a verb and its actor clear. Write "dies before the broker answers" rather than "dies before the ack". A label that only names a component or a participant needs no verb.
2. A term a reader has not met is dropped, or the text beside the diagram explains it. An abbreviation gets the same treatment.
3. A label holds one idea. Several ideas become several arrows or a note, and a long label wraps.
4. Code identifiers, state names, entry names and the design doc's pinned vocabulary stay exact, and a restyle changes no fact, actor, arrow or order.

**Say what a rule says, then point to it (owner directive, 2026-11-06).** A number chain such as "under case 3 of rule 5 of design.md's `### A fill is measured from the decision`" makes the reader open another file to learn what the sentence means, and the number breaks when the list moves. So a design doc, a charter, a CLAUDE.md or a diagram states what the rule requires in plain words, and a link to the section by name follows for a reader who wants more. A section link alone is fine where the sentence already says what happens. A list item in view of the sentence naming it needs no gloss, and neither does a heading.

<!-- TEMPLATE: replace OWNER/REPO in the two link forms below with this
     repository's owner and name, such as l3a0/new-repo. -->

**Link every issue and pull request number (owner directive, 2026-09-26).** In a chat reply, a message to another session, or a Markdown file in this repository, each number is a Markdown link: `[#NN](https://github.com/OWNER/REPO/issues/NN)` for an issue and `[PR #NN](https://github.com/OWNER/REPO/pull/NN)` for a pull request. A number written out in prose, like "issue 52", takes the same link around the words. Link every mention, not only the first, including numbers inside lists, tables and summaries. A bare `#NN` in chat is text the owner has to copy into a browser, and GitHub renders a bare `#NN` in a repository file as plain text too. A report that links its first number and leaves the rest bare fails the same way. A number that belongs to another repository links there.

The prefix still matters. Issues and pull requests share one number space, so a bare number cannot tell the reader whether it names scope or work in review. An issue is `#NN` and a pull request is `PR #NN`.

Two places keep the bare form.

1. **GitHub's own text.** In an issue body, a comment, a pull request body or a commit message, GitHub links a bare `#NN` on its own, and a closing keyword needs the number right after it.
2. **Code and quotations.** A command, a code span, a file name or a quoted commit subject stays exactly as written, because a link inside it breaks it.

## The design doc carries the reasoning

Two conventions keep [docs/design.md](docs/design.md) usable as the project grows.

- **The considered-and-rejected register.** Cut machinery is pinned in the doc with its rationale, so nothing gets re-proposed after it was decided against. When something new is cut, pin it the same way.
- **Pinned vocabulary.** Terms with exact definitions are listed and reused. Do not coin synonyms for a term the doc already defines.

One lesson is worth keeping in view. Reviews armor what exists. They rarely ask whether it should exist. Ask "why is this needed" before "is this correct."

## Design for 10x, across the whole lifecycle

The owner's global `~/.claude/CLAUDE.md` is the source for these two rules. This section repeats them because the repo is public and a reader or an agent may arrive without that file. The price is that the two copies can drift. The global file wins, and this section is what gets corrected.

**Design for 10x, plan the rewrite before 100x, build at 1x (owner directive, 2026-11-03).** This is Jeff Dean's rule, as Sam Newman's *Building Microservices* quotes it: design for about ten times growth, and plan to rewrite before about a hundred times (BM L4428). The owner adopted it on 2026-11-03 in place of the earlier directive to design for 100x. Every architecture is designed for 10 times the load it first carries, and its first version, the MVP, is built at that first load.

A design passes when reaching 10x takes configuration and more infrastructure, such as more instances, more machines or more partitions, and no rewrite of a component, a file format or a rule. The parts that only matter at 10x are designed now, built when load calls for them, and drilled before anything relies on them. Beyond 10x the design expects a rewrite rather than promising to avoid one, so it writes down three things.

1. The load parameter and the level, short of 100x, at which planning the rewrite starts.
2. What it expects the rewrite to replace.
3. What must survive the rewrite unchanged, such as recorded data and its formats.

That last point keeps the rewrite from becoming a migration of data that cannot be recaptured. This fits the ranking rule a repo's own CLAUDE.md carries, which defers a path that has run zero times. Two things are built at 1x all the same.

1. The measure of load, and the alarms that say when it nears the 1x limit and when it reaches the level where the rewrite's planning starts. Otherwise the first sign of either is an outage, and an alarm already sits outside that deferral.
2. Least privilege, so a credential carries only what its 1x use needs from the first day.

On 2026-11-02 an architecture review of l3a0/ithildin-runtime had written a cluster of three VMs into its first slice, and the owner moved the cluster to the scale-out path and started the slice on one VM. On 2026-11-03 the owner read Dean's rule in Newman's book and adopted it, because a design that promises no rewrite at 100x tends to build for load it may never see.

**Weigh the whole lifecycle (owner directive, 2026-11-02).** A design considers every stage of the software development lifecycle, from planning, building and testing through deploying and operating to retiring, and follows best practice for ten qualities.

1. Scalability.
2. Availability.
3. Security.
4. Operability.
5. Monitoring.
6. Auditing.
7. Testing.
8. Performance.
9. Usability.
10. Deployment.

A design that serves one stage and breaks another, such as a fast path no test can reach or a deployment nobody can roll back, is not finished. A design pull request says which of the ten it changes and what each change costs. A quality it leaves untouched needs no line.

[docs/design.md](docs/design.md)'s `## Design for 10x, plan the rewrite before 100x, build at 1x` and `## Every design weighs the whole lifecycle` are where a repo records how it applies them, including what 1x, 10x and the rewrite point mean for it and where each of the ten qualities lives. Its `## Design principles` holds the checks a review applies to every design.

## What a design here must hold

The owner's global `~/.claude/CLAUDE.md` is the source for these rules, under `## Designing systems`, `## Writing design and architecture documents` and `## Asking the owner`. This section repeats them because the repo is public and a reader or an agent may arrive without that file. The price is that the two copies can drift. The global file wins, and this section is what gets corrected. A line that names this repo's exception overrides the global file, as that file's opening allows.

**Each rule came from a correction during the architecture review on [l3a0/ithildin-runtime PR #15](https://github.com/l3a0/ithildin-runtime/pull/15) (owner directive, 2026-11-05).** A design or architecture change here meets all of them from its first draft.

1. **Try what already exists first.** Before proposing a new store, encryption key, credential, account or long-running service, try, in this order, data already held, a narrower permission on an existing role, and a managed default or a rule that needs no new credential. Say why each that does not serve fails.
2. **Depend on a neighbouring system's contract, never on its internals.** State what is read from a neighbour, how long it stays readable, and what happens when it is absent, and name no unpublished step of how the neighbour produces or removes it. The system that owns a step runs it alone and never holds it back for another system. A fallback reads the same published values from another published place, never a default or an older value, and where none is written, a missing input stops the work.
3. **A machine holds no state.** Each component runs as its own container, and a replacement machine loses nothing, because inputs and outputs live as blobs in durable storage and a record points at them. A process resumes by reading what storage holds and retrying what is safe to repeat. An outside write with no answer is looked up first, and resent only where the outside system proves a repeat cannot act twice.
4. **Fit the workload the product is heading for.** A first version that runs in a few short bursts a day is no argument for a host or a messaging design that only fits bursts. The build still starts at the first load.
5. **One convention per kind of value.** Every time the system writes is UTC, and a value received from outside stays as it arrived, with its UTC instant beside it. A setting tied to another value that can move is stated relative to it, such as minutes before a market's close.
6. **The body says what is true, and one section holds every decision.** Body text never says who decided something, when, or on which issue. Every decision is one dated entry in one section, oldest first, with a link to where it was made and the section it governs. A later decision gets its own entry, and the earlier entry stays. A proposal keeps its label until it is ruled on. New text follows this, and an existing inline ruling stays until someone moves it.
7. **Structure a document for a reader with no context.** Give each question its own subheading and break a mechanism into numbered steps. Draw a mechanism with several actors or steps, and a data type as a UML class diagram, and show the variations a figure leaves out. Title every table, as Markdown hygiene below says. Link every source the text leans on. Render each figure and read the words it drew before reporting it done.
   - **Pick the figure a reader understands fastest, not Mermaid by default.** Mermaid suits a flow, a sequence of calls, a set of states or a data type, because its source sits in the document and changes with the text. A sketch suits what boxes and arrows cannot show, such as a level that fills and drains, a quantity drawn to scale, or a physical picture like a bucket of tokens. Draw a sketch in the style of the sketch notes on l3a0/quantitative-trading's blog: an animated whiteboard GIF that a scene module draws with the shared whiteboard helpers in l3a0/ithildin-core, which [l3a0/ithildin-core#24](https://github.com/l3a0/ithildin-core/issues/24) moves there, with tests that pin its words, colours and figures, as l3a0/quantitative-trading's [`sketch-notes` skill](https://github.com/l3a0/quantitative-trading/blob/main/.claude/skills/sketch-notes/SKILL.md) describes. Until that issue lands, the helpers live only in l3a0/quantitative-trading, and no repository copies them, so a sketch for another repository waits for it. Place a sketch right after the text it draws, give it alt text that says what it draws, and change it in the same commit as that text. A figure drawn to scale reads its numbers from the source the text quotes, never typed twice. A figure never repeats what a table beside it already says.
8. **Diagrams, tables and figures are prose.** A ruling changes the body, every diagram that shows the old behaviour and the decisions section in one commit. Check every value stated twice against its source, and a number copied from an issue against that issue's latest comment. Re-read a long-lived design branch when `main` moves.

**A question to the owner carries its own answer.** Look up whatever a vendor's page, a connected account or the code can settle. Bring one recommendation, the metric that decides between the options, and the price of each, in plain words that stand alone. A question on money, contracts or law goes to the board of advisers that `/l3a0:ask-board` convenes, and it names what is decided, the metric and any price already measured, and carries no recommendation.

**Keep the work where the owner put it.** A change on the same issue as an open pull request goes on that pull request, not on a new one, unless the owner says otherwise.

## Markdown hygiene

Every `.md` file must pass markdownlint, which CI runs on every pull request. The rules that bite most: use real headings, never a bold line as a heading (MD036). No trailing whitespace (MD009). No stacked blank lines (MD012). End the file with exactly one newline (MD047). Table delimiter rows use single-space padding, so `| --- |` and never `|---|` (MD060). Escape an "approximately" tilde in prose as `\~`, since a bare tilde can render as strikethrough on some surfaces. Code fences are exempt.

Every table has a title, on a line of its own above it, starting with `**Table:**`, because Markdown has no caption (owner directive, 2026-11-05).

markdownlint has no rule for the tilde, for a table whose rows are tight throughout, or for a table with no title, so `tests/test_markdown_hygiene.py` carries all three. Run `uv run pytest` after editing prose. It reads every Markdown file the repo owns and blanks fenced blocks and backtick spans first, which a grep cannot do: a grep for these patterns reports the sentence that documents them.

When a heading changes, verify the Contents anchors still resolve.

## Running things

[README.md](README.md) carries the local commands and the steps for seeding a
new repo from this template. `scripts/setup-repo.sh` applies the ruleset,
the labels and CodeQL to a repository, reading them from
`.github/rulesets/default.json` and `.github/labels.json`. Take `DRY_RUN=1`
first if you want to see what it would send.

## Cross-surface consistency

A repo drifts when two surfaces describe the same thing and only one gets updated. The fix is to give each surface exactly one job, so nothing is stated twice.

- **The test suite is the single authority for any number the prose quotes.** Prose states these numbers and never derives them. A document that recomputes a number is a second implementation of the calculation, and the two drift without either one looking wrong. This is the only place that rule is stated. Module 1 in [docs/optional-policies.md](docs/optional-policies.md) carries what it costs in practice, not the rule itself.
- **The design doc is the single authority for reasoning.** Code comments point at it rather than restating it.
- **The issue is the single authority for unbuilt scope**, per the tracker directive above.

<!-- TEMPLATE: list this repo's prose surfaces and what can drift between them.
     The sibling `trading-strategies` repo's list is the worked example: line
     anchors of the form `file.py#L12`, symbol names cited in prose, pinned
     numbers, figure embeds, and generated artifacts that must be regenerated
     rather than hand-edited.

     Delete this comment and keep everything else under this heading. The two
     paragraphs below it apply to every repo, however many surfaces it has. -->

Before reporting a code change done, sweep the prose surfaces for what the change could have invalidated, and end the response with a short **Consistency sweep** note listing what was checked, what was updated, and what is still stale. For a pure-internal refactor that moves no line numbers and changes no observable behavior, say "no prose-facing surfaces affected" so it is clear the check was considered rather than forgotten.

A mechanical consequence of an edit is part of that edit, not a separate decision. When a change leaves a generated artifact stale, regenerate it in the same change without asking.

## Secrets and machine paths

This repo is public. Tracked files never carry secrets or machine-specific paths. Machine-local config lives under `~/.config/PROJECT_NAME/`, and the design doc's Configuration section states the full rules. Sweep for leaks before any publish.

<!-- TEMPLATE: name this repo's secrets and where they live. Credentials,
     tokens, ping URLs, and notification topics are all secrets. A path that
     names a machine or a person is not a secret but still does not belong in
     a tracked file. -->

## Committing

**Commit, push and open the pull request without waiting.** A session that has finished the deliverable it was given commits it, pushes the branch, and opens the pull request on its own. It does not stop to ask first.

An earlier version of this rule asked for explicit approval before every commit. The cost was a session idle on finished work whenever the owner was away from the keyboard, and the approval bought nothing the pull request's own diff does not show better and later.

Three things still hold.

1. `main` requires a pull request. An active repository ruleset enforces it. Owners can bypass that rule, but do not: branch, push, and open a PR, even for a one-line docs change.
2. A commit carries only what the session actually did. Unrelated edits found on the way past are filed as their own issue, per the closing rule below, and never swept into the branch.
3. Work outside the session's own deliverable still waits for the owner. That covers this file and anything under `~/.config/`.

Branch before the first edit, not just before the commit. The moment a task will modify any tracked file, run `git branch --show-current` and branch if it shows `main`. Re-check before every commit, not just the first of a session, because a mid-session squash-merge deletes the branch and leaves the checkout on `main`.

## Pull requests

**Review every pull request before the owner does.** A PR the owner has not seen reviewed is not finished work. This holds whether the PR is yours or someone else's, whether it is one line or a thousand, and whether or not a review was asked for. The owner's time is the scarce thing, so a PR reaches them already checked rather than waiting to be read cold.

**Send the link as soon as the pull request exists, then review it.** Opening the pull request and starting the review are one step, and neither waits on the owner. The link is what lets them watch the review land, so holding it back leaves them blind to work that is already pushed. Post the findings on the pull request, and say plainly what the review found and what it refuted, including when it found nothing.

Review by fanning out independent lenses, then verifying each finding adversarially. Several reviewers in parallel, each with one lens and no sight of the others, produce the findings. Verifiers then try to refute each one, and only what survives is acted on. Point one lens at completeness and one at over-reach, which catch the two failures that recur:

1. Fixing the instance rather than the class, such as a false claim corrected in one file while it still stands in three more.
2. Fixing past the class, such as generalising a change into places it does not belong.

**Consult the build team on every review (owner directive, 2026-10-29).** Beside completeness and over-reach, run `/l3a0:ask-team` in its lens mode. It seats the engineering roles the change touches, such as a risk engineer on a path that sends orders or a data engineer on data that cannot be recaptured, as more blind lenses, and returns their findings to the review rather than posting them. Their findings go through the same refutation pass as every other lens before anything is acted on, and the review folds what survives into its own comment. The skill ships in the `l3a0` Claude Code plugin from 0.5.0, which `## Keep the build board current` below says how to install. A review that cannot run it says so rather than skipping it silently.

Verify by executing, not by reading. Mutate the code and confirm a test fails. A test that still passes under mutation does not cover what it claims to cover.

**Watch the checks and fix what they find.** A pull request is not handed over until its checks have run and settled. Pushing is not the end of the work, because the branch that passes locally is not the branch CI builds. CI builds the merge of the branch and its base, and the base moves.

So watch the run rather than assume it. `gh pr checks <n> --watch` blocks until every check settles, and `gh pr view <n> --json statusCheckRollup` says what each one concluded. When a check fails, read its log, fix the cause, and push again, in the same session and without waiting to be asked. A red check the owner finds first is work handed over unfinished.

Three behaviours make the rule sharper than "look for a green tick". The first two were measured on pull requests in the `marketlake` repo this rule came from, and the third on this template's own first day.

1. **A conflicting pull request gets no run at all.** A `pull_request` workflow builds the merge ref, and a branch that conflicts has none, so no run is created. [PR #414](https://github.com/l3a0/marketlake/pull/414) there showed three green CodeQL entries and no `test` run whatsoever. An absent check reads as a short rollup rather than as a failure, so count what ran instead of scanning for red.
2. **Green goes stale.** A run is computed against one merge ref, and a later merge to the base replaces it. [PR #433](https://github.com/l3a0/marketlake/pull/433) there read green after the branch had already conflicted underneath it. Re-read the rollup whenever the base has moved.
3. **Red goes stale the same way, and costs more.** A failure inherited from the base survives in the rollup after the base has been fixed. This template's [PR #3](https://github.com/l3a0/repo-template/pull/3) carried a red `test` check from a run computed 25 seconds before the pull request that fixed its base merged. Rebasing made it green, and a monitor reading the older snapshot reported the failure again afterwards. A red check is a claim about one merge ref at one moment, so re-read it before acting, and check whether the pull request has already merged before fixing anything.

Fix the cause rather than the symptom. A lint rule that fails on one file usually fails on its siblings, so sweep for the class. Re-running a job changes nothing the second time unless the failure was the runner rather than the code. Where a failure comes from another branch's merge rather than from this change, say so on the pull request instead of absorbing an unrelated fix into it.

**A filed issue carries its milestone and its labels.** Filing is not finished when the issue exists. An issue with no milestone appears in no slice view and no view scoped by kind, so only a sweep for nulls finds it, and nothing brings it back on its own. So a filed issue is finished when it says three things.

1. A milestone says which slice owns it.
2. A label says what kind of work it is.
3. A dependency says what it waits on, where it waits on anything.

No automation supplies the first two. The same applies to an issue a spawned session is told it may file. The instruction to file carries the instruction to triage, or the work lands where nothing will look for it.

**Close an issue only when nothing is left in it.** Before a PR closes an issue, move whatever that PR does not do into its own issue. A piece described only inside a body goes when the body closes, and nothing surfaces it again.

While a piece is outstanding, a PR writes `Part of #NN` and the closing keyword waits for the PR that leaves nothing. GitHub reads the keyword only when the number follows it immediately, so `Closes the second half of #101` closes nothing at all. The keyword also has to be plain text, and a code span around it defeats it the same way. Rendered, a code span and plain text differ only in font, so reading the body back does not distinguish them. `gh pr view <n> --json closingIssuesReferences` does, and an empty result on a pull request that means to close something is the signal to fix the body before merging.

An issue whose pieces have all been split has no finishing PR left, so close it by hand and name where each piece went. Do the same when two PRs are open against one issue, because merge order decides which lands last and neither body can know it. A split leaves code comments pointing at the parent for work that moved, so repoint those in the PR that splits. A comment naming a closed issue in the past tense records what happened rather than pointing anywhere, and it stays.

PR titles use a Conventional Commits prefix. The form is `type(scope): summary`. `gh pr list --state merged --json title` reports which prefixes this repo has used, rather than a list here that goes stale on the first unfamiliar one. Add a scope in parens when it sharpens the title, like `docs(CLAUDE.md)`. Drop it when none does, like a plain `docs:` for a whole-doc change.

PR bodies use Markdown section headings, not a wall of prose. Lead with `## Why`, then `## What`. Add situational sections after as the change needs them, like `## Scope`, `## Notes`, `## Evidence`, or `## Qualities`, where a design pull request names each of the ten qualities it changes and the price. The body's prose obeys the writing-style rules above. So clear, short sentences and no em dashes. End every body with the footer line: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Keep the build board current

The build board is a page on GitHub Pages that answers what is in flight and what to take next. A GitHub Action rebuilds it from GitHub on every issue, comment and pull request change and on a schedule, so no session writes it. What the board cannot read from GitHub on its own is judgement: which cards are ranked and in what order, which session holds a card, whether a plan is finished, and what a card waits on. A session that makes one of those calls and does not set it on GitHub has made the board wrong, and nothing else notices.

So a session sets the matching label, "blocked by" link, marker line or `## Review` comment at the moment it makes the call. The `update-build-board` skill in the `l3a0` Claude Code plugin owns the formats and the full list of moments, and the plugin's `sync-prune-next` skill runs the status round that checks them. This repository keeps no copy of either skill, because the copies each repository once kept drifted apart. Install the plugin at 0.5.0 or later on each machine that runs a session here. These commands install it for the user, so it serves every repository on that machine, and they follow the plugin's `main` rather than a fixed version. Every session then runs what that `main` holds, including the plugin's hooks.

```bash
claude plugin marketplace add l3a0/claude-plugins
claude plugin install l3a0@l3a0
```

The skill leaves what each `band:N` label means to the repository, so a session reads it here.

<!-- TEMPLATE: say what band:1, band:2 and band:3 mean in this repo, under
     the ranking directive at the top of this file. For example, band:1 is
     the shortest path to a product someone can use, and band:3 is work that
     waits on evidence from using it. -->

## Repo-specific policy

<!-- TEMPLATE: policy that only this repo needs goes here. Two modules ship
     with the template in docs/optional-policies.md, ready to move into this
     section when the repo needs them:

       1. Research pins, for a repo whose prose quotes measured numbers.
       2. Cross-surface sweeps, for a repo with generated artifacts.

     Paste the module's text under this heading, adapt its names to the repo,
     and keep the heading. Delete the heading only if the repo needs neither
     module. -->
