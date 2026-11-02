# ADR-005: The gate could not see itself

**Status.** Accepted. Written after the first push to GitHub, where this repository's build
failed on a step that had never run anywhere else.

## What happened

Every check passed locally. `make verify` was green from a clean clone, twice, and left the
working tree untouched. The build failed on the first push.

The last step of the CI workflow ran a diagram renderer and compared the diagram it
produced against the committed one. Neither the renderer nor the diagram exists in this
repository. The workflow had been adapted from a sibling project that does have both, and
that step was left behind.

## Why nothing caught it

Two reasons, and the second is the interesting one.

The adaptation was done by text substitution, and the text it was looking for had changed
in the source file since the version it was written against. A substitution that matches
nothing does not fail; it silently does nothing and hands back the original. Every later
step reported success on a file that had not been edited.

The deeper reason is that `make verify` runs the same *checks* as CI but not the same
*file*. The gate re-derives the arithmetic, re-renders the tables, re-reads every document
and confirms the working tree is clean - and had no opinion whatsoever about the workflow
that would run it. A gate that cannot see the thing that invokes it has a blind spot
exactly the size of that file, and nothing inside the blind spot is checked by anything.

## The fix

`tools/check_workflow.py` reads every workflow file and asserts that each script it runs
and each path it diffs exists on disk. It runs as the first step of CI, before anything is
installed, and inside `make verify`.

It was written against the live failure: run on the broken workflow it named both missing
paths, and run after the fix it passes. That ordering matters more than usual here, because
a checker written after the bug is gone has never been shown to detect anything.

It is a text scan rather than a YAML parse, deliberately. It needs no dependency, it cannot
be confused by a step whose shell is doing something clever, and the question it answers -
does this path exist - is a question about the filesystem rather than about YAML.

## What it still does not check

That the workflow's steps are the right steps, that they run in a sensible order, or that
they match what `make verify` does. A workflow that checks nothing at all passes this
check, as does one that omits the law check entirely.

Keeping those in step is still a human job, and the honest statement is that this guard
closes one specific hole: a path that is named and is not there. That was the hole this
repository fell into, and it is a hole that any project assembled by adapting a sibling's
configuration can fall into the same way.
