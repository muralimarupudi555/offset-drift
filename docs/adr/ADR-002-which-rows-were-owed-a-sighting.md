# ADR-002: Which rows were owed a sighting

**Status.** Accepted. This is the definition every number in the repository rests on, so
it is worth being explicit about what it includes and what it lets through.

## The decision

A row is owed exactly one sighting if it was present when the scan started and still
present when the scan finished. Rows matching that description and never returned are
counted as **skipped**. Rows returned more than once are counted as **duplicates**. Rows
the writer inserted during the scan are counted separately and folded into neither.

## Why not something simpler

The obvious alternative is "every row that was there at the start should come back
exactly once". It is wrong, and it is wrong in the direction that flatters the paginator's
accuser: a row the writer deleted halfway through the scan was never owed anything, and
counting it as skipped blames the paginator for the writer's work. With five deletes per
page over seventy-odd pages that is several hundred rows of fictional drift, which would
have been larger than the real effect.

The opposite alternative - "every row present at the end should come back" - is wrong
too, because it includes rows inserted mid-scan, and whether a reader should see those is a
product decision rather than a correctness one.

The intersection is the only set with an unambiguous answer, so that is the set.

## What this definition gives up

It cannot see a row that was deleted and reinserted with the same key, which would look
like a row that was present throughout.

It says nothing about **order**. A scan could return every owed row exactly once and still
return them jumbled, and nothing here would notice. For a feed read by a human that matters
and is not measured.

It treats inserted rows as neutral, and the most interesting single fact in E1 is about
exactly those rows: an offset scan over a table being appended to **sees 0 of them**. The
cursor counts forward by the page size each page while the writer pushes rows down more
slowly, so the new rows stay permanently above the cursor's reach. That is reported, but it
is reported as an observation rather than as a defect, because the definition above
deliberately declines to say whether a reader was owed them.

## Where the numbers come from

Sightings are tallied from the ids each page returned, and the set of surviving rows is
read from the table after the scan finishes. Neither of those consults the paginator, the
writer, or the arithmetic. The model in `theory.py` predicts the same two numbers from the
cursor positions alone, and the two have to agree.
