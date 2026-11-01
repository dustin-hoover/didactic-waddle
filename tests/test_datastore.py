"""Tests for the point-in-time, survivorship-free datastore (Phase 1.1).

Acceptance (from the action plan):
  * a coin delisted in 2022 still appears in the 2021 universe (no survivorship), and
  * shifting features by +1 bar changes the aligned series (a look-ahead canary)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot.datastore import BarRow, DataStore


def test_delisted_coin_in_past_universe_not_present_now(tmp_path):
    ds = DataStore(str(tmp_path))
    ds.record_listing("BTC", "2013-01-01")                      # still live
    ds.record_listing("LUNA", "2019-07-01", delisting_date="2022-05-13")  # died in 2022
    # 2021: LUNA was alive -> must be in the universe (survivorship-free).
    assert "LUNA" in ds.universe_asof("2021-06-01")
    assert "BTC" in ds.universe_asof("2021-06-01")
    # Today: LUNA is delisted -> absent; BTC still present.
    assert "LUNA" not in ds.universe_asof("2026-01-01")
    assert "BTC" in ds.universe_asof("2026-01-01")
    # Before LUNA listed: absent.
    assert "LUNA" not in ds.universe_asof("2018-01-01")


def test_feature_known_ts_blocks_lookahead(tmp_path):
    ds = DataStore(str(tmp_path))
    # A fundamental for Q1 (value_date Mar 31) only PUBLISHED on Apr 20.
    ds.append_feature("AAA", "revenue", 100.0, value_date="2021-03-31", known_ts="2021-04-20")
    # As of Apr 1, it was NOT yet known.
    assert ds.latest_feature("AAA", "revenue", "2021-04-01") is None
    # As of Apr 20+, it is known.
    assert ds.latest_feature("AAA", "revenue", "2021-04-20") == 100.0
    assert ds.latest_feature("AAA", "revenue", "2021-05-01") == 100.0


def test_known_ts_before_value_date_is_rejected(tmp_path):
    ds = DataStore(str(tmp_path))
    with pytest.raises(ValueError, match="look-ahead"):
        ds.append_feature("AAA", "x", 1.0, value_date="2021-03-31", known_ts="2021-03-01")


def test_lookahead_canary_shift_changes_series(tmp_path):
    ds = DataStore(str(tmp_path))
    bars = [BarRow(f"2021-01-{d:02d}", 1, 1, 1, float(d), 0) for d in range(1, 8)]
    ds.append_bars("AAA", "1d", bars)
    for d in range(1, 8):
        ds.append_feature("AAA", "mom", float(d * 10), value_date=f"2021-01-{d:02d}")
    base = ds.aligned_feature("AAA", "mom", "1d", lag_bars=0)
    lag1 = ds.aligned_feature("AAA", "mom", "1d", lag_bars=1)
    assert base == [10, 20, 30, 40, 50, 60, 70]
    # A one-bar shift MUST change the series — if it didn't, look-ahead is baked in.
    assert lag1 != base
    assert lag1 == [None, 10, 20, 30, 40, 50, 60]


def test_bars_roundtrip_sorted_and_appendable(tmp_path):
    ds = DataStore(str(tmp_path))
    ds.append_bars("BTC", "1d", [BarRow("2021-01-02", 1, 2, 0.5, 1.5, 10)])
    ds.append_bars("BTC", "1d", [("2021-01-01", 1, 2, 0.5, 1.2, 9)])     # tuple form, earlier
    got = ds.bars("BTC", "1d")
    assert [b.date for b in got] == ["2021-01-01", "2021-01-02"]         # sorted on read
    assert got[0].close == 1.2 and got[1].volume == 10


def test_features_asof_returns_history_up_to_date(tmp_path):
    ds = DataStore(str(tmp_path))
    for m, v in [("01", 10), ("02", 20), ("03", 30)]:
        ds.append_feature("AAA", "tvl", float(v), value_date=f"2021-{m}-01")
    rows = ds.features_asof("AAA", "tvl", "2021-02-15")
    assert rows == [("2021-01-01", 10.0), ("2021-02-01", 20.0)]          # March withheld
