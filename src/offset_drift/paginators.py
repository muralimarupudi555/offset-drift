"""Two ways to ask for the next page, differing in what they name.

The offset paginator counts to the boundary. The keyset paginator names it. That is the
entire difference, and it is the reason one of them drifts and the other does not.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import psycopg

OFFSET_SQL = "SELECT id FROM od_feed ORDER BY id DESC LIMIT %s OFFSET %s"
KEYSET_SQL = "SELECT id FROM od_feed WHERE id < %s ORDER BY id DESC LIMIT %s"
KEYSET_FIRST_SQL = "SELECT id FROM od_feed ORDER BY id DESC LIMIT %s"


class Paginator(ABC):
    name: str

    def __init__(self, conn: psycopg.Connection, page_size: int) -> None:
        self.conn = conn
        self.page_size = page_size
        self.page = 0

    @abstractmethod
    def next_page(self) -> list[int]:
        """Return the next page of ids, or an empty list when the scan is done."""

    @abstractmethod
    def explain_rows_read(self) -> int:
        """Rows the database actually read to produce the most recent page."""


class OffsetPaginator(Paginator):
    """`LIMIT L OFFSET (i-1)L`, which is a count, not a position."""

    name = "offset"

    def next_page(self) -> list[int]:
        offset = self.page * self.page_size
        rows = self.conn.execute(OFFSET_SQL, (self.page_size, offset)).fetchall()
        self.page += 1
        self._last_offset = offset
        return [int(r[0]) for r in rows]

    def explain_rows_read(self) -> int:
        return getattr(self, "_last_offset", 0) + self.page_size


class KeysetPaginator(Paginator):
    """`WHERE id < last_seen`, which is a position and cannot be moved by a writer."""

    name = "keyset"

    def __init__(self, conn: psycopg.Connection, page_size: int) -> None:
        super().__init__(conn, page_size)
        self.cursor: int | None = None

    def next_page(self) -> list[int]:
        if self.cursor is None:
            rows = self.conn.execute(KEYSET_FIRST_SQL, (self.page_size,)).fetchall()
        else:
            rows = self.conn.execute(
                KEYSET_SQL, (self.cursor, self.page_size)).fetchall()
        self.page += 1
        ids = [int(r[0]) for r in rows]
        if ids:
            self.cursor = ids[-1]
        return ids

    def explain_rows_read(self) -> int:
        return self.page_size


def build(paginator: str, conn: psycopg.Connection, page_size: int) -> Paginator:
    if paginator == "offset":
        return OffsetPaginator(conn, page_size)
    if paginator == "keyset":
        return KeysetPaginator(conn, page_size)
    raise ValueError(f"unknown paginator {paginator!r}")
