"""Re-derive the index arithmetic and check the recorded measurements against it.

The timings in E2 and E3 belong to this machine. The drift counts and the scaling do not:
they follow from where an offset cursor lands, which is arithmetic. So the arithmetic is
what gets re-checked on every verify, and it holds on hardware that has never run a scan.

It was run against tampered results before being trusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offset_drift import theory  # noqa: E402

EXPERIMENTS = ROOT / "docs" / "experiments"


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(f"missing {path.relative_to(ROOT)}, run `make bench` first")
    return json.loads(path.read_text())


def check_e1(problems: list[str]) -> None:
    data = load("e1.json")
    rows, page = data["rows"], data["page_size"]

    for row in data["results"]:
        simulate = (theory.simulate_offset if row["paginator"] == "offset"
                    else theory.simulate_keyset)
        predicted = simulate(rows, page, row["writes_per_page"], row["write_mode"])
        label = f"{row['paginator']}/{row['write_mode']}"
        for field in ("pages", "duplicates", "skipped", "new_rows_seen"):
            if row[field] != getattr(predicted, field):
                problems.append(
                    f"E1 {label}: {field} is {row[field]}, the arithmetic says "
                    f"{getattr(predicted, field)}"
                )
        if not row["model_agrees"]:
            problems.append(f"E1 {label}: the run itself recorded a disagreement")

    for row in data["results"]:
        if row["paginator"] == "keyset" and not row["clean"]:
            problems.append(
                f"E1 keyset/{row['write_mode']}: a named boundary cannot be moved by a "
                "writer, so a keyset scan that drifts means the cursor logic is wrong"
            )
        if row["paginator"] == "offset" and row["write_mode"] == "none" \
                and not row["clean"]:
            problems.append("E1 offset/none: a quiet table cannot drift")
        if row["paginator"] == "offset" and row["write_mode"] == "delete" \
                and row["skipped"] == 0:
            problems.append(
                "E1 offset/delete: deleting above the cursor must step over rows"
            )
        if row["paginator"] == "offset" and row["write_mode"] == "insert" \
                and row["duplicates"] == 0:
            problems.append(
                "E1 offset/insert: inserting above the cursor must re-show rows"
            )


def check_e2(problems: list[str]) -> None:
    data = load("e2.json")
    page = data["page_size"]

    for row in data["measurements"]:
        expected = theory.rows_scanned_by_offset(row["depth"], page)
        if row["rows_read_by_offset"] != expected:
            problems.append(
                f"E2 depth={row['depth']}: rows read recorded as "
                f"{row['rows_read_by_offset']}, the arithmetic says {expected}"
            )
    if not data["offset_rises_with_depth"]:
        problems.append("E2: offset latency must rise with depth; it reads the offset")
    if not data["offset_cost_is_linear_in_rows_read"]:
        problems.append(
            f"E2: the per-row cost spread is {data['per_row_spread']}x, so the offset "
            "query's cost is not tracking the rows it reads and the run is measuring "
            "something else"
        )
    if not data["keyset_is_flat"]:
        problems.append(
            f"E2: keyset cost grew {data['keyset_growth_deep_over_shallow']}x from the "
            "shallow depths to the deep ones; an index seek does not read the offset"
        )


def check_e3(problems: list[str]) -> None:
    data = load("e3.json")
    page = data["page_size"]

    for row in data["measurements"]:
        expected = theory.full_scan_rows_read(row["rows"], page, terminating_page=True)
        if row["offset_rows_read"] != expected:
            problems.append(
                f"E3 rows={row['rows']}: offset read {row['offset_rows_read']}, the "
                f"arithmetic says {expected}"
            )
        if row["keyset_rows_read"] < row["rows"]:
            problems.append(
                f"E3 rows={row['rows']}: a keyset scan read {row['keyset_rows_read']} "
                "rows, which is fewer than the table it returned"
            )
    if not data["offset_scales_quadratically"]:
        problems.append(
            f"E3: offset time grew {data['offset_time_growth_per_doubling']} per "
            "doubling, which is not the quadratic the arithmetic predicts"
        )
    if not data["keyset_scales_linearly"]:
        problems.append(
            f"E3: keyset time grew {data['keyset_time_growth_per_doubling']} per "
            "doubling, which is not linear"
        )


def main() -> int:
    problems: list[str] = []
    check_e1(problems)
    check_e2(problems)
    check_e3(problems)

    if problems:
        print("law check failed:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f"\n{len(problems)} problem(s). A recorded measurement no longer matches the "
            "arithmetic it was derived from. Re-run `make bench`, and if the problem "
            "survives, the mechanism changed and the prose needs to change with it.",
            file=sys.stderr,
        )
        return 1

    print("law check passed: every recorded scan still matches the index arithmetic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
