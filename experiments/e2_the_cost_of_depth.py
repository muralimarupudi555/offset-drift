"""E2. One page of fifty rows costs more the further into the table it is.

`OFFSET 500000` does not skip five hundred thousand rows cheaply. The database walks them,
discards them, and then returns the fifty that were asked for, so the work is the offset
plus the page. Keyset pagination seeks straight to the boundary, so its work is the page.

Measurements are interleaved in a shuffled order across every depth and both paginators,
rather than looping depth by depth. The first version did loop depth by depth after one
warm-up pass each, and reported that keyset latency rose more than fourfold with depth -
which cannot be true of an index seek, and was not. It was the warm-up. Repeating the
measurement in reverse order moved the rise to the other end, and interleaving it in
random order with a properly warm cache flattened it to noise with no trend at all.

The apparatus check is linearity. If the offset query's cost really is the rows it reads,
then time divided by `offset + page_size` is a constant, and a measurement where that
constant wanders is measuring something other than the scan.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path

import psycopg

from offset_drift import theory
from offset_drift.config import DEFAULT_DSN
from offset_drift.database import ensure_schema

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
ROWS = 1_000_000
PAGE = 50
DEPTHS = (0, 10_000, 100_000, 250_000, 500_000, 999_000)
REPEATS = 15
WARMUP_PASSES = 4
SHUFFLE_SEED = 20260219
# The per-row cost is a ratio of two measured quantities at very different scales, so it
# is checked by how far it spreads across depths rather than against a fixed figure. A
# factor of three covers the fixed per-query overhead that dominates at depth zero.
LINEARITY_SPREAD = 3.0

OFFSET_SQL = "SELECT id FROM od_feed ORDER BY id DESC LIMIT %s OFFSET %s"
KEYSET_SQL = "SELECT id FROM od_feed WHERE id < %s ORDER BY id DESC LIMIT %s"


def timed(conn: psycopg.Connection, sql: str, params: tuple) -> float:
    started = time.perf_counter()
    conn.execute(sql, params).fetchall()
    return (time.perf_counter() - started) * 1000.0


def main() -> None:
    print(f"  building {ROWS:,} rows...")
    ensure_schema(DEFAULT_DSN, ROWS)

    rows = []
    with psycopg.connect(DEFAULT_DSN, autocommit=True) as conn:
        # Several warm-up passes over every depth, not one. One pass leaves the depths
        # measured first still paying for page faults, which is the artefact described
        # in the docstring.
        for _ in range(WARMUP_PASSES):
            for depth in DEPTHS:
                timed(conn, OFFSET_SQL, (PAGE, depth))
                timed(conn, KEYSET_SQL, (ROWS - depth, PAGE))

        offset_samples: dict[int, list[float]] = {d: [] for d in DEPTHS}
        keyset_samples: dict[int, list[float]] = {d: [] for d in DEPTHS}

        schedule = [(d, kind) for d in DEPTHS for kind in ("offset", "keyset")] * REPEATS
        random.Random(SHUFFLE_SEED).shuffle(schedule)
        for depth, kind in schedule:
            if kind == "offset":
                offset_samples[depth].append(timed(conn, OFFSET_SQL, (PAGE, depth)))
            else:
                keyset_samples[depth].append(
                    timed(conn, KEYSET_SQL, (ROWS - depth, PAGE)))

        for depth in DEPTHS:
            offset_ms = statistics.median(offset_samples[depth])
            keyset_ms = statistics.median(keyset_samples[depth])
            read = theory.rows_scanned_by_offset(depth, PAGE)
            rows.append({
                "depth": depth,
                "offset_ms": round(offset_ms, 4),
                "keyset_ms": round(keyset_ms, 4),
                "ratio": round(offset_ms / keyset_ms, 2),
                "rows_read_by_offset": read,
                "us_per_row_read": round(offset_ms * 1000 / read, 4),
            })
            print(f"  depth {depth:7}  offset {offset_ms:8.3f}ms  "
                  f"keyset {keyset_ms:6.3f}ms  {offset_ms / keyset_ms:7.1f}x  "
                  f"{offset_ms * 1000 / read:6.3f} us per row read")

    deep = [r for r in rows if r["depth"] >= 100_000]
    per_row = [r["us_per_row_read"] for r in deep]
    linear = max(per_row) / min(per_row) <= LINEARITY_SPREAD

    # The claim about keyset is that its cost does not grow with depth, so growth is
    # what gets tested. Comparing max to min would test the spread of sub-millisecond
    # medians on a shared machine, which is noise: these values move around by a factor
    # of two with no trend in them at all, and a spread test calls that a failure while
    # a trend test correctly calls it flat.
    keyset_values = [r["keyset_ms"] for r in rows]
    half = len(rows) // 2
    shallow_keyset = statistics.median(r["keyset_ms"] for r in rows[:half])
    deep_keyset = statistics.median(r["keyset_ms"] for r in rows[half:])
    shallow_offset = statistics.median(r["offset_ms"] for r in rows[:half])
    deep_offset = statistics.median(r["offset_ms"] for r in rows[half:])
    keyset_growth = deep_keyset / shallow_keyset
    offset_growth = deep_offset / shallow_offset
    keyset_flat = keyset_growth <= 1.5
    offset_values = [r["offset_ms"] for r in rows]

    payload = {
        "experiment": "e2_the_cost_of_depth",
        "rows": ROWS, "page_size": PAGE, "repeats": REPEATS, "depths": list(DEPTHS),
        "measurements": rows,
        "offset_rises_with_depth": offset_values == sorted(offset_values),
        "offset_cost_is_linear_in_rows_read": linear,
        "per_row_spread": round(max(per_row) / min(per_row), 2),
        "keyset_is_flat": keyset_flat,
        "keyset_growth_deep_over_shallow": round(keyset_growth, 3),
        "offset_growth_deep_over_shallow": round(offset_growth, 1),
        "keyset_spread": round(max(keyset_values) / min(keyset_values), 2),
        "deepest_ratio": rows[-1]["ratio"],
        "deepest_offset_ms": rows[-1]["offset_ms"],
        "deepest_keyset_ms": rows[-1]["keyset_ms"],
        "shallow_offset_ms": rows[0]["offset_ms"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e2.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"offset latency rises with depth:  {payload['offset_rises_with_depth']}")
    print(f"and is linear in the rows it reads: "
          f"{payload['offset_cost_is_linear_in_rows_read']} "
          f"(per-row cost spread {payload['per_row_spread']}x)")
    print(f"keyset shows no growth with depth: {payload['keyset_is_flat']} "
          f"(deep/shallow {keyset_growth:.2f}x, against offset's "
          f"{offset_growth:.0f}x over the same depths)")
    print(f"at depth {DEPTHS[-1]:,} the same page costs "
          f"{payload['deepest_ratio']}x as much")


if __name__ == "__main__":
    main()
