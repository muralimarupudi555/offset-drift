"""Command line entry point.

Exit code 4 is the one worth having. Rows that were present for the whole scan were never
returned by it. Every page came back the right size, no query failed, and the only way to
find out is to have kept a list.

Exit code 1 is the lesser cousin: rows returned more than once. Annoying in a feed,
expensive in a job that processes each page, and not data loss.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from offset_drift.config import PAGINATORS, WRITE_MODES, ConfigError, ScanConfig
from offset_drift.report import Report, build_report

EXIT_CLEAN = 0
EXIT_ROWS_DUPLICATED = 1
EXIT_BAD_CONFIG = 2
EXIT_INTERNAL_ERROR = 3
EXIT_ROWS_SKIPPED = 4
EXIT_MODEL_DISAGREES = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offset-drift",
        description="Measure what a paginated scan returns while the table changes.",
    )
    parser.add_argument("--paginator", choices=PAGINATORS, default="offset")
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--write-mode", choices=WRITE_MODES, default="insert")
    parser.add_argument("--writes-per-page", type=int, default=5)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def classify(report: Report) -> int:
    if not report.model_agrees:
        return EXIT_MODEL_DISAGREES
    if report.rows_skipped:
        return EXIT_ROWS_SKIPPED
    if report.rows_duplicated:
        return EXIT_ROWS_DUPLICATED
    return EXIT_CLEAN


def render(report: Report) -> str:
    config, result = report.config, report.result
    lines = [
        f"{config.paginator} pagination, {config.rows} rows, pages of "
        f"{config.page_size}, writer {config.write_mode} "
        f"{config.writes_per_page} per page",
        "",
        f"{'reading':<34}{'measured':>10}{'model':>10}",
        "-" * 54,
        f"{'pages fetched':<34}{result.pages:>10}{report.predicted.pages:>10}",
        f"{'rows owed a sighting':<34}{result.survivors:>10}",
        f"{'returned more than once':<34}{result.duplicates:>10}"
        f"{report.predicted.duplicates:>10}",
        f"{'never returned at all':<34}{result.skipped:>10}"
        f"{report.predicted.skipped:>10}",
        f"{'new rows the reader saw':<34}{result.new_rows_seen:>10}"
        f"{report.predicted.new_rows_seen:>10}",
        f"{'rows the database read':<34}{result.rows_read:>10}",
    ]
    if report.rows_skipped:
        lines += [
            "",
            f"{result.skipped} rows were present when the scan started, present when it "
            f"finished, and never returned by any page: "
            f"{result.skipped_share:.1%} of the table.",
            "Every page came back full and no query failed.",
        ]
    if report.rows_duplicated:
        lines += [
            "",
            f"{result.duplicates} rows were returned more than once, because the writer "
            f"moved {report.overlap_per_page} rows past the cursor between pages.",
        ]
    if result.new_rows_seen == 0 and config.write_mode in ("insert", "mixed"):
        lines.append(
            "The reader saw none of the rows inserted during the scan: the cursor "
            "counts forward faster than the writer pushes rows down."
        )
    if not report.model_agrees:
        lines += [
            "",
            "the index arithmetic in theory.py does not reproduce what the database "
            "did, so this run is not understood and its drift figures should not be used",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fields = dict(paginator=args.paginator, rows=args.rows,
                      page_size=args.page_size, write_mode=args.write_mode,
                      writes_per_page=args.writes_per_page)
        if args.dsn:
            fields["dsn"] = args.dsn
        config = ScanConfig(**fields)
    except ConfigError as exc:
        print(f"invalid scenario: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    try:
        report = build_report(config)
    except Exception as exc:  # noqa: BLE001
        print(f"scan failed to complete: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    print(json.dumps(report.as_dict(), indent=2) if args.json else render(report))
    return classify(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
