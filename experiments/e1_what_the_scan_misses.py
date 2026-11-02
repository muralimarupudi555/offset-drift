"""E1. What a paginated scan returns while the table changes under it.

Four write modes, both paginators, eight scans. For each one the index arithmetic in
`theory.py` predicts the outcome with no database involved, and the scan runs it against a
real index. The two have to agree to the row.

That agreement is the claim this repository actually makes. Anybody can observe that
offset pagination misbehaves under concurrent writes; what is worth having is the exact
count, derived from the one line of arithmetic that causes it, and reproduced by the
database to the row.
"""

from __future__ import annotations

import json
from pathlib import Path

from offset_drift import theory
from offset_drift.config import DEFAULT_DSN, ScanConfig
from offset_drift.report import build_report

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
ROWS = 4000
PAGE = 50
WRITES = 5

MODES = [("none", 0), ("insert", WRITES), ("delete", WRITES), ("mixed", WRITES)]


def main() -> None:
    rows = []
    for mode, writes in MODES:
        for paginator in ("offset", "keyset"):
            config = ScanConfig(paginator=paginator, rows=ROWS, page_size=PAGE,
                                write_mode=mode, writes_per_page=writes,
                                dsn=DEFAULT_DSN)
            report = build_report(config)
            result = report.result
            rows.append({
                "paginator": paginator, "write_mode": mode,
                "writes_per_page": writes,
                "pages": result.pages, "survivors": result.survivors,
                "duplicates": result.duplicates, "skipped": result.skipped,
                "skipped_share": result.skipped_share,
                "new_rows_seen": result.new_rows_seen,
                "rows_read": result.rows_read,
                "model_agrees": report.model_agrees,
                "clean": result.clean,
            })
            print(f"  {paginator:7} {mode:7} pages {result.pages:3}  "
                  f"dup {result.duplicates:4}  skipped {result.skipped:4}  "
                  f"new seen {result.new_rows_seen:3}  "
                  f"model {'agrees' if report.model_agrees else 'DISAGREES'}")

    offset_rows = [r for r in rows if r["paginator"] == "offset"]
    keyset_rows = [r for r in rows if r["paginator"] == "keyset"]
    delete_row = next(r for r in offset_rows if r["write_mode"] == "delete")
    insert_row = next(r for r in offset_rows if r["write_mode"] == "insert")
    mixed_row = next(r for r in offset_rows if r["write_mode"] == "mixed")

    payload = {
        "experiment": "e1_what_the_scan_misses",
        "rows": ROWS, "page_size": PAGE, "writes_per_page": WRITES,
        "results": rows,
        "model_agrees_everywhere": all(r["model_agrees"] for r in rows),
        "keyset_always_clean": all(r["clean"] for r in keyset_rows),
        "delete_skipped": delete_row["skipped"],
        "delete_skipped_share": round(delete_row["skipped_share"], 5),
        "insert_duplicates": insert_row["duplicates"],
        "mixed_skipped": mixed_row["skipped"],
        "mixed_duplicates": mixed_row["duplicates"],
        "new_rows_seen_under_inserts": insert_row["new_rows_seen"],
        "quiet_offset_clean": next(
            r["clean"] for r in offset_rows if r["write_mode"] == "none"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e1.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"the model reproduces the database in all eight scans: "
          f"{payload['model_agrees_everywhere']}")
    print(f"keyset was clean in every write mode: {payload['keyset_always_clean']}")
    print(f"deletes hid {delete_row['skipped']} rows that were present throughout, "
          f"{delete_row['skipped_share']:.1%} of the table")
    print(f"inserts returned {insert_row['duplicates']} rows twice and showed the reader "
          f"{insert_row['new_rows_seen']} of the new ones")
    print(f"the overlap per page is {theory.overlap_per_page(PAGE, WRITES, 'insert')} "
          f"rows, which is the write rate")


if __name__ == "__main__":
    main()
