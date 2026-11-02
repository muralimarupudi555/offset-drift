# ADR-001: A writer that acts between pages, not on a thread of its own

**Status.** Accepted.

## The decision

The writer inserts and deletes between page fetches, in the same process, rather than
racing the reader from a separate thread or connection.

## Why

The mechanism under test is index arithmetic. `LIMIT L OFFSET (i-1)L` asks the database to
discard a count of rows from whatever the query returns at that moment, and the drift is
the difference between the count the reader meant and the rows actually there. Nothing
about that depends on two things happening at the same instant. It depends on the table
having changed between one page and the next, and *when* the change lands inside that
interval does not alter where the cursor comes down.

What a deterministic writer buys is the thing this repository is actually built around:
the scan can be compared against a model with no database in it. `theory.py` simulates the
same walk in pure arithmetic, and every scan in E1 agrees with it to the row. With a real
concurrent writer the counts would move between runs and the comparison would become a
tolerance band rather than an equality, which would weaken the claim without making it
more true.

## What is given up

Three things, named again in ADR-004.

Transaction isolation never comes into play. A real reader and writer overlap inside
PostgreSQL's MVCC, and a page fetched in `READ COMMITTED` sees a snapshot taken when that
statement began. That is exactly what happens here too - each page is its own statement,
and the writer has committed before the next one - so the snapshot behaviour is the same.
What is absent is the case where a long-running transaction holds a single snapshot across
the whole scan, which fixes the drift entirely and is discussed in ADR-004.

Lock contention and the writer's own cost are absent. The writer here is free, and in
production it is competing with the reader for the same pages.

The timing of the write inside the interval cannot be varied, so this cannot answer
questions about a writer that commits halfway through a page fetch. For a single statement
that question has no content, which is why it is not asked.

## Deleting from the top

The writer deletes the newest surviving original rows rather than random ones. That is the
case the arithmetic describes exactly - every surviving row shifts by the same amount - and
it is a real pattern: the most recent items in a feed are the ones moderated away, expired,
or retracted.

Deleting from the middle shifts only the rows after the deletion, so the drift becomes a
function of where each delete landed relative to the cursor, which is a distribution rather
than a count. The effect is the same in kind and smaller in size, and measuring it properly
would need a different model. ADR-004 says so rather than leaving the reader to assume this
covers it.
