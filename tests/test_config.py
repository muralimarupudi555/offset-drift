"""A scan that cannot show the effect should not start."""

from __future__ import annotations

import pytest

from offset_drift.config import ConfigError, ScanConfig


def test_defaults_are_valid():
    assert ScanConfig().paginator == "offset"


@pytest.mark.parametrize("paginator", ["offset", "keyset"])
def test_both_paginators_accepted(paginator):
    assert ScanConfig(paginator=paginator).paginator == paginator


def test_unknown_paginator_refused():
    with pytest.raises(ConfigError, match="paginator must be one of"):
        ScanConfig(paginator="cursor_probably")


def test_unknown_write_mode_refused():
    with pytest.raises(ConfigError, match="write_mode must be one of"):
        ScanConfig(write_mode="chaos")


def test_a_tiny_table_refused():
    with pytest.raises(ConfigError, match="two pages"):
        ScanConfig(rows=50)


def test_a_page_larger_than_the_table_refused():
    with pytest.raises(ConfigError, match="never move a cursor"):
        ScanConfig(rows=500, page_size=800)


def test_a_write_mode_with_no_writes_refused():
    """Otherwise a clean scan is reported as though concurrency had been tested."""
    with pytest.raises(ConfigError, match="quiet table in disguise"):
        ScanConfig(write_mode="insert", writes_per_page=0)


def test_no_write_mode_with_writes_refused():
    with pytest.raises(ConfigError, match="contradictory"):
        ScanConfig(write_mode="none", writes_per_page=5)


def test_the_quiet_table_is_configurable():
    assert ScanConfig(write_mode="none", writes_per_page=0).page_count > 1


def test_page_count_rounds_up():
    assert ScanConfig(rows=2001, page_size=50, write_mode="none",
                      writes_per_page=0).page_count == 41


def test_an_explicit_page_cap_wins():
    assert ScanConfig(rows=2000, page_size=50, pages=3).page_count == 3


def test_config_is_frozen():
    config = ScanConfig()
    with pytest.raises(AttributeError):
        config.rows = 10  # type: ignore[misc]


def test_as_dict_round_trips():
    config = ScanConfig(paginator="keyset", rows=900, write_mode="delete")
    assert ScanConfig(**config.as_dict()).as_dict() == config.as_dict()
