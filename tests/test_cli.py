"""Exit codes, because they are the interface a pipeline uses."""

from __future__ import annotations

import json

from offset_drift.cli import (
    EXIT_BAD_CONFIG,
    EXIT_CLEAN,
    EXIT_ROWS_DUPLICATED,
    EXIT_ROWS_SKIPPED,
    main,
)


def test_deletes_under_an_offset_scan_exit_four(dsn, capsys):
    code = main(["--write-mode", "delete", "--rows", "1000", "--dsn", dsn])
    assert code == EXIT_ROWS_SKIPPED
    assert "never returned by any page" in capsys.readouterr().out


def test_inserts_under_an_offset_scan_exit_one(dsn, capsys):
    code = main(["--write-mode", "insert", "--rows", "1000", "--dsn", dsn])
    assert code == EXIT_ROWS_DUPLICATED
    assert "returned more than once" in capsys.readouterr().out


def test_a_quiet_offset_scan_exits_zero(dsn):
    assert main(["--write-mode", "none", "--writes-per-page", "0",
                 "--rows", "1000", "--dsn", dsn]) == EXIT_CLEAN


def test_keyset_exits_zero_under_deletes(dsn):
    assert main(["--paginator", "keyset", "--write-mode", "delete",
                 "--rows", "1000", "--dsn", dsn]) == EXIT_CLEAN


def test_a_bad_scenario_exits_two(dsn, capsys):
    assert main(["--rows", "10", "--dsn", dsn]) == EXIT_BAD_CONFIG
    assert "invalid scenario" in capsys.readouterr().err


def test_an_unreachable_database_exits_three(capsys):
    code = main(["--rows", "1000", "--dsn",
                 "postgresql://postgres@127.0.0.1:1/postgres"])
    assert code == 3
    assert "failed to complete" in capsys.readouterr().err


def test_json_output_parses(dsn, capsys):
    main(["--paginator", "keyset", "--rows", "1000", "--json", "--dsn", dsn])
    payload = json.loads(capsys.readouterr().out)
    assert payload["clean"] is True
    assert payload["model_agrees"] is True


def test_the_report_says_the_reader_saw_no_new_rows(dsn, capsys):
    main(["--write-mode", "insert", "--rows", "1000", "--dsn", dsn])
    assert "saw none of the rows inserted" in capsys.readouterr().out
