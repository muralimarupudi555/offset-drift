"""Run a paginated scan while a writer changes the table, and count what was missed.

The accounting is the careful part. A row is owed exactly one sighting if it was there
when the scan started and still there when it finished. A row the writer deleted part way
through was never owed anything, and counting it as skipped would blame the paginator for
the writer's work. ADR-002 argues that definition and names what it gives up.

Rows inserted during the scan are counted separately rather than being folded into either
number. Whether a reader "should" see them is a product decision, not a correctness one,
and the interesting fact about them turns out to be that an offset scan shows none of them
at all.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

import psycopg

from offset_drift.config import ScanConfig
from offset_drift.database import Writer, ensure_schema, live_ids
from offset_drift.paginators import build
from offset_drift.theory import MAX_PAGES


@dataclass(frozen=True)
class ScanResult:
    """One scan: what came back, and what that means for the rows owed a sighting."""

    config: ScanConfig
    pages: int
    returned: int
    distinct_originals: int
    duplicates: int
    skipped: int
    new_rows_seen: int
    survivors: int
    rows_read: int
    wall_seconds: float

    @property
    def clean(self) -> bool:
        return self.duplicates == 0 and self.skipped == 0

    @property
    def skipped_share(self) -> float:
        return self.skipped / self.survivors if self.survivors else 0.0

    def as_dict(self) -> dict:
        return {
            "config": self.config.as_dict(), "pages": self.pages,
            "returned": self.returned,
            "distinct_originals": self.distinct_originals,
            "duplicates": self.duplicates, "skipped": self.skipped,
            "new_rows_seen": self.new_rows_seen, "survivors": self.survivors,
            "skipped_share": round(self.skipped_share, 5),
            "rows_read": self.rows_read, "clean": self.clean,
            "wall_seconds": round(self.wall_seconds, 4),
        }


def run_scan(config: ScanConfig) -> ScanResult:
    """Page through the table, letting the writer act between pages."""
    ensure_schema(config.dsn, config.rows)
    sightings: Counter[int] = Counter()
    new_seen = 0
    rows_read = 0

    with psycopg.connect(config.dsn, autocommit=True) as conn:
        paginator = build(config.paginator, conn, config.page_size)
        writer = Writer(conn, config.rows, config.writes_per_page, config.write_mode)

        started = time.perf_counter()
        pages = 0
        while pages < MAX_PAGES:
            page = paginator.next_page()
            rows_read += paginator.explain_rows_read()
            if not page:
                break
            pages += 1
            for row_id in page:
                if row_id > config.rows:
                    new_seen += 1
                else:
                    sightings[row_id] += 1
            if config.pages and pages >= config.pages:
                break
            writer.after_page()
        wall = time.perf_counter() - started

        survivors = live_ids(conn, config.rows)

    duplicates = sum(count - 1 for count in sightings.values() if count > 1)
    skipped = len(survivors - set(sightings))

    return ScanResult(
        config=config, pages=pages, returned=sum(sightings.values()) + new_seen,
        distinct_originals=len(sightings), duplicates=duplicates, skipped=skipped,
        new_rows_seen=new_seen, survivors=len(survivors), rows_read=rows_read,
        wall_seconds=wall,
    )
