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

The next group comes from Steve McConnell's *Code Complete* (2nd ed.,
Microsoft Press, 2004), cited by printed page, so CC p. 470 is page 470. It
covers how the code holds the design's rules. Its case for writing each rule
as a check is measured: no single way of finding defects reaches more than
about 75% at its typical rate, and two methods combined find almost twice
what one finds (CC p. 470, p. 471).

The last group comes from Mark Douglas's book *Trading in the Zone* (Prentice
Hall Press, 2000), cited by Kindle location, so TZ L2038 is location 2038. It
covers judging a process whose single outcomes are partly chance, such as a
trading strategy or an experiment. Douglas writes for
traders who decide each trade themselves, and these rules carry his method
for judging an edge over a sample, not his psychology.

These are checks on a design, and a review applies all of them. The mechanism
a rule names is built when the path it guards first runs, under the ranking
rule in [CLAUDE.md](../CLAUDE.md), and no sooner. That rule's three
exceptions decide what is built from the first run whatever the count.

1. Whatever keeps data the project cannot recapture from loss or corruption,
   such as checksums, append-only storage and backups.
2. Alarms, such as the checks a running system makes on its own guarantees, a
   clock-offset monitor and every queue's lag alarm.
3. Guards whose price is paid by building them late, such as the id that drops
   a repeated write, the lease number on every write that needs one, and the
   check that refuses an action whose worst loss it cannot compute.

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
   id carried from end to end can drop the duplicate (DDIA L16438). The
   receiver drops it with a uniqueness constraint applied in the same step as
   the write, since a check that no such row exists yet has nothing to lock
   and two writers can each pass it (DDIA L7635). A timed-out write is
   recorded as unknown rather than failed. A read of the receiver that finds
   the write settles it, and a read that finds nothing does not, because a
   request can still land after its sender has gone. Where the write is
   irreversible or moves money, its record reaches stable storage, through
   `fsync` or the store's acknowledged write, before the write is sent, and a
   write in doubt is resent only to a receiver shown to reject a repeated id.
2. **A lease or a lock is enforced by a fencing token where the protected
   resource checks one, and where it cannot, the design says the write is
   unfenced and guards the window that is left.** A process can pause past
   the end of its lease, in a garbage-collection pause, a suspended virtual
   machine, swapping or a blocking write, then wake and act as if it still
   held it (DDIA L9084, L9094, L9102, L9110). A fencing token is a number each
   grant of the lease carries, higher than every earlier grant, and the
   resource itself refuses a write whose number is lower than one it has
   already accepted, since a client checking its own lease is not enough
   (DDIA L9274, L9286). For a resource that cannot check a token, the book
   suggests carrying it in what the resource stores, such as a file name (DDIA
   L9292). That lets a late write be found afterwards and stops none, and the
   book offers nothing more. So where the resource does not check, the design
   checks the lease just before each write, names the window between that
   check and the write, never resends a write whose outcome is in doubt, and
   halts when it finds a write that names an older lease after a takeover. No
   id or lease number comes from a counter that a failover or a restore from
   backup can wind back. The book's case is a promoted replica whose lagging
   counter reused keys another system already held (DDIA L4868). A lock held
   for one process is one released only when its holder exits, such as
   `flock`, never a POSIX record lock that closing any descriptor for the file
   releases. A test pauses one holder between its check and its write, lets a
   second take over, resumes the first, and asserts that the resource holds
   exactly one result, or, where the resource checks tokens, that the stale
   write is refused.
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

### The code holds its own rules, and every check runs in production

1. **A rule whose breach cannot be undone is held by the code's structure, a
   type or a test, never by a comment or a convention alone.** McConnell
   separates programming in a language, limited to what it offers, from
   programming into one, deciding what the program needs and making the
   language supply it (CC p. 68, p. 69). Where the language enforces no
   boundary between modules, a check in CI enforces the boundaries the design
   draws, and a test that adds a forbidden import shows it fails. An import
   check guards the wiring and not the call, since code handed an object can
   call it without importing anything. McConnell's way to make one step's
   dependence on another visible is to pass the earlier step's output to the
   later one (CC p. 349). Most languages let any module build any type, so the
   argument shows a reader the order and a check holds it. The later step
   reads the record the argument names, and refuses one that is missing, not
   yet durable or already used.
2. **A check that guards an irreversible action or stored data runs the same
   way in tests and in production.** McConnell's default compiles assertions
   out of production builds (CC p. 190), though he keeps the code that checks
   for important errors and the code that lets a program fail safely, which
   the Mars Pathfinder's engineers left in and used to fix it after landing
   (CC p. 209, p. 210). Python drops every `assert`, and every
   `if __debug__:` block, when it runs with `-O`. A guard written that way is
   tested and then absent where it matters, so it raises explicitly, a lint
   rule refuses `assert` outside the tests, and CI runs the suite once under
   `python -O`.
3. **The design chooses once between correctness and robustness, and where a
   wrong result costs more than no result, bad input fails rather than turning
   neutral.** McConnell lists ways to handle a bad value, among them a neutral
   value, the closest legal value, and a logged warning followed by carrying
   on, and calls the choice an architectural decision (CC p. 194, p. 195,
   p. 197). Correctness means returning no result rather than a wrong one,
   which safety-critical software favors (CC p. 197). Where the design picks
   correctness, no value such as −1 or zero stands for "missing" (CC p. 257),
   a branch over a closed set ends in a failure rather than a default case
   (CC p. 363), as the faults rule's stop on an impossible case requires, a
   function's result starts as the failing one (CC p. 224), and a number is
   compared with zero explicitly (CC p. 441). Bad input stops the action it
   feeds and never an action that reduces risk, such as a cancel, which keeps
   acting on everything else it covers. Data stored as received is not
   refused at the door. The check runs where the data is parsed, under the
   recorded-data rules above.
4. **Data from outside becomes the project's own types at the boundary, and a
   stand-in for an outside system passes the same contract tests as the real
   one.** McConnell's barricade checks and converts data at the boundary, so
   the code inside can treat a bad value as a bug rather than as input
   (CC p. 203, p. 204). The adapter records what it received unchanged before
   converting it, and that raw record is the only thing past the boundary in
   the vendor's form. Each adapter checks the result of every call it makes
   (CC p. 197), and raises the project's own exceptions at the level of the
   interface it presents (CC p. 199, p. 200), keeping rejected, provably not
   sent and outcome unknown apart. Its exceptions and logs carry no
   credential, since attackers read error messages (CC p. 196). A stand-in,
   such as a fake or a simulator, keeps every promise of the thing it
   replaces, which is McConnell's statement of the Liskov principle
   (CC p. 145). So one contract suite runs against the stand-in and against
   the real system or its recorded responses, and covers the cases the code's
   correctness depends on rather than only the shapes of responses. A
   recording strips credentials and account identifiers before it is written,
   and a test fails on a committed recording that matches a credential
   pattern.
5. **A result whose error costs money or cannot be undone is checked in tests
   by a second, plain implementation, and a change made for speed carries a
   measurement before and after.** McConnell's example is an insurer that
   checked a complicated rate system with a separate tool computing each rate
   on its own, because accuracy was essential (CC p. 722). The second
   implementation lives under the tests, which no module outside them
   imports, so it is a reference rather than a second code path, and it
   shares no helper with the code it checks. McConnell's tuning procedure
   measures each change alone and reverts one that does not help, since more
   than half of attempted tunings gain little or slow the code (CC p. 606).

### A process with chance outcomes is judged over a sample set in advance

1. **The sample, the measures, the result that counts as success and the
   result that ends the process are written down before the first outcome,
   and no conclusion rests on one outcome or one streak.** Douglas holds that
   wins and losses fall at random within any set of conditions that defines
   an edge (TZ L2038). He judges an edge over a sample large enough to test
   it fairly and small enough that a fading edge shows before it has cost
   too much (TZ L3198). His own sample of at least 20 trades comes from his
   experience rather than data, so the project sets each sample from the
   smallest effect worth detecting and the spread of the outcomes it
   expects, as the considered-and-rejected register records. The plan also
   names the measures after costs, the smallest effect the sample can
   detect, and the range of losses to expect, set without any data held
   back for the final test. Success is judged across every sample opened
   for the same process, under the project's control for many tries. A
   review checks that the plan existed before the first outcome.
2. **The parts that decide the outcomes run unchanged through the sample,
   every case is accounted for, and a change to those parts starts a new
   sample.** Douglas trades a system exactly as designed for every
   occurrence of its edge in the sample (TZ L3232), because taking every
   case is what lets the sample show the odds (TZ L1860). Here each outcome
   counted in a sample carries one version of the parts that decide it. A
   replay of the sample's cases confirms that a change elsewhere left the
   decisions the same, which keeps the sample open, and every sample opened
   is counted, including one ended early, so a sample cannot be restarted
   until one happens to look good. Every case the process should have acted
   on maps to exactly one recorded outcome, such as acted on or skipped for
   a reason from a closed list, and a skip never answers a missing or
   invalid input. A test matches them one to one by id, the running system
   counts the same match and alarms on a mismatch, and fault tests drop and
   duplicate an outcome to see the alarm fire. Overrides cluster on cases
   that look bad at the time, so a case a person overrode is scored as the
   process's own decision would have played out and kept in the sample,
   with the override's effect reported apart (TZ L559). A halt of the whole
   system pauses the sample, and the record says whether stopping one
   process ended it. Either can happen at any time.
3. **Each action that can lose money or something the project cannot
   recover has its worst loss fixed first, and a check refuses it rather
   than resizing it.** Douglas's exit for a losing trade says in advance how
   much must be risked to learn whether the trade works (TZ L3095), and a
   trader whose total risk is too large cuts the size and leaves each
   trade's risk where the research set it (TZ L3220). Here the worst loss
   comes from a stated stress case with every part of the action moving
   against it, counting the actions already sent and still unanswered at
   their worst, or from the planned exit where that is a fixed level and
   larger. The project adds the reason: a jump or a halt can carry the
   result past any exit. A check refuses an action that adds risk when that
   loss cannot be computed, counts the part of an action that crosses zero
   as adding, never refuses one that only reduces risk, and never resizes.
   The step that sizes actions makes them smaller, and makes actions sized
   together smaller together.
4. **Nothing raises the stake after a run of good results, except a rule
   written down before the run.** Douglas finds a trader most likely to break
   rules and oversize while winning, and a larger position magnifies the
   next move against it (TZ L919, L943). A raise of a limit or a stake cites
   the evidence the plan named before the run, never a streak.

The price of these rules is a checksum and a format version on every stored
record, an id on every write to another system, a lease number on every
write that needs one, histograms in place of averages, a test harness that can inject
faults, an import check in CI, a run of the suite under `python -O`, a type
for each kind of outside value, a contract suite for each stand-in, a second
implementation in the tests of each result whose error costs money, a
measurement for each tuning change, a sample plan written before any
process with chance outcomes is judged, a recorded outcome for every case
with a running match that alarms, and a worst loss computed before each
action that can lose money. What they buy is stored data that survives the bugs in the code
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

Steve McConnell's *Rapid Development* (Microsoft Press, 1996) supplies the
rules for estimating, cutting and tracking the work, cited by printed page,
so RD p. 199 is page 199. The book writes from studies of human teams in the
1980s and 1990s, so its rules are adopted for their method rather than their
numbers, and how well they fit agent loops is untested. Five rules follow.

1. **A slice builds its most important behavior first.** McConnell's staged
   delivery ends every stage with a product that meets its size, performance
   and quality targets as well as its function, and delivers capabilities
   from most to least important (RD p. 553). A working product is a more
   accurate status report than any paper report (RD p. 551). The parent issue
   names the check that shows the slice usable, and that check runs before
   the parent closes.
2. **An estimate is a range drawn from loops of the same kind, posted under
   its own heading, and the next estimate of that kind carries the slip.**
   McConnell's multipliers, adapted from Boehm and others' COCOMO 2.0 of
   1995, put an estimate of effort made at the first concept anywhere from a
   quarter to four times the final figure (RD p. 169), and estimating from
   memory of similar projects goes with overruns (RD p. 178, citing Lederer
   and Prasad 1992). So a build issue carries a comment opening with
   `## Estimate` that gives a range and names the earlier loops of the same
   kind it was drawn from, whose measured costs are the `## Cost` comments
   the owner's global instructions require. Where none of that kind exists,
   the first estimate is a labelled guess inside the widest of McConnell's
   ranges. A project behind schedule hardly ever makes up the lost time
   (RD p. 199, citing van Genuchten 1991), and McConnell raises what remains
   by the share of the slip so far (RD p. 381). So when a loop's cost lands
   above its range, the next estimate of that kind raises its range by the
   same ratio.
3. **A loop that runs past its estimate drops behavior from a list written in
   advance, and never a check.** McConnell's timebox drops features rather
   than quality, and he advises against boxing planning, requirements and
   design, whose mistakes cost the most downstream (RD p. 581). So a build
   issue lists, in order, the behaviors a slip may drop. That list never
   holds anything the ranking rule's three exceptions name, an alarm or the
   drill that shows it works, a rollback, a review, a test, or anything that
   guards what the premise says cannot be recovered. A dropped behavior moves
   to an issue of its own, and its acceptance tests stay in the suite as
   strict expected failures that name that issue.
4. **Done is a state a check shows, never a percentage.** McConnell's test of
   a finished piece is whether it could be locked in a vault and shipped as
   it stands, so a piece "99 percent done" is not done (RD p. 381). A report
   of done links the merged pull request that closed the issue, its review,
   and the checks that ran the changed code. A check that never ran the
   changed code shows nothing.
5. **A spike answers one stated question and never becomes production code,
   and a risk to something that cannot be undone ranks above every risk that
   can.** McConnell treats each throwaway prototype as an experiment with a
   hypothesis, and stops it once the hypothesis is settled (RD p. 572), so a
   spike lives outside the product's package, nothing in the product imports
   it, and it takes no irreversible action. He ranks risks to a schedule by
   probability times size, then moves a larger loss above its place in that
   order (RD p. 95, p. 96). A slice keeps the risks to its delivery on its
   parent issue under a `## Risks` heading. The losses the premise names rank
   first whatever their probability, and the list ranks what to watch, never
   what to build next. The status round of the `/l3a0:sync-prune-next` skill
   reviews it whenever it names a card from the slice, and posts a dated
   comment opening with `## Risks review`.

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
| *Trading in the Zone*'s sample of at least 20 trades as the unit that judges a process | Douglas found it from his own trading and gives no data for it (TZ L3198). A sample that small can detect only a large effect, so each project sets its sample from the smallest effect worth detecting and the spread of the outcomes it expects, under [A process with chance outcomes is judged over a sample set in advance](#a-process-with-chance-outcomes-is-judged-over-a-sample-set-in-advance) |
| A copy of the build board's skills in each repository | Four repositories held their own copies of the build board's skills, and each copy held something the others lacked, which [l3a0/claude-plugins#28](https://github.com/l3a0/claude-plugins/issues/28) inventoried. The skills moved into the `l3a0` Claude Code plugin on 2026-10-29, and a seeded repository installs the plugin rather than copying them. [#24](https://github.com/l3a0/repo-template/issues/24) had kept them per repository because a repository pins the generator to one commit while a plugin skill moves with each release. That is the price, and a second comes with it: every session runs what the plugin's `main` holds, hooks included, with no pull request in this repository to show a change. The plugin skill's `## Generator compatibility` table names the generator commits its formats were checked against. `tests/test_build_board_generator.py` reads the skill at a pinned plugin commit, so renaming a marker or a label the generator reads fails here until a matching plugin release exists. Other format changes rest on the plugin's release rule |
| Holding a reviewed, green branch back only while a build session holds its card | l3a0/marketlake's own page held such a branch back from the owner's queue only for `working:build`. The shared page holds it back for any `working:` label, and [#47](https://github.com/l3a0/repo-template/issues/47) kept that rule when it ported marketlake's review rule. The plugin's `sync-prune-next` skill already applied the stricter hold to marketlake's queue because it fails safe. marketlake's build-only check was the fix for [l3a0/marketlake PR #713](https://github.com/l3a0/marketlake/pull/713), adding a hold the sync skill had promised, rather than a decision that a decompose loop frees a branch. The price is that a reviewed, green pull request whose card carries `working:decompose` waits under "Waiting on my review" until the loop ends. Porting marketlake's rule would need a flag in `board.json`, because a change to the page alone would move a current caller's card. |
| A warning on a pull request whose closing link GitHub did not register | l3a0/marketlake's page drew one. Neither generator can write the entry that draws it, because each writes `linked` false only beside `partOf`, which [#47](https://github.com/l3a0/repo-template/issues/47) measured over 73 mixes of closing link and body. The `pr_items` docstring in `scripts/build_board.py` carries the reason, and the page carries no such warning. |
| Compiling assertions out of the production build | *Code Complete*'s default for assertions (CC p. 190), though it keeps the code that checks for important errors (CC p. 209). A guard that is tested and then compiled out is absent where it matters, so a guard raises explicitly and runs in every environment. [The code holds its own rules](#the-code-holds-its-own-rules-and-every-check-runs-in-production) carries the reasoning |
| A neutral value, the closest legal value, or logging and carrying on, as the answer to bad input where a wrong result costs more than none | *Code Complete* offers each one (CC p. 194, p. 195). Each turns bad input into a value the project acts on. A project whose wrong result is cheap may choose robustness instead, and says so here |
| TODO | TODO |
