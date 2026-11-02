"""The two paginators against a real table and a real index."""

from __future__ import annotations

from offset_drift.database import Writer, ensure_schema
from offset_drift.paginators import KeysetPaginator, OffsetPaginator, build

ROWS = 400
PAGE = 50


def test_build_returns_each_paginator(conn, dsn):
    ensure_schema(dsn, ROWS)
    assert build("offset", conn, PAGE).name == "offset"
    assert build("keyset", conn, PAGE).name == "keyset"


def test_build_refuses_an_unknown_name(conn):
    import pytest

    with pytest.raises(ValueError, match="unknown paginator"):
        build("magic", conn, PAGE)


def test_both_agree_on_a_quiet_table(conn, dsn):
    ensure_schema(dsn, ROWS)
    offset = OffsetPaginator(conn, PAGE)
    keyset = KeysetPaginator(conn, PAGE)
    for _ in range(ROWS // PAGE):
        assert offset.next_page() == keyset.next_page()


def test_a_scan_returns_newest_first(conn, dsn):
    ensure_schema(dsn, ROWS)
    page = OffsetPaginator(conn, PAGE).next_page()
    assert page[0] == ROWS
    assert page == sorted(page, reverse=True)


def test_an_exhausted_scan_returns_nothing(conn, dsn):
    ensure_schema(dsn, ROWS)
    paginator = KeysetPaginator(conn, PAGE)
    for _ in range(ROWS // PAGE):
        paginator.next_page()
    assert paginator.next_page() == []


def test_the_offset_paginator_reports_what_the_database_read(conn, dsn):
    ensure_schema(dsn, ROWS)
    paginator = OffsetPaginator(conn, PAGE)
    paginator.next_page()
    assert paginator.explain_rows_read() == PAGE
    paginator.next_page()
    assert paginator.explain_rows_read() == PAGE * 2


def test_the_keyset_paginator_reads_one_page_whatever_the_depth(conn, dsn):
    ensure_schema(dsn, ROWS)
    paginator = KeysetPaginator(conn, PAGE)
    for _ in range(ROWS // PAGE):
        paginator.next_page()
        assert paginator.explain_rows_read() == PAGE


def test_an_insert_lands_above_the_whole_feed(conn, dsn):
    ensure_schema(dsn, ROWS)
    Writer(conn, ROWS, 5, "insert").after_page()
    assert OffsetPaginator(conn, PAGE).next_page()[0] == ROWS + 5


def test_a_delete_removes_the_newest_originals(conn, dsn):
    ensure_schema(dsn, ROWS)
    Writer(conn, ROWS, 5, "delete").after_page()
    assert OffsetPaginator(conn, PAGE).next_page()[0] == ROWS - 5


def test_the_keyset_cursor_is_unmoved_by_an_insert(conn, dsn):
    """The guarantee, demonstrated rather than asserted."""
    ensure_schema(dsn, ROWS)
    paginator = KeysetPaginator(conn, PAGE)
    first = paginator.next_page()
    Writer(conn, ROWS, 20, "insert").after_page()
    second = paginator.next_page()
    assert not set(first) & set(second)
    assert second[0] == first[-1] - 1
