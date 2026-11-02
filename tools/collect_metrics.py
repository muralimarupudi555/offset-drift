"""Read the experiment outputs and write the file every document is checked against."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"

CHECKED_DOCUMENTS = (
    "README.md",
    "docs/adr/ADR-001-a-writer-between-pages.md",
    "docs/adr/ADR-002-which-rows-were-owed-a-sighting.md",
    "docs/adr/ADR-003-three-measurements-that-were-wrong.md",
    "docs/adr/ADR-004-what-this-cannot-measure.md",
)


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(
            f"missing {path.relative_to(ROOT)}. Run `make bench` first: the documents "
            "are checked against measurements."
        )
    return json.loads(path.read_text())


def count_tests() -> int:
    out = subprocess.run(
        ["python3", "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    per_file = re.findall(r"^\S+\.py: (\d+)$", out, re.MULTILINE)
    if per_file:
        return sum(int(n) for n in per_file)
    for line in reversed(out.splitlines()):
        match = re.match(r"^(\d+) tests? collected", line.strip())
        if match:
            return int(match.group(1))
    node_ids = sum(1 for line in out.splitlines() if "::" in line)
    if node_ids == 0:
        raise SystemExit(
            "could not count tests from pytest's output; fix count_tests() rather than "
            "letting a zero reach the README."
        )
    return node_ids


def main() -> None:
    e1, e2, e3 = (load(f"e{i}.json") for i in (1, 2, 3))

    deepest = e2["measurements"][-1]
    largest = e3["measurements"][-1]

    metrics = {
        "rows": e1["rows"],
        "page_size": e1["page_size"],
        "writes_per_page": e1["writes_per_page"],
        "delete_skipped": e1["delete_skipped"],
        "delete_skipped_share": e1["delete_skipped_share"],
        "insert_duplicates": e1["insert_duplicates"],
        "mixed_skipped": e1["mixed_skipped"],
        "mixed_duplicates": e1["mixed_duplicates"],
        "new_rows_seen": e1["new_rows_seen_under_inserts"],

        "depth_rows": e2["rows"],
        "deepest_depth": deepest["depth"],
        "deepest_offset_ms": deepest["offset_ms"],
        "deepest_keyset_ms": deepest["keyset_ms"],
        "deepest_ratio": deepest["ratio"],
        "per_row_spread": e2["per_row_spread"],
        "keyset_growth": e2["keyset_growth_deep_over_shallow"],
        "offset_growth": e2["offset_growth_deep_over_shallow"],

        "largest_scan_rows": largest["rows"],
        "largest_offset_seconds": largest["offset_seconds"],
        "largest_keyset_seconds": largest["keyset_seconds"],
        "largest_read_amplification": largest["read_amplification"],
        "largest_time_ratio": largest["time_ratio"],

        "tests": count_tests(),
    }

    display = {
        "delete_skipped_share": f"{metrics['delete_skipped_share']:.1%}",
        "deepest_depth": f"{metrics['deepest_depth']:,}",
        "deepest_offset_ms": f"{metrics['deepest_offset_ms']:.1f}",
        "deepest_keyset_ms": f"{metrics['deepest_keyset_ms']:.2f}",
        "deepest_ratio": f"{metrics['deepest_ratio']:.0f}",
        "per_row_spread": f"{metrics['per_row_spread']:.2f}",
        "keyset_growth": f"{metrics['keyset_growth']:.2f}",
        "offset_growth": f"{metrics['offset_growth']:.0f}",
        "depth_rows": f"{metrics['depth_rows']:,}",
        "largest_scan_rows": f"{metrics['largest_scan_rows']:,}",
        "largest_offset_seconds": f"{metrics['largest_offset_seconds']:.2f}",
        "largest_keyset_seconds": f"{metrics['largest_keyset_seconds']:.2f}",
        "largest_read_amplification": f"{metrics['largest_read_amplification']:.1f}",
        "largest_time_ratio": f"{metrics['largest_time_ratio']:.0f}",
    }
    for key, value in metrics.items():
        display.setdefault(key, str(value))

    anchors = {
        "rows": ["a table of {} rows"],
        "page_size": ["pages of {}"],
        "writes_per_page": ["{} writes between pages"],
        "delete_skipped": ["{} rows were never returned"],
        "delete_skipped_share": ["{} of the table"],
        "insert_duplicates": ["returns {} rows twice"],
        "mixed_skipped": ["skips {} rows"],
        "mixed_duplicates": ["duplicates {}"],
        "new_rows_seen": ["sees {} of them"],
        "depth_rows": ["a table of {}"],
        "deepest_depth": ["depth {}"],
        "deepest_offset_ms": ["{} ms"],
        "deepest_keyset_ms": ["{} ms"],
        "deepest_ratio": ["{} times as long"],
        "per_row_spread": ["within {}x"],
        "keyset_growth": ["grows {}x"],
        "offset_growth": ["grows {}x"],
        "largest_scan_rows": ["{} rows takes"],
        "largest_offset_seconds": ["{} seconds"],
        "largest_keyset_seconds": ["{} seconds"],
        "largest_read_amplification": ["{}x the table"],
        "largest_time_ratio": ["{}x longer"],
        "tests": ["{} tests"],
    }

    OUT.write_text(json.dumps({
        "metrics": metrics, "display": display, "anchors": anchors,
        "checked_documents": list(CHECKED_DOCUMENTS),
    }, indent=2) + "\n")
    print(f"collected {len(metrics)} metrics into {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
