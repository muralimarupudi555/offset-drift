"""The table, and the writer that changes it under the scan.

The writer runs between page fetches rather than on a thread of its own. That is a
deliberate simplification and ADR-001 argues it: a real concurrent writer would add
nondeterminism without changing the mechanism, and the mechanism is index arithmetic. What
this buys is a scan that produces the same answer every time and can be compared against a
model that has no database in it.
"""

from __future__ import annotations

import psycopg

SCHEMA = """
DROP TABLE IF EXISTS od_feed;
CREATE TABLE od_feed (
    id bigint PRIMARY KEY,
    payload text NOT NULL
);
"""

# The feed is read newest first, so the index that serves it is descending. Without this
# every page is a sort of the whole table and the depth measurement in E2 would be
# measuring the sort rather than the offset.
INDEX = "CREATE INDEX od_feed_id_desc ON od_feed (id DESC);"


def ensure_schema(dsn: str, rows: int) -> None:
    """Build a table of `rows` rows with ids 1..rows."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO od_feed (id, payload) "
            "SELECT g, repeat('x', 64) FROM generate_series(1::bigint, %s::bigint) AS g",
            (rows,),
        )
        conn.execute(INDEX)
        conn.execute("ANALYZE od_feed")


def live_ids(conn: psycopg.Connection, up_to: int) -> set[int]:
    """Original ids still present, which are the only rows owed a sighting."""
    rows = conn.execute(
        "SELECT id FROM od_feed WHERE id <= %s", (up_to,)
    ).fetchall()
    return {int(r[0]) for r in rows}


def row_count(conn: psycopg.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM od_feed").fetchone()[0])


class Writer:
    """Inserts at the top of the feed, or deletes from it, between pages."""

    def __init__(self, conn: psycopg.Connection, original_rows: int,
                 writes_per_page: int, mode: str) -> None:
        self.conn = conn
        self.original_rows = original_rows
        self.writes_per_page = writes_per_page
        self.mode = mode
        self.next_id = original_rows + 1
        self.inserted = 0
        self.deleted = 0
        self.page = 0

    def _insert(self, count: int) -> None:
        if count <= 0:
            return
        self.conn.execute(
            "INSERT INTO od_feed (id, payload) "
            "SELECT g, repeat('y', 64) FROM generate_series(%s::bigint, %s::bigint) AS g",
            (self.next_id, self.next_id + count - 1),
        )
        self.next_id += count
        self.inserted += count

    def _delete_from_the_top(self, count: int) -> None:
        """Remove the newest surviving original rows.

        Deleting from the top is the case the model describes exactly, and it is what
        happens when the most recent items in a feed are moderated away or expire.
        Deleting from the middle shifts a subset of positions instead of all of them, and
        ADR-003 says what that does to these numbers.
        """
        if count <= 0:
            return
        self.deleted += self.conn.execute(
            "DELETE FROM od_feed WHERE id IN ("
            "  SELECT id FROM od_feed WHERE id <= %s ORDER BY id DESC LIMIT %s)",
            (self.original_rows, count),
        ).rowcount

    def after_page(self) -> None:
        self.page += 1
        if self.mode == "insert":
            self._insert(self.writes_per_page)
        elif self.mode == "delete":
            self._delete_from_the_top(self.writes_per_page)
        elif self.mode == "mixed":
            if self.page % 2:
                self._insert(self.writes_per_page)
            else:
                self._delete_from_the_top(self.writes_per_page)
