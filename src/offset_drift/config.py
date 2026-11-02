"""Scenario configuration, validated on construction."""

from __future__ import annotations

import os
from dataclasses import dataclass

PAGINATORS = ("offset", "keyset")
WRITE_MODES = ("none", "insert", "delete", "mixed")

MIN_ROWS = 200

DEFAULT_DSN = os.environ.get(
    "OFFSET_DRIFT_DSN",
    "postgresql://postgres:postgres@127.0.0.1:5433/postgres",
)


class ConfigError(ValueError):
    """Raised when a scenario cannot show what it claims to show."""


@dataclass(frozen=True)
class ScanConfig:
    """One paginated scan, with a writer changing the table underneath it."""

    paginator: str = "offset"
    rows: int = 2000
    page_size: int = 50
    write_mode: str = "insert"
    writes_per_page: int = 5
    pages: int = 0
    seed: int = 20260219
    dsn: str = DEFAULT_DSN

    def __post_init__(self) -> None:
        if self.paginator not in PAGINATORS:
            raise ConfigError(
                f"paginator must be one of {PAGINATORS}, got {self.paginator!r}")
        if self.write_mode not in WRITE_MODES:
            raise ConfigError(
                f"write_mode must be one of {WRITE_MODES}, got {self.write_mode!r}")
        if self.rows < MIN_ROWS:
            raise ConfigError(
                f"rows={self.rows} is below {MIN_ROWS}. The effect is counted in rows "
                "skipped over a whole scan, and a table small enough to fit in two "
                "pages cannot drift far enough to count anything."
            )
        if self.page_size < 1:
            raise ConfigError("page_size must be at least 1")
        if self.page_size > self.rows:
            raise ConfigError(
                f"page_size={self.page_size} exceeds rows={self.rows}: the scan would "
                "finish in one page and never move a cursor at all"
            )
        if self.writes_per_page < 0:
            raise ConfigError("writes_per_page cannot be negative")
        if self.write_mode == "none" and self.writes_per_page:
            raise ConfigError(
                "write_mode 'none' with writes_per_page above zero is contradictory; "
                "set writes_per_page to 0 or choose a write mode"
            )
        if self.write_mode != "none" and self.writes_per_page == 0:
            raise ConfigError(
                f"write_mode {self.write_mode!r} with no writes per page is the quiet "
                "table in disguise, and would report a clean scan as though concurrency "
                "had been tested"
            )
        if self.pages < 0:
            raise ConfigError("pages cannot be negative")

    @property
    def page_count(self) -> int:
        """How many pages the scan will take, if not capped explicitly."""
        if self.pages:
            return self.pages
        return -(-self.rows // self.page_size)

    def as_dict(self) -> dict:
        return {
            "paginator": self.paginator, "rows": self.rows,
            "page_size": self.page_size, "write_mode": self.write_mode,
            "writes_per_page": self.writes_per_page, "pages": self.pages,
            "seed": self.seed,
        }
