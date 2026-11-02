# offset-drift

**`LIMIT 50 OFFSET 400` is not "page nine". It is "discard four hundred rows of whatever
this query returns right now", and when the table has changed since page eight those are
not the same four hundred rows.**

Nothing errors. Every page comes back the right size. Rows are quietly returned twice, or
never returned at all, and the only way to find out is to have kept a list.

Over **a table of 4000 rows** in **pages of 50** with **5 writes between pages**, an offset
scan against a table being deleted from above the cursor returns every page full while
**330 rows were never returned** — **9.1% of the table**, present when the scan started and
still present when it finished. Keyset pagination over the same writer returns all of them.

## E1. What the scan misses

Four write modes, both paginators, eight scans. For each one the index arithmetic in
`theory.py` predicts the outcome with no database involved, and the scan runs it against a
real index. They agree to the row.

<!-- table:e1 -->
```text
paginator       writer   pages   twice   never  new seen   model
----------------------------------------------------------------
offset            none      80       0       0         0     yes
keyset            none      80       0       0         0     yes
offset          insert      89     440       0         0     yes
keyset          insert      80       0       0         0     yes
offset          delete      73       0     330         0     yes
keyset          delete      80       0       0         0     yes
offset           mixed      80     200     190         0     yes
keyset           mixed      80       0       0         0     yes
```
<!-- /table:e1 -->

- **Deletes above the cursor** make the window advance by `L + k` instead of `L`, so `k`
  rows between consecutive pages are stepped over. This is the dangerous direction: the
  rows are simply gone from the result.
- **Inserts above the cursor** make it advance by `L - k`, so consecutive pages overlap and
  the scan **returns 440 rows twice**. Worse and less obvious: it **sees 0 of them** — none
  of the newly inserted rows — because the cursor counts forward faster than the writer
  pushes rows down, so the new rows stay permanently out of reach.
- **Both at once** does both: the same scan **skips 190 rows** and **duplicates 200**.
- **Keyset** names the boundary instead of counting to it. Rows inserted above the cursor
  are above the boundary and cannot move it; rows deleted above it were already behind it.
  The shift term never enters the arithmetic, so neither does the drift.

That last point is the whole fix, and it is one clause: `WHERE id < :last_seen` instead of
`OFFSET :count`.

## E2. One page costs more the deeper it is

`OFFSET 500000` does not skip half a million rows cheaply. The database walks them,
discards them, and returns the fifty that were asked for.

<!-- table:e2 -->
```text
      depth   offset ms   keyset ms     ratio    rows read    us/row
--------------------------------------------------------------------
          0       0.315       0.516      0.6x           50     6.306
     10,000       1.426       0.267      5.3x       10,050     0.142
    100,000       9.734       0.349     27.9x      100,050     0.097
    250,000      24.173       0.367     65.8x      250,050     0.097
    500,000      47.959       0.413    116.0x      500,050     0.096
    999,000      96.302       0.376    256.3x      999,050     0.096
```
<!-- /table:e2 -->

Against **a table of 1,000,000**, the same page of fifty rows at **depth 999,000** takes
**96.3 ms** against the keyset query's **0.38 ms** — **256 times as long**.

The apparatus check is linearity. If the offset query's cost really is the rows it reads,
then time divided by `offset + page_size` is a constant, and across the deep half of the
sweep it holds **within 1.01x**. Keyset cost **grows 1.08x** from the shallow depths to the
deep ones while the offset query over the same depths **grows 34x**.

An earlier version of this experiment reported keyset latency rising fourfold with depth,
which cannot be true of an index seek. It was the warm-up, and
[ADR-003](docs/adr/ADR-003-three-measurements-that-were-wrong.md) records how that was
established.

## E3. Paging through everything is quadratic

Per-page cost compounds. Summing `offset + page_size` over every page gives roughly
`n² / 2L`, so doubling the table should roughly quadruple the work.

<!-- table:e3 -->
```text
      rows   offset s   keyset s    ratio   rows read
-----------------------------------------------------
    10,000      0.151      0.025     6.1x      101.5x
    20,000      0.511      0.047    10.9x      201.5x
    40,000      1.849      0.097    19.0x      401.5x
    80,000      7.141      0.217    32.9x      801.5x
```
<!-- /table:e3 -->

Paging through **80,000 rows takes** **7.14 seconds** with OFFSET and **0.22 seconds** with
keyset — **33x longer** — and the offset scan reads **801.5x the table** to return it once.

Hidden in that figure is the most expensive query of the scan. A paginator that stops when
a page comes back short never learns it has finished when the table divides evenly by the
page size, so it asks for one more page and gets nothing — and the database reads the
entire table to hand back that nothing. The prediction originally left it out, and the
measurement is what noticed.

## How the numbers are kept honest

Two instruments that have to agree. `theory.py` simulates the cursor walk in pure
arithmetic with no database in it; the harness runs real queries against a real index and
tallies sightings from the ids that came back. Neither consults the other. All eight scans
in E1 match to the row, and when they did not, it was the arithmetic that was wrong — the
model let inserts and deletes cancel, which they do not.

`tools/check_laws.py` re-derives the arithmetic on every `make verify` and checks it
against the committed results, so the published counts stay checkable on a machine that has
never run a scan. It was run against tampered results before being trusted.

`tools/check_numbers.py` matches figures to prose in both directions: every metric must
appear through an anchor phrase, and every decimal in the prose must correspond to a
metric. The tables above are generated from the experiment output and regenerated by
`make verify`.

Three measurements in this repository were wrong and are written up rather than quietly
fixed, in [ADR-003](docs/adr/ADR-003-three-measurements-that-were-wrong.md). None was
caught by a test.

## What this cannot measure

Read [ADR-004](docs/adr/ADR-004-what-this-cannot-measure.md) before quoting anything. The
most important omission first:

- **A single snapshot fixes the drift and is not measured here.** A reader holding one
  transaction open in `REPEATABLE READ`, or a declared cursor, sees rows that cannot move,
  and offset pagination over that snapshot does not drift at all. It has costs of its own —
  vacuum held back, a snapshot the cluster must respect — and none of them appear in these
  numbers. Anyone concluding from this repository that keyset is the only fix has read too
  much into it.
- The writer deletes from the top, which is the case the model describes exactly. Deletes
  scattered through the table shift only the rows after them: same effect, smaller, and
  needing a different model.
- The timings are this machine's, with a table that fits in memory. On a cold cache the
  offset scan gets relatively worse, because the rows it discards may have to be fetched
  first.
- Order is not checked. A scan could return every owed row exactly once, jumbled, and
  nothing here would notice.
- Keyset cannot jump to page fifty. Some products need that, and nothing here weighs it.

## Running it

`make verify` is the gate: lint, **68 tests**, the law check and the number check.

```bash
make install
make db-up      # PostgreSQL 16.15, pinned, on port 5433
make verify
make bench      # the three experiments, a few minutes
```

A single scan, with the exit code as the interface:

```bash
offset-drift --paginator offset --write-mode delete --rows 4000
```

| exit | meaning |
| --- | --- |
| 0 | every row owed a sighting got exactly one |
| 1 | rows came back more than once |
| 2 | the scenario cannot show the effect |
| 3 | the scan did not complete |
| 4 | rows present for the whole scan were never returned |
| 5 | the arithmetic does not reproduce what the database did |

Real transcripts are in [docs/cli-output.md](docs/cli-output.md).

## Layout

```text
src/offset_drift/
  config.py      scenario validation that refuses scans which cannot show the effect
  theory.py      the cursor walk as index arithmetic, with no database in it
  database.py    the table, and the writer that changes it between pages
  paginators.py  one that counts to the boundary, one that names it
  harness.py     sighting accounting: which rows were owed one, and which got it
  report.py      verdict, plus the refusal to publish a run the model cannot reproduce
  cli.py         exit codes
experiments/     the three experiments above
tools/           metric collection, the two checkers, the tables, the transcripts
docs/adr/        four decision records, including three mistakes and their fixes
```

## How this was built

This repository was built by Murali Marupudi working with Claude, an AI assistant, as a
pair-programming partner. The claim, the experimental design, the decisions about what to
measure and what to throw away, and the judgement calls recorded in the decision records
are the author's. Claude was used for implementation, for argument, and as a second pair of
eyes on the measurements.

## Licence

MIT. See [LICENSE](LICENSE).
