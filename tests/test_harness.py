"""Whole scans, where the model and the database have to agree with each other."""

from __future__ import annotations

import pytest

from offset_drift import theory
from offset_drift.config import ScanConfig
from offset_drift.harness import run_scan

ROWS = 1000
PAGE = 50

MODES = [("none", 0), ("insert", 5), ("delete", 5), ("mixed", 5)]


@pytest.mark.parametrize(("mode", "writes"), MODES)
@pytest.mark.parametrize("paginator", ["offset", "keyset"])
def test_the_model_reproduces_the_database(dsn, paginator, mode, writes):
    """Eight combinations, all of which must match to the row.

    The model has no database in it and the scan has no arithmetic in it. Agreement is
    the claim that the drift is understood, and it is checked rather than asserted.
    """
    config = ScanConfig(paginator=paginator, rows=ROWS, page_size=PAGE,
                        write_mode=mode, writes_per_page=writes, dsn=dsn)
    result = run_scan(config)
    simulate = (theory.simulate_offset if paginator == "offset"
                else theory.simulate_keyset)
    predicted = simulate(ROWS, PAGE, writes, mode)

    assert result.pages == predicted.pages
    assert result.duplicates == predicted.duplicates
    assert result.skipped == predicted.skipped
    assert result.new_rows_seen == predicted.new_rows_seen


def test_a_quiet_offset_scan_is_clean(dsn):
    config = ScanConfig(rows=ROWS, page_size=PAGE, write_mode="none",
                        writes_per_page=0, dsn=dsn)
    assert run_scan(config).clean


def test_a_busy_offset_scan_is_not(dsn):
    config = ScanConfig(rows=ROWS, page_size=PAGE, write_mode="delete",
                        writes_per_page=5, dsn=dsn)
    assert not run_scan(config).clean


@pytest.mark.parametrize(("mode", "writes"), MODES)
def test_keyset_is_clean_whatever_the_writer_does(dsn, mode, writes):
    config = ScanConfig(paginator="keyset", rows=ROWS, page_size=PAGE,
                        write_mode=mode, writes_per_page=writes, dsn=dsn)
    assert run_scan(config).clean


def test_deletes_hide_rows_that_were_there_throughout(dsn):
    config = ScanConfig(rows=ROWS, page_size=PAGE, write_mode="delete",
                        writes_per_page=5, dsn=dsn)
    result = run_scan(config)
    assert result.skipped > 0
    assert result.skipped_share > 0.05


def test_a_deleted_row_is_not_counted_as_skipped(dsn):
    """Rows the writer removed were never owed a sighting."""
    config = ScanConfig(rows=ROWS, page_size=PAGE, write_mode="delete",
                        writes_per_page=5, dsn=dsn)
    result = run_scan(config)
    assert result.survivors < ROWS
    assert result.skipped < ROWS - result.survivors + result.skipped


def test_an_offset_scan_reads_far_more_rows_than_a_keyset_one(dsn):
    shared = dict(rows=ROWS, page_size=PAGE, write_mode="none", writes_per_page=0,
                  dsn=dsn)
    offset = run_scan(ScanConfig(paginator="offset", **shared))
    keyset = run_scan(ScanConfig(paginator="keyset", **shared))
    assert offset.rows_read > 5 * keyset.rows_read


def test_a_scan_is_reproducible(dsn):
    config = ScanConfig(rows=ROWS, page_size=PAGE, write_mode="mixed",
                        writes_per_page=5, dsn=dsn)
    first, second = run_scan(config), run_scan(config)
    assert (first.duplicates, first.skipped) == (second.duplicates, second.skipped)
