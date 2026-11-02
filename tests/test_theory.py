"""The index arithmetic, tested as properties and against known hand-worked cases."""

from __future__ import annotations

from offset_drift import theory

ROWS = 2000
PAGE = 50


def test_a_quiet_table_scans_cleanly():
    outcome = theory.simulate_offset(ROWS, PAGE, 0, "none")
    assert outcome.duplicates == 0
    assert outcome.skipped == 0
    assert outcome.pages == ROWS // PAGE


def test_inserting_at_the_top_causes_duplicates_not_skips():
    outcome = theory.simulate_offset(ROWS, PAGE, 5, "insert")
    assert outcome.duplicates > 0
    assert outcome.skipped == 0


def test_deleting_from_the_top_causes_skips_not_duplicates():
    outcome = theory.simulate_offset(ROWS, PAGE, 5, "delete")
    assert outcome.skipped > 0
    assert outcome.duplicates == 0


def test_mixing_them_causes_both():
    outcome = theory.simulate_offset(ROWS, PAGE, 5, "mixed")
    assert outcome.duplicates > 0
    assert outcome.skipped > 0


def test_inserts_and_deletes_do_not_cancel():
    """The model bug that the database caught.

    An inserted row is not a resurrected original, and deleting an original does not
    undo an insert. A model that folds them into one signed shift reports a mixed scan
    as quieter than it is.
    """
    mixed = theory.simulate_offset(ROWS, PAGE, 5, "mixed")
    assert mixed.duplicates + mixed.skipped > 0


def test_drift_grows_with_the_write_rate():
    drift = [
        theory.simulate_offset(ROWS, PAGE, k, "delete").skipped for k in (1, 2, 5, 10)
    ]
    assert drift == sorted(drift)


def test_a_reader_sees_none_of_the_inserted_rows():
    """While the writer is slower than the page size, new rows stay out of reach."""
    outcome = theory.simulate_offset(ROWS, PAGE, 5, "insert")
    assert outcome.new_rows_seen == 0


def test_a_writer_faster_than_the_page_lets_new_rows_through():
    outcome = theory.simulate_offset(ROWS, PAGE, PAGE * 2, "insert")
    assert outcome.new_rows_seen > 0


def test_keyset_never_drifts_whatever_the_writer_does():
    for mode, k in (("none", 0), ("insert", 5), ("delete", 5), ("mixed", 5)):
        outcome = theory.simulate_keyset(ROWS, PAGE, k, mode)
        assert outcome.duplicates == 0, mode
        assert outcome.skipped == 0, mode


def test_keyset_takes_the_quiet_page_count_whatever_the_writer_does():
    quiet = theory.simulate_keyset(ROWS, PAGE, 0, "none").pages
    for mode in ("insert", "delete", "mixed"):
        assert theory.simulate_keyset(ROWS, PAGE, 5, mode).pages == quiet


def test_overlap_is_the_write_rate_capped_by_the_page():
    assert theory.overlap_per_page(50, 5, "insert") == 5
    assert theory.overlap_per_page(50, 500, "insert") == 50
    assert theory.overlap_per_page(50, 5, "none") == 0


def test_one_page_costs_the_offset_plus_the_page():
    assert theory.rows_scanned_by_offset(10_000, 50) == 10_050


def test_a_full_offset_scan_is_quadratic():
    small = theory.full_scan_rows_read(1000, 50)
    large = theory.full_scan_rows_read(2000, 50)
    assert large / small > 3.5


def test_a_full_keyset_scan_is_linear():
    assert theory.full_scan_rows_read_keyset(2000) == 2000
    assert theory.full_scan_rows_read_keyset(4000) == 4000


def test_the_offset_scan_reads_far_more_than_the_table():
    assert theory.full_scan_rows_read(ROWS, PAGE) > 10 * ROWS


def test_the_terminating_query_is_the_most_expensive_one():
    """A full last page gives no hint that it is the last, so the loop asks again.

    The database then reads the whole table to return nothing. Leaving this out made the
    prediction in E3 disagree with the measurement by exactly one table scan.
    """
    without = theory.full_scan_rows_read(ROWS, PAGE)
    with_it = theory.full_scan_rows_read(ROWS, PAGE, terminating_page=True)
    assert with_it - without == theory.rows_scanned_by_offset(ROWS, PAGE)


def test_a_table_that_does_not_divide_evenly_needs_no_terminating_query():
    """The short page announces the end, so nothing extra is asked for."""
    odd = ROWS + 7
    assert theory.full_scan_rows_read(odd, PAGE) == \
        theory.full_scan_rows_read(odd, PAGE, terminating_page=True)


def test_the_terminating_query_reads_more_than_any_other_page():
    pages = ROWS // PAGE
    last_real = theory.rows_scanned_by_offset((pages - 1) * PAGE, PAGE)
    terminating = theory.rows_scanned_by_offset(pages * PAGE, PAGE)
    assert terminating > last_real
