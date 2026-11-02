# ADR-003: Three measurements that were wrong, and what they were replaced with

**Status.** Accepted. The corrections are the most useful thing in the repository, so they
are written down rather than quietly fixed.

## The first: a model that let inserts and deletes cancel

The model in `theory.py` tracked the cursor's displacement as one signed number: positive
for rows inserted above it, negative for rows deleted from above it. That is correct
whenever only one of those is happening, and it is wrong the moment both are.

An inserted row is not a resurrected original, and deleting an original does not undo an
insert. They are different populations sitting in different places in the ordering, and a
single counter makes them cancel.

The mixed-mode scan is what exposed it. Seven of the eight scans in E1 matched the model
exactly and the eighth disagreed - a few pages and a few rows out, in the direction of
reporting the scan as quieter than it was. The model now carries two counters, `above` for
inserted rows and `removed` for deleted originals, and all eight scans agree to the row.

The part worth keeping is that the database caught the arithmetic, which is the opposite
of the usual direction. That only happened because the two were built to be compared.

## The second: a warm-up that looked like a result

E2 measures what one page costs at a given depth, and its first version reported that
keyset latency rose more than fourfold from the shallowest depth to the deepest.

An index seek does not read the offset, so that cannot be true, and an impossible result
means the instrument is wrong rather than the world being surprising. The sweep had warmed
each depth once and then measured depth by depth in order, so the depths measured first
were still paying for page faults the later ones did not have to.

Two checks settled it. Repeating the sweep in reverse order moved the rise to the other
end, which is the signature of an ordering artefact rather than a property of the query.
Interleaving the measurements across all depths in a shuffled order, after several warm-up
passes, flattened it: the keyset medians now wander by a factor of two with no trend in
them at all, and the deep half **grows 1.08x** over the shallow half while the offset
query over the same depths **grows 34x**.

The check changed with it. Comparing the largest keyset median to the smallest tests the
spread of sub-millisecond numbers on a shared machine, which is noise; the claim is that
cost does not grow with depth, so growth is what is tested.

## The third: a query the prediction forgot

E3 predicts the total rows an offset scan reads and compares it to what the scan actually
read. The two disagreed by exactly one full table scan at every size, which is the kind of
error that is either trivial or important and is worth two minutes to find out which.

It was important, in a small way. A paginator that stops when a page comes back short
never learns it has finished when the table divides evenly by the page size: the last full
page looks like any other, so the loop asks for one more and gets nothing back. The
database reads the entire table to hand back that nothing, which makes it the single most
expensive query in the whole scan.

The measurement was right and the arithmetic was incomplete. `full_scan_rows_read` now
takes a `terminating_page` flag, and E3 passes it.

## What the three have in common

None was caught by a test. The first was caught by two instruments disagreeing, the second
by a number that could not be true, the third by a prediction missing by a suspiciously
round amount. Tests check what you thought of in advance. Building two things that have to
agree, and then looking hard at the gap, is what catches the rest.
