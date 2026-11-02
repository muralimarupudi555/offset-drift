"""Shared fixtures.

Tests that need a database take `dsn`. There is no skip-if-unavailable guard: a suite that
quietly passes with half its tests skipped means something different from one machine to
the next. `docker compose up -d` or the CI service container is a precondition.
"""

from __future__ import annotations

import psycopg
import pytest

from offset_drift.config import DEFAULT_DSN


@pytest.fixture(scope="session")
def dsn() -> str:
    return DEFAULT_DSN


@pytest.fixture
def conn(dsn: str):
    with psycopg.connect(dsn, autocommit=True) as connection:
        yield connection
