# ADR-004: What this cannot measure

**Status.** Accepted. Read this before quoting any figure from here.

## A single snapshot fixes the drift, and that is not measured

Every page here is its own statement, so each one sees its own snapshot. A reader that
holds one transaction open across the entire scan in `REPEATABLE READ` sees a single
snapshot throughout, and offset pagination over that snapshot does not drift at all - the
rows cannot move, because the reader is not looking at the rows that moved.

That is a real and underused answer to the problem in this repository, and nothing here
measures it. It has costs of its own, which are also not measured: a long-running
transaction holds back vacuum, accumulates a snapshot the whole cluster has to respect, and
is a poor fit for a scan paced by a human clicking "next". Cursors (`DECLARE ... CURSOR`)
are the same idea with the same caveat. Neither appears in these numbers, and a reader who
concludes from this repository that keyset pagination is the only fix has read too much
into it.

## The timings are this machine's

E2 and E3 ran on a two-core container with a local PostgreSQL and a table that fits in
memory. On a cold cache or a table larger than the buffer pool the absolute numbers change
completely, and the offset scan gets relatively worse, because the rows it reads and throws
away are rows it may have to fetch from disk first.

What survives is the arithmetic: cost tracks the rows read, and the rows read are the
offset plus the page. That is why the law check re-derives the counts rather than
re-asserting the milliseconds.

## Deleting from the top is the clean case

The writer removes the newest surviving rows, which shifts every remaining row by the same
amount and is what the model describes exactly. Deletes scattered through the table shift
only the rows after them, so the drift becomes a function of where each delete fell relative
to the cursor - the same effect in kind, smaller in size, and needing a different model to
predict. It is not measured here.

## One reader, one writer, no contention

The writer is free and nothing competes for pages or locks. A production scan runs against
a database doing other work, and the offset query's extra reads are extra pressure on the
same buffer pool the rest of the application is using. That makes the measured ratios a
floor rather than a ceiling.

## Order is not checked

The accounting counts sightings, not sequence. A scan could return every owed row exactly
once and still return them in a jumbled order, and nothing here would notice. For a feed
read by a human that matters.

## Keyset has a cost this does not show

Keyset pagination needs the sort key to be unique, or a tiebreaker added to it, and it
cannot jump to page fifty. "Page 50 of 200" is a thing offset pagination can do and keyset
cannot, and some products need it. Nothing in these experiments weighs that against the
drift, because it is a product question rather than a measurable one.

## What is left standing

The arithmetic: where an offset cursor lands after the table has shifted, that inserts
above the cursor re-show rows while deletes above it step over them, that the work is the
offset plus the page, and that paging through everything is therefore quadratic. Those are
properties of the index and the query, and they survive every gap above.
