# Design — PROJECT_NAME

<!-- TEMPLATE: this doc carries the reasoning. The tracker carries unbuilt
     scope, and this doc links to an issue rather than restating it. Write the
     premise first and leave the rest to grow as decisions get made. -->

## Contents

- [Premise](#premise)
- [Design for 100x, build at 1x](#design-for-100x-build-at-1x)
- [Every design weighs the whole lifecycle](#every-design-weighs-the-whole-lifecycle)
- [Design principles](#design-principles)
- [How work is cut and ordered](#how-work-is-cut-and-ordered)
- [Vocabulary](#vocabulary)
- [Configuration](#configuration)
- [Considered and rejected](#considered-and-rejected)

## Premise

<!-- TEMPLATE: the premise is the one thing this project must get right, and
     the reason it must. Every ranking decision appeals back to it, so it is
     worth more than a sentence.

     marketlake's premise is capture reliability: a minute of option chain data
     not recorded at the moment it existed is gone forever, while everything
     computed from a captured minute can be recomputed. That asymmetry is what
     makes its capture path the one thing that never gets deferred.

     Name the equivalent asymmetry here. If nothing in the project is
     irreversible, say that, because it changes what the ranking rule in
     CLAUDE.md protects. -->

TODO.

## Design for 100x, build at 1x

<!-- TEMPLATE: say what this project's first load is, in the load
     parameters the design principles below ask a design to name, what 100
     times it would be, what carries the design to 100x without a rewrite,
     how load is measured and what alarm says it nears the 1x limit, and
     which 100x parts are designed now and built later. CLAUDE.md carries
     the rule. -->

TODO.

## Every design weighs the whole lifecycle

<!-- TEMPLATE: for each of the ten qualities CLAUDE.md lists, point at the
     section of this doc or the code that carries it, or say that the
     project does not have it yet. -->

TODO.

## Design principles

<!-- TEMPLATE: these rules hold for any repository seeded from the template.
     Add the project's own principles under headings of their own after
     them, each with the check a review runs and its source. A rule that does
     not fit the project moves to the considered-and-rejected register with
     the reason, so the decision stays visible. -->

A principle earns a place here only when a design can pass or fail it. Each
rule below names what a review checks and the reason behind it. The rules come
from Martin Kleppmann's *Designing Data-Intensive Applications* (1st ed.,
O'Reilly Media, 2017), cited by Kindle location, so DDIA L293 is location 293.
They cover what goes wrong in any system that stores data, calls another
system or reads a clock. Parts fail, clocks drift, retries repeat, writers
race, and stored records have to outlive the bugs in the code that reads them.
The rules serve the book's three goals for maintainable software: operability,
simplicity and evolvability (DDIA L645, L646, L648).

These are checks on a design, and a review applies all of them. The mechanism
a rule names is built when the path it guards first runs, under the ranking
rule in [CLAUDE.md](../CLAUDE.md), and no sooner. That rule's three
exceptions decide what is built from the first run whatever the count.

1. Whatever keeps data the project cannot recapture from loss or corruption,
   such as checksums, append-only storage and backups.
2. Alarms, such as the checks a running system makes on its own guarantees, a
   clock-offset monitor and every queue's lag alarm.
3. Guards whose price is paid by building them late, such as the id that drops
   a repeated write and the fencing token on a lease.

### Faults are expected, and the system checks itself while it runs

1. **Every fault the design says it handles is caused on purpose in a test.**
   DDIA separates a fault, where one part leaves its specification, from a
   failure, where the system as a whole stops serving its users (DDIA L293).
   Faults cannot be prevented, so a design keeps them from becoming failures.
   Many serious bugs sit in error handling that rarely runs, so the book
   recommends causing faults deliberately, unlikely ones included, to keep
   that handling exercised (DDIA L300, L8461). A design that lists the faults
   it tolerates names the test that injects each one, such as a killed
   process, a lost response, a repeated message or a clock that jumps.
2. **A guarantee the system relies on is checked while it runs, and a mismatch
   raises an alert.** The book's example is a queue that compares the count of
   messages in with the count out (DDIA L372). Faults that share a cause across
   machines produce more failures than independent hardware faults, and the
   bugs behind them wait for the day an assumption about the environment stops
   holding (DDIA L351, L366). A check that runs only before a release misses
   that day.
3. **A case the design calls impossible stops and alerts a person, and never
   continues on a guess.** Real code still needs a branch for what the
   algorithm assumes cannot happen, even when that branch only stops and leaves
   the cleanup to a person (DDIA L9488). The book divides properties into
   safety, meaning nothing bad happens, and liveness, meaning something good
   eventually happens. Safety must hold in every case, while liveness may wait
   on conditions such as a network recovering (DDIA L9454, L9466, L9469). So a
   design names which of its properties are safety properties, and it may give
   up progress to keep one, never the reverse.

### Time comes from the right clock, and order from a sequence number

1. **Elapsed time is measured on a monotonic clock, order comes from a
   sequence number, and a dependence on wall-clock time has its offset
   monitored.** A time-of-day clock can jump backward when the time service
   resets it, and a paused virtual machine sees it jump forward (DDIA L8811,
   L8878). A monotonic clock measures intervals on one machine, and its
   readings mean nothing on another (DDIA L8823). A counter orders events
   without measuring time, which the book calls the safer way to order them
   (DDIA L8966, L10533). Clocks drift, a machine cut off from its time servers
   can go unnoticed, and a time server can be wrong by hours (DDIA L8846,
   L8853, L8859). So software whose correctness rests on synchronized clocks
   monitors each machine's offset and takes a machine out of service once it
   drifts past a stated bound (DDIA L8913).
2. **A computation that must reproduce reads the time, random numbers and
   reference data from inputs it records, and data from outside keeps its
   event time beside its receive time.** A statement that calls the current
   time or a random number gives a different result each time it runs (DDIA
   L4912), so a replay or a test of it cannot repeat. So code reads the time
   through an injected clock and random numbers from a recorded seed.
   Reference data that changes, such as a rate or a limit, gets an identifier
   for each version, and a result records the version it used (DDIA L14943).
   Event time is when the source says something happened, and receive time is
   when this system got it. Mixing the two makes a backlog processed after a
   restart look like a burst of activity (DDIA L14747). A clock outside the
   system's control may be wrong, so the book keeps the sender's timestamp and
   the receiver's side by side and estimates the offset between them (DDIA
   L14784, L14788). Neither overwrites the other.

### Writes happen once, from one writer at a time

1. **A write to another system carries an id fixed before its first attempt,
   and the receiver drops a repeat of it.** A request that timed out has an
   unknown outcome. It may have landed with only its response lost, so a retry
   performs it twice unless the receiver removes duplicates (DDIA L4204,
   L4207). The retries at each layer below cannot see one another, so only an
   id carried from end to end can drop the duplicate (DDIA L16438). A
   timed-out write is recorded as unknown rather than failed, until a read of
   the receiver settles it.
2. **A lease or a lock is enforced by a fencing token that the protected
   resource checks, and no id comes from a counter that a failover can wind
   back.** A process can pause past the end of its lease, in a
   garbage-collection pause or a suspended virtual machine, then wake and act
   as if it still held it (DDIA L9084, L9094, L9102). A fencing token is a
   number each grant of the lease carries, higher than every earlier grant,
   and the resource refuses a write whose number is lower than one it has
   already accepted (DDIA L9274, L9286). A resource that cannot check a token
   itself still needs a workaround, such as carrying the token in the name it
   writes (DDIA L9292). The book's case against a counter is a promoted
   replica whose lagging counter reused keys another system already held
   (DDIA L4868). A test pauses one holder past its lease, grants the lease to a
   second, resumes the first, and asserts that its next write is refused.
3. **A read-modify-write on shared state is atomic, or every write that may
   conflict goes to one partition and runs in order.** Two writers that each
   read a value and write back a change lose one of the changes (DDIA L7374).
   Two writers that read the same data and then update different parts of it
   can together break a rule each one checked, which the book calls write
   skew (DDIA L7538). Its remedy without a distributed transaction is to route
   every write that may conflict to one partition and apply them one at a time
   (DDIA L16535). A single thread in a loop can even outrun a concurrent design,
   because it skips the cost of locks (DDIA L7725). A design names each piece
   of shared state and which of the two protects it.
4. **Coordination is paid for only where a broken constraint cannot be
   repaired, and never through a distributed transaction or a consensus
   algorithm written here.** The book separates timeliness, meaning a reader
   sees the latest state, from integrity, meaning no state is ever wrong. A
   lapse in timeliness heals on its own, and a lapse in integrity stays (DDIA
   L16612, L16626). Many businesses accept a briefly broken constraint and
   apologize for it, and coordinating only where it is needed buys speed and
   availability everywhere else (DDIA L16676, L16700, L16711, L16712).
   Two-phase commit, the usual protocol for a transaction across systems,
   needs every participant to answer, so one broken part fails them all, and
   its coordinator is a database whose loss leaves locks held until someone
   steps in (DDIA L11174, L11150, L11110). Consensus is hard enough that the
   book advises using an existing coordination service over writing one's own
   algorithm (DDIA L11247, L11519). So a design names the few constraints that
   must never break, coordinates those, and lets everything else lag.

### Recorded data outlives every bug

1. **Each fact has one system of record, which only appends, and everything
   else is derived from it by a command that can run again.** A system of
   record holds the authoritative version of a fact, written there first, and
   where a derived copy disagrees, the system of record is right by
   definition (DDIA L11985). Append-only files make crash recovery and
   concurrency simpler, because a crash cannot leave a value half overwritten
   (DDIA L2484). So a correction is a new record that points at the one it
   corrects. Recording the intent of an action, rather than its side effects
   on tables, lets a later feature derive new results from old records (DDIA
   L14319). A derived view is rebuilt by a command rather than repaired by
   hand, since tools that recompute data are one of the book's ways to
   recover from human error (DDIA L391).
2. **A new view or a batch output is built beside the old one and switched to
   in one step, and the old one stays until nothing reads it.** When data is
   written in one form and read through several derived views, a new view can
   run alongside the existing ones without changing them (DDIA L14461, L14470).
   The book's batch example writes new files beside the old, switches over
   atomically, and can switch back because the old files remain (DDIA L12811,
   L12822). Inputs stay read-only, so a run can repeat without harm (DDIA
   L12311). A change to how data is read follows the same path, so the system
   of record stays as written and only the derived views move.
3. **Data from outside is stored as received and checked before use, and
   nothing stored or received is decoded with a language's built-in
   serialization.** Making raw data available quickly is often worth more
   than settling the ideal model first, and its interpretation can be left to
   whoever reads it (DDIA L12909, L12920). A parser bug then costs a rerun
   rather than lost data. Values are sanity-checked, such as ranges and
   sizes, before anything acts on them (DDIA L9382). A built-in serializer,
   such as Python's `pickle`, ties the data to one language, tends to neglect
   versioning, and lets whoever controls the bytes run code when they are
   decoded (DDIA L3623, L3632, L3626). So every format the project writes is
   language-neutral and carries a version, and readers keep reading every
   version ever written.
4. **Every stored record carries a checksum that each read verifies, and a
   backup copies only closed segments.** The checksums in network protocols
   catch corruption on the wire, but not a bug at either end or corruption on
   disk, so the book calls for a check from end to end (DDIA L16445, L9376). A
   crash can leave a half-written record at the end of an append-only file,
   and a checksum is how a reader tells it from a whole one (DDIA L2471). A
   reader reports such a record rather than dropping it silently, because it
   may be the only trace of an action that already happened. A backup taken
   while writes continue holds parts from different moments, and restoring it
   makes the mismatch permanent (DDIA L7227). A segment that is never written
   again gives a backup a consistent thing to copy (DDIA L2449). A restore
   drill checks record counts and checksums.

### Load is named before it is scaled

1. **A design names its load parameters and the operations it assumes are
   common, and its 100x holds only along them.** A load parameter is one of
   the few numbers that describe load, such as requests per second or records
   per day. The book asks two questions of each one: how performance changes
   when it rises and resources stay fixed, and how far resources must grow to
   hold performance steady (DDIA L482, L484). A scalable architecture rests on
   assumptions about which operations are common, and a wrong assumption
   wastes the scaling work or makes it harmful (DDIA L627). The book also
   finds that an architecture rarely copes with ten times its load, so a
   fast-growing service rethinks it at each tenfold rise (DDIA L598). That
   finding sits beside the directive in [CLAUDE.md](../CLAUDE.md) to design
   for 100 times the first load rather than against it. A 100x design holds
   only along the parameters it names, so
   [Design for 100x, build at 1x](#design-for-100x-build-at-1x) names them,
   and a review checks them against measured use. Load along a parameter
   nobody named is what forces a rewrite. Stateful parts stay on one machine
   until cost or an availability target forces a split, which the book
   reports as the common practice for databases until recently (DDIA L614).
2. **A key maps to a partition through a hash that is stable across
   processes, the partition count is well above the machine count, and
   nothing routes by the key modulo the machine count.** Some built-in hash
   functions give one key a different value in each process, as the book
   shows for Java and Ruby (DDIA L6211). Python's `hash()` on a string does
   the same. Routing by a hash modulo the machine count moves most keys
   whenever a machine is added (DDIA L6411). Many more partitions than
   machines lets a new machine take whole partitions, so no key changes
   partition (DDIA L6418). The count chosen at the start caps the machines
   the split can use, and each partition carries overhead, so the count is
   sized for the 100x load and no higher (DDIA L6443).
3. **Latency is reported as percentiles from merged histograms, and every
   queue has a bound and an alarm on how far behind it is.** A mean hides how
   many requests were slow, percentiles show it, and the slowest requests
   often belong to the users with the most data (DDIA L518, L523, L536). A
   request that waits on several calls is as slow as the slowest, so the tail
   grows with each call added (DDIA L569). Averaging percentiles across
   machines or time windows gives a meaningless number, so histograms are
   added together and percentiles read from the sum (DDIA L583). A backlog
   can grow unseen until a disk fills, as when compaction falls behind the
   writes (DDIA L2766). How far a consumer trails the head of a log is the
   number to alarm on (DDIA L14056). A buffer that drops its oldest entries
   when full (DDIA L14037) loses data, so a queue that holds data the project
   cannot recapture spills to disk or slows its producer rather than dropping
   anything.

The price of these rules is a checksum and a format version on every stored
record, an id on every write to another system, a fencing token on every
lease, histograms in place of averages, and a test harness that can inject
faults. What they buy is stored data that survives the bugs in the code
around it, and a 100x design that holds along parameters it has named.

## How work is cut and ordered

A slice is the smallest set of deliverables that leaves the product usable by
someone at the end of it. Not a layer, and not a subsystem. A slice that ends
with a component nobody can run is a slice cut the wrong way.

Each slice lives on the tracker as three things.

1. A milestone with the slice's name, so a filed issue has one to take.
2. A parent issue holding what the slice leaves usable and the tests that show
   it works, each stated as what a test executes rather than what the code
   looks like.
3. One sub-issue per deliverable.

A sub-issue that cannot start until another finishes gets a "blocked by" link
to it, and a slice's parent issue that waits on another slice gets one to that
slice's parent issue. Name only the dependencies that are real. An invented
dependency is how a plan quietly becomes a layered build.

Order the slices by what the ranking rule in [CLAUDE.md](../CLAUDE.md)
decides: what is missing from the shortest path to a product someone can use
goes first. Then ship it, use it, and let what breaks set the order after
that.

<!-- TEMPLATE: link the current slice's parent issue, and update the line when
     the next slice starts. -->

Slice 1 is TODO, on TODO issue link.

## Vocabulary

Terms with exact definitions, reused on purpose. A term listed here is not a
candidate for a synonym. Anything not listed here follows the writing-style
rule in [CLAUDE.md](../CLAUDE.md), which prefers deleting an in-group term to
glossing it.

| Term | Definition |
| --- | --- |
| TODO | TODO |

## Configuration

<!-- TEMPLATE: name every secret, where it lives, and what reads it. The repo
     is public, so a secret in a tracked file is published. A machine-specific
     path is not a secret but still does not belong in a tracked file, because
     it is wrong on every other machine. -->

Machine-local config lives under `~/.config/PROJECT_NAME/`. Nothing tracked in
this repository carries a secret or a machine-specific path.

| Setting | Secret | Lives in | Read by |
| --- | --- | --- | --- |
| TODO | TODO | TODO | TODO |

## Considered and rejected

Machinery that was considered and cut, pinned here with the reason. The point
is that a decision stays decided. When something new is cut, add it here in
the same change that cuts it.

Reviews armor what exists and rarely ask whether it should exist, so this
register is also where the answer to "why is this needed" gets written down
once rather than re-argued.

| Cut | Why |
| --- | --- |
| A build-plan doc listing each slice's deliverables and tests | It would restate scope the tracker holds, so the two would drift. A slice's tests are its parent issue's acceptance criteria, and what each deliverable waits on is its sub-issue's "blocked by" links. The rule for cutting a slice is the one part GitHub cannot hold, and it lives in [How work is cut and ordered](#how-work-is-cut-and-ordered) |
| A copy of the build board's skills in each repository | Four repositories held their own copies of the build board's skills, and each copy held something the others lacked, which [l3a0/claude-plugins#28](https://github.com/l3a0/claude-plugins/issues/28) inventoried. The skills moved into the `l3a0` Claude Code plugin on 2026-10-29, and a seeded repository installs the plugin rather than copying them. [#24](https://github.com/l3a0/repo-template/issues/24) had kept them per repository because a repository pins the generator to one commit while a plugin skill moves with each release. That is the price, and a second comes with it: every session runs what the plugin's `main` holds, hooks included, with no pull request in this repository to show a change. The plugin skill's `## Generator compatibility` table names the generator commits its formats were checked against. `tests/test_build_board_generator.py` reads the skill at a pinned plugin commit, so renaming a marker or a label the generator reads fails here until a matching plugin release exists. Other format changes rest on the plugin's release rule |
| Holding a reviewed, green branch back only while a build session holds its card | l3a0/marketlake's own page held such a branch back from the owner's queue only for `working:build`. The shared page holds it back for any `working:` label, and [#47](https://github.com/l3a0/repo-template/issues/47) kept that rule when it ported marketlake's review rule. The plugin's `sync-prune-next` skill already applied the stricter hold to marketlake's queue because it fails safe. marketlake's build-only check was the fix for [l3a0/marketlake PR #713](https://github.com/l3a0/marketlake/pull/713), adding a hold the sync skill had promised, rather than a decision that a decompose loop frees a branch. The price is that a reviewed, green pull request whose card carries `working:decompose` waits under "Waiting on my review" until the loop ends. Porting marketlake's rule would need a flag in `board.json`, because a change to the page alone would move a current caller's card. |
| A warning on a pull request whose closing link GitHub did not register | l3a0/marketlake's page drew one. Neither generator can write the entry that draws it, because each writes `linked` false only beside `partOf`, which [#47](https://github.com/l3a0/repo-template/issues/47) measured over 73 mixes of closing link and body. The `pr_items` docstring in `scripts/build_board.py` carries the reason, and the page carries no such warning. |
| TODO | TODO |
