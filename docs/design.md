# Design — PROJECT_NAME

<!-- TEMPLATE: this doc carries the reasoning. The tracker carries unbuilt
     scope, and this doc links to an issue rather than restating it. Write the
     premise first and leave the rest to grow as decisions get made. -->

## Contents

- [Premise](#premise)
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
| TODO | TODO |
