"""What a paginated scan returns while the table moves, derived before measuring.

Order the feed newest first, which is what feeds do. Original rows occupy positions
`0..n-1` in that ordering. A writer inserting at the top pushes every original row
further down; a writer deleting from the top pulls every original row up.

`LIMIT L OFFSET (i-1)L` does not ask for "page i". It asks the database to discard
`(i-1)L` rows of whatever the query returns at that moment and hand back the next `L`. So
the original rows page `i` actually covers start at::

    start_i = (i - 1) * L - shift_i

where `shift_i` is the net number of rows inserted above the cursor before page `i` was
fetched, negative for deletions. Everything in this repository follows from that one line.

**Inserting at the top.** With `k` inserts between pages, `shift_i = (i - 1) * k`, so the
window advances by `L - k` each page while covering `L` rows. Consecutive pages overlap by
`k`, and the reader is shown `k` rows it has already seen, every page, for the whole scan.
Worse and less obvious: while `k < L` the cursor never reaches back far enough to return
any of the new rows either, so a reader paging through a busy feed sees old rows twice and
new rows never.

**Deleting from the top.** `shift_i` is negative, the window advances by `L + k`, and `k`
rows between consecutive pages are stepped over entirely. Nothing errors, every page comes
back full, and the rows are simply gone from the result.

**Keyset.** `WHERE id < last_seen ORDER BY id DESC LIMIT L` names the boundary instead of
counting to it. Rows inserted above the cursor are above the boundary and cannot move it;
rows deleted above the cursor were already behind it. `shift_i` does not appear, so
neither does the drift.

The functions below simulate that arithmetic exactly, with no database involved. The
experiments run the same scans against PostgreSQL. If the two agree, the mechanism is
understood rather than merely observed.
"""

from __future__ import annotations

from dataclasses import dataclass

# A cap so a scan whose window advances slowly cannot run forever. It is generous: a scan
# that needs more pages than this has already made the point.
MAX_PAGES = 10_000


@dataclass(frozen=True)
class ScanOutcome:
    """What a scan saw, in terms of original row positions."""

    pages: int
    returned: int
    distinct_originals: int
    duplicates: int
    skipped: int
    new_rows_seen: int

    def as_dict(self) -> dict:
        return {
            "pages": self.pages, "returned": self.returned,
            "distinct_originals": self.distinct_originals,
            "duplicates": self.duplicates, "skipped": self.skipped,
            "new_rows_seen": self.new_rows_seen,
        }


def simulate_offset(rows: int, page_size: int, writes_per_page: int,
                    mode: str) -> ScanOutcome:
    """Walk the offset cursor over a shifting ordering and count what it touched.

    Two counters, not one. `above` is how many rows the writer inserted at the top of the
    feed, and `removed` is how many originals it deleted from the top of the original
    block. An earlier version folded them into a single signed shift, which is correct
    whenever only one of them is happening and wrong the moment both are: an inserted row
    is not a resurrected original, and deleting an original does not cancel an insert.
    The mixed-mode scan disagreed with the database by exactly that error.
    """
    seen: dict[int, int] = {}
    new_seen = 0
    above = 0
    removed = 0
    page = 0
    returned = 0

    while page < MAX_PAGES:
        offset = page * page_size
        total = (rows - removed) + above
        if offset >= total:
            break

        taken = min(page_size, total - offset)
        for slot in range(offset, offset + taken):
            if slot < above:
                new_seen += 1
                continue
            position = slot - above + removed
            if position < rows:
                seen[position] = seen.get(position, 0) + 1
        returned += taken
        page += 1

        if mode == "insert":
            above += writes_per_page
        elif mode == "delete":
            removed = min(rows, removed + writes_per_page)
        elif mode == "mixed":
            if page % 2:
                above += writes_per_page
            else:
                removed = min(rows, removed + writes_per_page)

    duplicates = sum(count - 1 for count in seen.values() if count > 1)
    # Positions `0..removed-1` are the originals the writer deleted from the top. They
    # were never owed a sighting, so they are excluded rather than counted as skipped.
    skipped = sum(1 for position in range(removed, rows) if position not in seen)
    return ScanOutcome(
        pages=page, returned=returned, distinct_originals=len(seen),
        duplicates=duplicates, skipped=skipped, new_rows_seen=new_seen,
    )


def simulate_keyset(rows: int, page_size: int, writes_per_page: int,
                    mode: str) -> ScanOutcome:
    """The same walk with a named boundary instead of a count.

    Inserted rows are above the boundary and invisible to it; deleted rows were already
    behind it. The cursor advances by exactly one page of surviving rows each time, so
    the page count is the quiet table's page count whatever the writer does.
    """
    pages = -(-rows // page_size) if rows else 0
    removed = 0
    if mode == "delete":
        removed = min(rows, writes_per_page * pages)
    elif mode == "mixed":
        removed = min(rows, writes_per_page * (pages // 2))
    survivors = rows - removed
    return ScanOutcome(
        pages=pages, returned=survivors, distinct_originals=survivors,
        duplicates=0, skipped=0, new_rows_seen=0,
    )


def overlap_per_page(page_size: int, writes_per_page: int, mode: str) -> int:
    """Rows re-shown, or stepped over, between one page and the next."""
    if mode == "none" or writes_per_page == 0:
        return 0
    return min(writes_per_page, page_size)


def rows_scanned_by_offset(offset: int, page_size: int) -> int:
    """What the database reads to answer one page: the discarded rows plus the kept ones.

    This is why depth costs. The rows before the offset are not free to skip; they are
    read and thrown away.
    """
    return offset + page_size


def full_scan_rows_read(rows: int, page_size: int) -> int:
    """Total rows read to page through a quiet table with OFFSET, which is quadratic.

    Summing `offset + page_size` over every page gives roughly `n^2 / (2L) + n`. Keyset
    reads `n`, because each page starts where the last one stopped.
    """
    pages = -(-rows // page_size)
    return sum(rows_scanned_by_offset(p * page_size, page_size) for p in range(pages))


def full_scan_rows_read_keyset(rows: int) -> int:
    return rows
