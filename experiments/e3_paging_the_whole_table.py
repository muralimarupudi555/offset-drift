"""E3. Paging through everything costs the square of the table with OFFSET.

E2 measures one page at a depth. This measures the aggregate, because that is the shape of
the job that actually hurts: an export, a backfill, a nightly reconciliation that walks
every row fifty at a time.

Summing `offset + page_size` over every page gives roughly `n^2 / 2L`. Keyset reads `n`.
So doubling the table should roughly quadruple the offset scan's work and merely double
the keyset scan's, and that is a prediction sharp enough to be wrong.

Rows read is counted from the arithmetic, which is not independent of the prediction and
is not claimed to be. Wall time is the independent instrument: nothing about a clock knows
how many rows a plan intends to touch.

One detail in here was found by the two disagreeing. A paginator that stops when a page
comes back short never learns it has finished when the table divides evenly by the page
size, so it asks once more and gets nothing - and the database reads the entire table to
hand back that nothing. It is the single most expensive query in the scan, and the first
version of the prediction left it out.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import psycopg

from offset_drift import theory
from offset_drift.config import DEFAULT_DSN
from offset_drift.database import ensure_schema

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
SIZES = (10_000, 20_000, 40_000, 80_000)
PAGE = 50
# Doubling the table should quadruple a quadratic scan and double a linear one. The bands
# are wide because the small sizes still carry per-query overhead that is linear in the
# page count rather than in the rows read.
QUADRATIC_BAND = (2.8, 5.2)
LINEAR_BAND = (1.3, 3.0)

OFFSET_SQL = "SELECT id FROM od_feed ORDER BY id DESC LIMIT %s OFFSET %s"
KEYSET_SQL = "SELECT id FROM od_feed WHERE id < %s ORDER BY id DESC LIMIT %s"
KEYSET_FIRST_SQL = "SELECT id FROM od_feed ORDER BY id DESC LIMIT %s"


def page_everything(conn: psycopg.Connection, paginator: str) -> tuple[float, int, int]:
    """Walk the whole table and report wall time, pages and rows the plan read."""
    started = time.perf_counter()
    pages = 0
    rows_read = 0
    cursor = None

    while True:
        if paginator == "offset":
            offset = pages * PAGE
            got = conn.execute(OFFSET_SQL, (PAGE, offset)).fetchall()
            rows_read += theory.rows_scanned_by_offset(offset, PAGE)
        elif cursor is None:
            got = conn.execute(KEYSET_FIRST_SQL, (PAGE,)).fetchall()
            rows_read += PAGE
        else:
            got = conn.execute(KEYSET_SQL, (cursor, PAGE)).fetchall()
            rows_read += PAGE

        if not got:
            break
        pages += 1
        cursor = int(got[-1][0])
        if len(got) < PAGE:
            break

    return time.perf_counter() - started, pages, rows_read


def main() -> None:
    rows = []
    for size in SIZES:
        ensure_schema(DEFAULT_DSN, size)
        with psycopg.connect(DEFAULT_DSN, autocommit=True) as conn:
            conn.execute(OFFSET_SQL, (PAGE, 0)).fetchall()  # warm
            offset_s, offset_pages, offset_read = page_everything(conn, "offset")
            keyset_s, keyset_pages, keyset_read = page_everything(conn, "keyset")

        predicted_offset = theory.full_scan_rows_read(size, PAGE, terminating_page=True)
        rows.append({
            "rows": size,
            "offset_seconds": round(offset_s, 4),
            "keyset_seconds": round(keyset_s, 4),
            "offset_pages": offset_pages, "keyset_pages": keyset_pages,
            "offset_rows_read": offset_read,
            "predicted_offset_rows_read": predicted_offset,
            "keyset_rows_read": keyset_read,
            "read_amplification": round(offset_read / size, 1),
            "time_ratio": round(offset_s / keyset_s, 1),
        })
        print(f"  {size:7} rows  offset {offset_s:7.3f}s  keyset {keyset_s:6.3f}s  "
              f"{offset_s / keyset_s:6.1f}x   read {offset_read / size:7.1f}x the table")

    def growth(key: str) -> list[float]:
        return [
            rows[i + 1][key] / rows[i][key] for i in range(len(rows) - 1)
        ]

    offset_growth = growth("offset_seconds")
    keyset_growth = growth("keyset_seconds")
    offset_quadratic = all(QUADRATIC_BAND[0] <= g <= QUADRATIC_BAND[1]
                           for g in offset_growth)
    keyset_linear = all(LINEAR_BAND[0] <= g <= LINEAR_BAND[1] for g in keyset_growth)
    arithmetic_holds = all(
        r["offset_rows_read"] == r["predicted_offset_rows_read"] for r in rows)

    payload = {
        "experiment": "e3_paging_the_whole_table",
        "page_size": PAGE, "sizes": list(SIZES), "measurements": rows,
        "offset_time_growth_per_doubling": [round(g, 2) for g in offset_growth],
        "keyset_time_growth_per_doubling": [round(g, 2) for g in keyset_growth],
        "offset_scales_quadratically": offset_quadratic,
        "keyset_scales_linearly": keyset_linear,
        "rows_read_matches_the_arithmetic": arithmetic_holds,
        "largest_read_amplification": rows[-1]["read_amplification"],
        "largest_time_ratio": rows[-1]["time_ratio"],
        "largest_offset_seconds": rows[-1]["offset_seconds"],
        "largest_keyset_seconds": rows[-1]["keyset_seconds"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e3.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"offset time per doubling: {payload['offset_time_growth_per_doubling']} "
          f"-> quadratic: {offset_quadratic}")
    print(f"keyset time per doubling: {payload['keyset_time_growth_per_doubling']} "
          f"-> linear: {keyset_linear}")
    print(f"rows read matches the arithmetic exactly: {arithmetic_holds}")
    print(f"at {SIZES[-1]:,} rows the offset scan reads "
          f"{rows[-1]['read_amplification']}x the table to return it once")


if __name__ == "__main__":
    main()
