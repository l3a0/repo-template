# Design — PROJECT_NAME

<!-- TEMPLATE: this doc carries the reasoning. The tracker carries unbuilt
     scope, and this doc links to an issue rather than restating it. Write the
     premise first and leave the rest to grow as decisions get made. -->

## Contents

- [Premise](#premise)
- [Design for 10x, plan the rewrite before 100x, build at 1x](#design-for-10x-plan-the-rewrite-before-100x-build-at-1x)
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

## Design for 10x, plan the rewrite before 100x, build at 1x

<!-- TEMPLATE: say what this project's first load is, in the load
     parameters the design principles below ask a design to name, what 10
     times it would be, what carries the design to 10x without a rewrite,
     how load is measured, the alarm that says it nears the 1x limit and the
     one that says it reached the rewrite-planning level, which 10x parts
     are designed now and built later, and, for growth beyond 10x, the load
     at which planning a rewrite starts, what it would replace and what must
     carry over unchanged, such as recorded data, its formats and its
     partition layout. CLAUDE.md carries the rule. -->

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

The group on the code comes from Steve McConnell's *Code Complete* (2nd ed.,
Microsoft Press, 2004), cited by printed page, so CC p. 470 is page 470. It
covers how the code holds the design's rules. Its case for writing each rule
as a check is measured: no single way of finding defects reaches more than
about 75% at its typical rate, and two methods combined find almost twice
what one finds (CC p. 470, p. 471).

The group on modules and releases comes from Sam Newman's *Building
Microservices* (O'Reilly Media, 2015), cited by Kindle location, so BM L4252
is location 4252 and BM L\~932 is good to about one screen. It covers where
modules are cut, how one build reaches every environment, and how each
dependency fails. The book argues for splitting a system into services, and
its own author's team found that splitting too soon was costly, so the rules
split a component further only when evidence calls for it
(BM L777, BM L796).

Viktor Farcic's *The DevOps 2.0 Toolkit* (2016), cited by printed page, so DT
p. 247 is page 247, supplies the group on releases, machines and healing. It
covers what happens once code leaves the repository: how a release is checked
on the machine that runs it, how those machines are built, and what an
automatic restart may do. The book's pipeline deploys every passing commit to
production with no person in it (DT p. 20). A project whose owner deploys by
hand takes the book's continuous delivery instead, where every passing build
could be deployed and a person decides when (DT p. 19).

The last group comes from Mark Douglas's book *Trading in the Zone* (Prentice
Hall Press, 2000), cited by Kindle location, so TZ L2038 is location 2038. It
covers judging a process whose single outcomes are partly chance, such as a
trading strategy or an experiment. Douglas writes for
traders who decide each trade themselves, and these rules carry his method
for judging an edge over a sample, not his psychology, with this project's
additions, such as power, replay scoring and pauses.

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
   check that refuses an action that adds to a position that can lose money when its worst loss cannot be computed.

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
   write in doubt is resent only to a receiver shown to reject a repeated id and
   only within the time it is shown to remember one, or,
   for a cancel by the receiver's own id, one a test against its sandbox shows
   applies a repeated cancel at most once.
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
   check and the write, never resends a write whose outcome is in doubt except as rule 1 allows, and
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
   common, and its 10x holds only along them.** A load parameter is one of
   the few numbers that describe load, such as requests per second or records
   per day. The book asks two questions of each one: how performance changes
   when it rises and resources stay fixed, and how far resources must grow to
   hold performance steady (DDIA L482, L484). A scalable architecture rests on
   assumptions about which operations are common, and a wrong assumption
   wastes the scaling work or makes it harmful (DDIA L627). The book also
   finds that an architecture rarely copes with ten times its load, so a
   fast-growing service rethinks it at each tenfold rise (DDIA L598). That
   finding matches the directive in [CLAUDE.md](../CLAUDE.md) to
   design for 10 times the first load and plan the rewrite before 100
   times. A 10x design holds only along the parameters it names, so
   [Design for 10x, plan the rewrite before 100x, build at 1x](#design-for-10x-plan-the-rewrite-before-100x-build-at-1x) names them,
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
   the split can use, and each partition carries overhead, and changing the
   count moves stored data, so the count is sized for 100 times the first
   load, the ceiling a rewrite must come before, and no higher, since the partition layout is part of
   what must survive a rewrite (DDIA L6411, L6443).
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

### Modules are cut by capability, and every release and dependency is bounded

1. **A module is cut along a capability of the domain, and no other module
   reads its internal state except through its interface.** Newman draws
   boundaries along bounded contexts, the parts of a domain that keep their
   internal models to themselves (BM L740), and finds that services sharing
   one database lose both cohesion and loose coupling (BM L\~932). A
   module's interface may be the files it publishes in a versioned format. A
   backup, a scheduled read-back or a replay that copies files whole is not a
   read of a module's records, and any parse of a copied file goes through the
   owning module's reader. A module cut along a technical layer, such as one that only
   wraps storage, names its reason, such as a performance goal, because the
   book makes the technical seam the second driver (BM L866).
2. **A component splits further than the design already does only with a
   named reason and the history of changes across its boundary.** Newman's
   team split a product into services early, merged them back, and split
   again a year later along boundaries that held (BM L777, BM L796). The
   reason names the load, the isolation or the credential that calls for the
   split. Clones of a component and a split by key follow the scale rules and
   need no such reason.
3. **One artifact is built once and runs in every environment, and
   configuration may differ by environment only in a committed list of
   keys.** Newman builds an artifact once so that what is deployed is what
   was tested (BM L\~2160), and keeps configuration that changes between
   environments to an absolute minimum (BM L2393). The list holds adapter
   selection and parameters, references to where each credential is read
   from and never its value. A limit that configuration must never raise sits outside the
   configuration. A test fails
   on any other difference, and the deploy and the running process each
   record the artifact's hash so a mismatch halts startup or a running process, and a rollback re-points the deploy's record to the kept hash. Where only one
   instance may act at a time, a new release acts only after the old one has
   stopped taking new work and exited, as the host shows. Blue/green runs two versions side by side (BM L3044), and where replay must attribute each decision to one version, two versions acting by turns would apply different rules to one record and replay could not say which decided what. Throughout the handover something reads the actions that reduce risk, the old release until the new one's own checks have passed, and the new one from the start of its wait, each under the one-actor guard and re-reading the record so a cancel already recorded is recognised, and is sent again only as rule 1 of [Writes happen once, from one writer at a time](#writes-happen-once-from-one-writer-at-a-time) allows, and a release serves them once the checks the action itself needs have passed, such as its own artifact and a record it can append to, while a failure of any other check stops new work only. Every takeover, a rollback's included, rebuilds its state after it
   takes over, and an alarm fires when no release has been acting past a
   written bound, watched from outside every release and started by a risk-reducing action that waits.
4. **Every outside call has a timeout, every dependency that can stall
   others has its own limit and a breaker, each limit keeps a slice for actions that reduce risk, and a breaker never stops an
   action that reduces risk.** Newman puts a timeout on every outside call,
   and names bulkheads and circuit breakers as tools to use where they fit
   (BM L4252, BM L4292, BM L4995). Where a wrong result costs more than none,
   an open breaker stops new irreversible actions rather than serving a stale
   value, and an action that reduces risk passes through it with every call it needs. A cancel with no
   answer is looked up rather than sent again, unless it is a cancel by the receiver's own id that rule 1 of [Writes happen once, from one writer at a time](#writes-happen-once-from-one-writer-at-a-time) allows to be resent, and one still unsettled past a written time pages a person. Where a breaker raises a halt, the halt releases itself at most a written number of times
   before it waits for a person. The call that tests recovery has no side effect, a breaker
   closing releases no halt before the state it guards is reconciled, and
   recording data the project cannot recapture never waits on a breaker. His
   cautionary tale is a queue with no retry limit, where one request that
   crashed its worker went back on the queue and crashed the next (BM L1286).
   So a retried job that builds something regenerable has a maximum, past
   which it is set aside and alerts, and a write that is not safe to repeat,
   such as a new order, that got no answer is looked up, and resent only to a
   receiver shown to reject a repeated id, and only within the time it is shown
   to remember one.
5. **One correlation id runs from where a request starts through everything
   it leads to, and a synthetic transaction watches the running system
   without reaching anything irreversible.** Newman finds correlation ids
   very hard to add later (BM L3354). Each write to an outside system still
   gets an id of its own that contains the correlation id, so a request that
   leads to several writes gives each a unique one. He found a scheduled fake
   event, with an alert when its result did not appear, a far better sign of
   trouble than lower-level metrics (BM L3250, BM L3300). Every synthetic
   transaction carries a marker that passes to every record built from it,
   the real adapters refuse anything carrying it, and the transaction never
   enters recorded data or an input the real system reads.

### Releases are checked where they run, and nothing heals by hiding a fault

1. **The checks that clear a release to act are the code its tests ran, run
   where the release runs with only the target changed, and the release acts
   only after they pass.** Farcic runs the same integration tests against a
   new release twice, with only the address changed: once at its own address
   before it is made publicly available, and once through the entry point
   users reach after the switch (DT p. 173, p. 247, p. 248). So the checks that clear a release, whether at startup or from the pipeline,
   are the same functions the tests run, rather than a
   second list that would drift from them. A failure halts new irreversible
   actions, or rolls back where the project allows an automatic rollback, and
   tells a person, and the actions that reduce risk, such as a cancel or a
   stop, stay served wherever their own record can still be written before
   they are sent. A release that fails its own integrity check cannot be
   trusted to serve them, so it serves nothing and the page names the person's
   fallback. No such check takes an action that cannot be undone, such as an irreversible
   send or a change to a customer's data, in any environment, so its code is the same
   everywhere. A check that starts something waits on a readiness check
   with a timeout, never on a fixed sleep, and a wait that expires fails the check. The book calls its own fixed pause
   something to use rarely (DT p. 200), and this doc makes it never.
2. **Every machine is built from committed code, a check of that code against
   what it built finds no difference, and a change made by hand is committed
   or undone.** Farcic runs every step from a delivery server and finds no
   need to log in to a server and work on it by hand (DT p. 88), and a second
   run of his playbook finds almost nothing left to do (DT p. 190). The code
   names where each credential is read from and holds none, its state stays
   out of the repository, every environment applies the same committed code,
   differing only in the committed list of keys, and a setting only the owner may change stays
   outside it. Applying the code to production is a deploy, timed so it cannot
   cut an action that reduces risk, such as a cancel. An infrastructure change rolls back by a new commit on the default branch,
   applied like any other change, that restores the code before it and
   detaches, never destroys, any protected store the change created. It rolls
   forward by bringing that store back under the code by its recorded id. The scheduled
   check runs in a mode that only reports, under a role that cannot write and
   reads no stored data, and a difference is drift, which alerts, as does a
   check that has not reported past a written bound. Neither the code nor any
   role that applies it can delete, overwrite, append to, expire or recreate data the project cannot recapture, a stop that only a person may release, a lease, or the channel
   that carries actions that reduce risk, write a setting only the owner may
   change, read, overwrite or delete a credential, grant read of one to any principal but the one
   the design names, or change who can act as that principal. That guard sits where the role it
   binds cannot edit it, such as an account-level policy, and a check on the
   plan's machine-readable output refuses such a change, including one to a
   lifecycle rule or a policy attached to the store, whether or not the store's block is still in the code. A store of a stop that is created again starts stopped
   until a person releases it, and a store of records the project cannot
   recapture that is found empty, or behind its own copies, reads as missing,
   never as empty. A protected store found missing stops new irreversible actions, until a person
   releases the stop, where the project has such a stop, and pages a person, while recording of data the
   project cannot recapture keeps running. A store of such records found
   missing, empty or behind takes no entry until it is restored, and where that
   leaves an action that reduces risk unserved, the page names the person's
   fallback. A comparison with a copy that cannot finish, or first-start evidence
   that is absent or unreadable, stops new irreversible actions until a person releases the stop and alerts,
   and never reads as current, and an entry written meanwhile stays through any
   restore, as the rules on recorded data require. A store of such records starts empty only once, on a
   record that says this is the first start. Such data is restored from its copies and never rebuilt
   this way. Every interface that can control a host or a container takes only
   authenticated calls from the identities the design names for it. The book's
   own setup listens for remote requests from any address and says a real one
   must be much more restrictive (DT p. 92). Deployment code swallows no error
   either. The book's function that reads which release is live returns an
   empty value on any failure (DT p. 246), so an outage there reads as no
   release live, and the next deploy can land on the release that is serving.
   A deployment state that cannot be read stops the deploy.
3. **No run of a branch other than the default holds a production credential,
   and a deploy by hand sits behind an approval no agent session can give.**
   No workflow run whose code comes from a branch other than the default holds
   a credential that can deploy to, act on or read production. Where the owner deploys
   by hand, a deploy credential sits behind an environment per target account
   that admits only the default branch, with an identity no agent session holds as its required reviewer and no
   administrator bypass, and no login an agent session holds, on
   GitHub or in the cloud, can change that environment, bypass the default
   branch's ruleset or assume a role that deploys or applies the code. A deploy's cloud role trusted through OIDC trusts only that environment, and a job that uses it
   runs only on a push or a manual dispatch on the default branch, never on
   `pull_request_target` or `workflow_run`, and runs nothing but the default
   branch's head. A deploy that holds no such credential, such as the build
   board's Pages, is outside this. A deploy accepts only an artifact a run on the default branch recorded when it
   built the commit then at that branch's head, in a store no other run and no login an agent
   session holds can write, where that run was started by a
   push or a manual dispatch, never by `pull_request_target` or `workflow_run`.
   A plan's output and a deploy's log stay out of any public log or artifact,
   and the code writes no secret into its state. A scheduled read-only check's role trusts one workflow and one event on the
   default branch. These credential rules are this doc's, not the book's.
4. **An automatic restart, reschedule or scale step is capped, recorded and
   reported, a stop made on purpose is never a failure to heal, and a missing
   reading leads to no step at all.** Farcic warns that recovery from a failed
   process often needs a person to find the cause, so a notification goes with
   it (DT p. 302), and he finds a bare redeploy incomplete for the same reason
   (DT p. 263). Docker's `always` policy restarts a container without limit
   (DT p. 345). A restart starts the artifact already deployed and cannot
   change which one that is, and a record of what is deployed that cannot be
   read takes no restart and alerts. Each component restarts at most a written
   number of times in a written window before a person is paged, held by one implementation, such as the host supervisor's own start limit,
   which does not bind the two kinds of component below, and the cap
   is stated so a test at it has one answer: with a cap of N, the Nth restart
   runs and the crash after it pages. A window can let a slow crash loop pass,
   so a crash loop slower than the window must still reach a person.
   Each restart, reschedule and scale step is recorded with its component, exit or
   reason and count, and a component with no written kind takes the stricter
   outcome below. Where a
   component can move to another machine on its own, the count survives the
   move without the restarter gaining write access where irreplaceable records
   live. Two kinds of component keep restarting past the cap, with a delay that grows
   to a written maximum and a page, and for one that serves actions that reduce risk the maximum, plus the time
   from a start to serving those actions, sits below the written bound on them: one whose stop loses data the
   project cannot recapture, and one that serves actions that reduce risk,
   such as a cancel, which comes up stopped for everything else, as it does below the cap when its switch or count cannot be read or is absent,
   or its switch is off. Neither an
   unreadable record nor an unreadable or flipped switch stops their restarts.
   Where the project has a halt that stops irreversible actions, a component
   whose output the system acts on, or whose check it relies on, raises it at its cap rather than only paging, and a crash of any
   component that takes no restart, for any reason, counts as reaching its cap.
   There, a crash on one record that cannot be recaptured or repeated halts on
   the first crash, names the record and takes no restart into it. The book's own average over the last hour
   comes back null when no entry falls inside it (DT p. 383), and a null,
   stale or failed reading takes no step and alerts. A person can switch these steps off without a deploy, through an authenticated
   call, the code declares the switch and never its position, a switch left off
   alerts when the component next starts, and one continuing cause raises one page
   at a written interval, except the
   restarts of the two kinds of component above, a flip is recorded, and an
   unreadable switch takes no step and alerts. A scaling step has a written floor and ceiling on
   instances. An instance that scaling removes stops taking work, where the
   book's scale-down simply removes the instances it no longer wants (DT p.
   286), and a write whose outcome it cannot learn follows the rule on writes with
   an unknown outcome. A component stopped or halted on purpose reports that state,
   so no health check reads it as failed and restarts it to clear it, and it
   comes up halted after a restart. Neither a cap nor a scaling step leaves an action that reduces risk, such as
   a cancel, with nothing to serve it, and where one would, or a restart cannot
   serve it after all, the page names the person's fallback.
5. **Where a component runs on more than one machine, or on a machine that
   keeps no state, its logs leave the machine as structured records, into one
   place that can be searched, and no log write waits on that place.** Farcic
   finds a service's logs spread over several files and several servers, and
   gathers them into one store that can be searched (DT p. 349, p. 350, p. 362). A
   line goes through a bounded buffer that drops and counts what it cannot
   write, so a stalled pipeline never stalls the work, and the buffer alarms
   before it drops. A component's log credential can only write, and only the identities the
   design names can read that store. A record that cannot
   be recaptured, such as an audit trail, keeps its own store, which no log
   pipeline, retention rule or cleanup reaches.

Each run-time failure this group handles is a fault the faults rule above
injects, with its test, such as a component that must come up halted, a null
reading behind a step that heals, and a store found missing. A failure at
deploy time, such as an unreadable deployment state, drift or an
infrastructure change rolled back and forward, has a CI test
and a drill, and so do the restart cap, every alarm this group adds, and the
switch that stops restarts and scaling, flipped with the component left running, and a crash after it takes no
restart, except on the two kinds of component the rule names.

### A process with chance outcomes is judged over a sample set in advance

1. **The sample, the measures, the result that counts as success and the
   result that ends the process are written down before the sample's first
   outcome, and no conclusion rests on one outcome or one streak.** Douglas
   holds that wins and losses fall at random within any set of conditions that
   defines an edge (TZ L2038). He judges an edge over a sample large enough to
   test it fairly and small enough that a fading edge shows before it has cost
   too much (TZ L3198). His own sample of at least 20 trades comes from his
   experience rather than data, so the project sets each sample from the
   smallest effect worth detecting and the spread of the outcomes it expects,
   as the considered-and-rejected register records. The plan also names, for a
   process that keeps running, the sample's longest span in time and when the
   result that ends it is checked, and the measures after costs, which count
   every position the sample opened, with one still open at the end marked at
   recorded prices. It names the smallest effect the sample can detect with
   the level and power behind it, and, where the process can lose money, the
   range of losses to expect, set without any data held back for the final
   test. Where a person can override the process, it also names the most
   overrides the sample takes, the longest total time pauses a person starts
   or ends may take, and the largest share of cases it may score by replay
   rather than by its own results. A sample ends at the first of its size and
   its longest span, pauses included, and one with too few outcomes to detect
   the stated effect or past its most overrides ends without a verdict and
   still counts. Success is judged across every sample the project opened
   toward a decision, a batch wider than one search, under a declared
   false-discovery-rate control such as [the research pins
   module](https://github.com/l3a0/repo-template/blob/main/docs/optional-policies.md#module-1-research-pins).
   A project that judges chance outcomes with no such control declares one
   before calling any result registered, meaning committed in writing before
   the number was seen. A review checks that the plan existed before the
   sample's first outcome.
2. **The parts that decide the outcomes run unchanged through the sample,
   every case is accounted for, and a change to those parts closes the sample
   without a verdict.** Douglas trades a system exactly as designed for every
   occurrence of its edge in the sample (TZ L3232), because taking every case
   is what lets the sample show the odds (TZ L1860). Here each outcome counted
   in a sample carries one version of the parts that decide it. A replay of
   the sample's cases that shows no difference after a change elsewhere keeps
   the sample open, though it speaks only for the cases replayed, and a
   difference counts as a change to those parts. Every sample opened is
   counted, including one ended early, so a sample cannot be restarted until
   one happens to look good. Every case the process should have acted on ends
   in one recorded outcome per action, or one for the case where no action
   followed, such as a skip for a reason from a closed list, every action
   traces back to its cause, such as a case, a recorded human act, a halt,
   where the project's own rule allows it an event the outside system itself
   originates, shown by its own record, or an outside action a person
   confirms, never the match itself, and a skip never answers a missing, stale
   or invalid input. A test matches them one to one by id. Where a running
   system acts on the process's decisions, it checks the same match, and the
   result that ends the process, within a stated time, treats a case inside
   that time as in flight, shows how many cases it checked, alarms on a
   mismatch and when it has not run within that time, and on either halts
   where the actions can lose money, and each such halt says why it halted and
   how it is released. Fault tests drop and duplicate an outcome, feed a skip
   a bad input, inject an action with no cause and stop the match, to see the
   alarm fire each time and, where the actions can lose money, the halt.
   Douglas finds that unplanned action cannot show what works (TZ L559).
   Overrides can also be expected to cluster on cases that look bad at the
   time, so this project scores a case a person overrode as the process's own
   decision would have played out and keeps it in the sample, with the
   override's effect reported apart. A person stopping the process counts as
   an override of every case while it is stopped, though a stop, a cancel or a
   cut in size never counts toward the most overrides, and no sample rule
   delays or refuses one. The only price of a long stop is that it can use up
   the share scored by replay and end the sample without a verdict. A raise of
   the stake or of a limit closes the sample without a verdict unless a rule
   written before the sample moved it, a raise that comes from a lower
   estimate of the risk closes it even then, and a cut, a tightened limit or
   its return to the value it held when the sample opened keeps it open, with
   results judged per unit of risk and a case refused because a person
   tightened a limit scored by replay. A fix to a safety control or a rollback
   is never held back to keep a sample whole. Only a halt the rules set in
   advance or a stop of the system itself pauses the sample. A pause stops new
   cases counting, while every position held through it keeps counting its
   results and the cases it skipped are scored by replay, reported apart and
   counted toward the share scored by replay. Past the total the plan named
   for pauses a person starts or ends, such as a drill recorded as one before
   it starts, their cases are scored as a stop's are. Numbers from a sample
   that ended without a verdict, from a run with no sample open, and cases
   reported apart, are labelled exploratory, and what is promoted is the exact
   version the passing sample ran on, and a result that ends the process,
   reached after the pass, withdraws it.
3. **Where a process's actions can lose money, each action that adds to a
   position has its worst loss fixed first, and a check refuses rather than
   resizes.** Douglas's exit for a losing trade says in advance how much must
   be risked to learn whether the trade works (TZ L3095), and a trader whose
   total risk is too large cuts the size and leaves each trade's risk where
   the research set it (TZ L3220). Here the worst loss comes from a stated
   stress case over a stated window, with every part of the position moving
   against it, counting every action already sent, working or unanswered,
   under each case of which ones fill, or from the planned exit where that is
   a fixed level and larger. The project adds the reason: a jump or a halt can
   carry the result past any exit. An action counts as reducing only when it
   reduces that position and the total the limit covers, under every case, and
   the part of an action that crosses zero counts as adding. A stress value
   that is missing, stale, not a finite positive number or outside a stated
   sane range is bad input, and halts as bad input does. A check refuses an
   action that adds to a position whose worst loss it cannot compute, never
   refuses an action that only reduces the position for want of that figure,
   though a halt's own rule decides whether it holds that action, and never
   resizes. The step that sizes actions makes them smaller, and makes actions
   sized together smaller together. Tests cover an action one step short of
   zero, at zero and past it, an action already sent on each side, a loss that
   cannot be computed, and a bad stress value.
4. **Where a process's actions can lose money, no process, agent or proposal
   raises the stake after a run of good results, except on a rule or evidence
   set out before the run.** Douglas holds that a trader is most likely to
   break rules and oversize while winning, and that a larger position
   magnifies the next move against it (TZ L919, L943). A proposed raise of a
   limit or a stake cites the evidence the plan named before the run, never a
   streak. For a process whose sizing rule reads no results, a test runs the
   same inputs, account value and limits with no record of results, after a
   run of good ones and after a run of bad ones, and asserts the stake is
   identical.

The price of these rules is a checksum and a format version on every stored
record, an id on every write to another system, a lease number on every write
that needs one, histograms in place of averages, a test harness that can
inject faults, an import check in CI, a run of the suite under `python -O`, a
type for each kind of outside value, a contract suite for each stand-in, a
second implementation in the tests of each result whose error costs money, a
measurement for each tuning change, a timeout per outside call, a limit and a
breaker per dependency that can stall others, the artifact's hash, a test on
configuration that differs between environments, a correlation id, a synthetic
transaction, an alarm at the level where planning the rewrite starts, startup
checks that are the tested code, run where each release runs, an approval no
agent session holds on every deploy credential, where the owner deploys by
hand, a rollback that waits on a merge, a start that needs a copy to answer,
infrastructure code with a scheduled check that finds no difference, a cap on
every automatic restart, a log pipeline off the machine, a sample plan written
before any process with chance outcomes is judged, a recorded outcome for
every case with a running match that alarms, and a worst loss computed before
each action that adds to a position that can lose money. What they buy is
stored data that survives the bugs in the code around it, a 10x design that
holds along parameters it has named, and judgements of a chance process that
one outcome or one streak cannot move.

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
| *Trading in the Zone*'s sample of at least 20 trades as the unit that judges a process | Douglas found it from his experience and gives no data for it (TZ L3198). A sample that small can detect only a large effect, so each project sets its sample from the smallest effect worth detecting and the spread of the outcomes it expects, under [A process with chance outcomes is judged over a sample set in advance](#a-process-with-chance-outcomes-is-judged-over-a-sample-set-in-advance) |
| A copy of the build board's skills in each repository | Four repositories held their own copies of the build board's skills, and each copy held something the others lacked, which [l3a0/claude-plugins#28](https://github.com/l3a0/claude-plugins/issues/28) inventoried. The skills moved into the `l3a0` Claude Code plugin on 2026-10-29, and a seeded repository installs the plugin rather than copying them. [#24](https://github.com/l3a0/repo-template/issues/24) had kept them per repository because a repository pins the generator to one commit while a plugin skill moves with each release. That is the price, and a second comes with it: every session runs what the plugin's `main` holds, hooks included, with no pull request in this repository to show a change. The plugin skill's `## Generator compatibility` table names the generator commits its formats were checked against. `tests/test_build_board_generator.py` reads the skill at a pinned plugin commit, so renaming a marker or a label the generator reads fails here until a matching plugin release exists. Other format changes rest on the plugin's release rule |
| Holding a reviewed, green branch back only while a build session holds its card | l3a0/marketlake's own page held such a branch back from the owner's queue only for `working:build`. The shared page holds it back for any `working:` label, and [#47](https://github.com/l3a0/repo-template/issues/47) kept that rule when it ported marketlake's review rule. The plugin's `sync-prune-next` skill already applied the stricter hold to marketlake's queue because it fails safe. marketlake's build-only check was the fix for [l3a0/marketlake PR #713](https://github.com/l3a0/marketlake/pull/713), adding a hold the sync skill had promised, rather than a decision that a decompose loop frees a branch. The price is that a reviewed, green pull request whose card carries `working:decompose` waits under "Waiting on my review" until the loop ends. Porting marketlake's rule would need a flag in `board.json`, because a change to the page alone would move a current caller's card. |
| A warning on a pull request whose closing link GitHub did not register | l3a0/marketlake's page drew one. Neither generator can write the entry that draws it, because each writes `linked` false only beside `partOf`, which [#47](https://github.com/l3a0/repo-template/issues/47) measured over 73 mixes of closing link and body. The `pr_items` docstring in `scripts/build_board.py` carries the reason, and the page carries no such warning. |
| Compiling assertions out of the production build | *Code Complete*'s default for assertions (CC p. 190), though it keeps the code that checks for important errors (CC p. 209). A guard that is tested and then compiled out is absent where it matters, so a guard raises explicitly and runs in every environment. [The code holds its own rules](#the-code-holds-its-own-rules-and-every-check-runs-in-production) carries the reasoning |
| A neutral value, the closest legal value, or logging and carrying on, as the answer to bad input where a wrong result costs more than none | *Code Complete* offers each one (CC p. 194, p. 195). Each turns bad input into a value the project acts on. A project whose wrong result is cheap may choose robustness instead, and says so here |
| Deploying every passing commit to production with no human step, where the owner deploys by hand | *The DevOps 2.0 Toolkit*'s continuous deployment runs from a commit to production with no human intervention (DT p. 20). A project whose owner deploys by hand takes the book's continuous delivery instead, where every passing build could be deployed and a person decides when (DT p. 19) |
| Restarting a component without limit, as Docker's `always` policy does | The book lists the policy, which restarts a container whatever its exit status (DT p. 345). A restart without limit hides the cause of a crash loop, so each component has a written cap, and only a component whose stop loses unrecoverable data or a cancel keeps restarting past it, with a page |
| A fixed sleep to wait for something to start | The book pauses its playbook for a fixed time and says such a pause should be rarely used (DT p. 200). A fixed sleep passes or fails by timing, so every check that starts something waits on readiness with a timeout |
| TODO | TODO |
