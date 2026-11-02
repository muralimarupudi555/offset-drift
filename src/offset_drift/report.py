"""Turn a scan into a verdict, and check the model against the database while doing it.

Every report re-runs the index arithmetic in `theory.py` for the same scenario and
compares it to what PostgreSQL did. The two are independent: one is a pure simulation with
no database in it, the other is a real query against a real index. When they agree, the
mechanism is understood rather than merely observed, and when they disagree the report
refuses to publish a drift figure.

That guard has already earned its place. An earlier model folded inserts and deletes into
a single signed shift, which is right whenever only one of them is happening and wrong the
moment both are. The mixed-mode scan disagreed by exactly that error.
"""

from __future__ import annotations

from dataclasses import dataclass

from offset_drift import theory
from offset_drift.config import ScanConfig
from offset_drift.harness import ScanResult, run_scan


@dataclass(frozen=True)
class Report:
    result: ScanResult

    @property
    def config(self) -> ScanConfig:
        return self.result.config

    @property
    def predicted(self) -> theory.ScanOutcome:
        config = self.config
        simulate = (theory.simulate_offset if config.paginator == "offset"
                    else theory.simulate_keyset)
        return simulate(config.rows, config.page_size, config.writes_per_page,
                        config.write_mode)

    @property
    def model_agrees(self) -> bool:
        predicted, result = self.predicted, self.result
        return (predicted.pages == result.pages
                and predicted.duplicates == result.duplicates
                and predicted.skipped == result.skipped
                and predicted.new_rows_seen == result.new_rows_seen)

    @property
    def rows_skipped(self) -> bool:
        return self.result.skipped > 0

    @property
    def rows_duplicated(self) -> bool:
        return self.result.duplicates > 0

    @property
    def overlap_per_page(self) -> int:
        return theory.overlap_per_page(
            self.config.page_size, self.config.writes_per_page,
            self.config.write_mode)

    def as_dict(self) -> dict:
        return {
            **self.result.as_dict(),
            "predicted": self.predicted.as_dict(),
            "model_agrees": self.model_agrees,
            "rows_skipped": self.rows_skipped,
            "rows_duplicated": self.rows_duplicated,
            "overlap_per_page": self.overlap_per_page,
        }


def build_report(config: ScanConfig) -> Report:
    return Report(result=run_scan(config))
