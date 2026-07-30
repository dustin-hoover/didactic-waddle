"""Offline tests for the network feeds (no real HTTP)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ampl_bot.feeds as feeds
from ampl_bot.feeds import CoinGeckoFeed, OnChainFeed


def test_coingecko_reduces_to_daily(monkeypatch):
    # Two points on the same UTC day + one on the next; expect 2 daily bars,
    # keeping the LAST observation per day.
    day1 = 1_700_000_000_000  # ms
    fake = {"prices": [[day1, 1.00], [day1 + 3_600_000, 1.05], [day1 + 90_000_000, 0.98]]}
    monkeypatch.setattr(feeds, "_http_json", lambda *a, **k: fake)
    bars = CoinGeckoFeed().history(days=2)
    assert len(bars) == 2
    assert bars[0].price == 1.05  # last obs of day 1
    assert bars[1].price == 0.98
    assert bars[0].timestamp < bars[1].timestamp


def test_onchain_price_math(monkeypatch):
    ampl = OnChainFeed.__init__  # noqa: F841 (import smoke)
    feed = OnChainFeed(ampl_token="0x" + "aa" * 20)

    def fake_eth_call(to, data):
        if data == feeds.SEL_TOKEN0:
            return "0x" + "00" * 12 + "aa" * 20  # token0 == AMPL
        if data == feeds.SEL_GET_RESERVES:
            # reserve0 (AMPL, 9 dec) = 100 AMPL, reserve1 (WETH, 18 dec) = 50 WETH
            r0 = (100 * 10**9).to_bytes(32, "big").hex()
            r1 = (50 * 10**18).to_bytes(32, "big").hex()
            ts = (0).to_bytes(32, "big").hex()
            return "0x" + r0 + r1 + ts
        if data == feeds.SEL_LATEST_ANSWER:
            return hex(3000 * 10**8)  # ETH/USD = $3000, 8 decimals
        raise AssertionError("unexpected selector")

    monkeypatch.setattr(feed, "_eth_call", fake_eth_call)
    # eth_per_ampl = 50/100 = 0.5; * 3000 = $1500
    assert abs(feed.spot_price() - 1500.0) < 1e-6


def test_onchain_history_not_implemented():
    raised = False
    try:
        OnChainFeed().history()
    except NotImplementedError:
        raised = True
    assert raised


def test_onchain_falls_back_across_endpoints(monkeypatch):
    feed = OnChainFeed(rpc_urls=["http://bad1", "http://good"])
    calls = {"n": 0}

    def fake_http(url, data=None, tries=2, timeout=30):
        calls["n"] += 1
        if url == "http://bad1":
            raise RuntimeError("down")
        return {"result": "0x" + "00" * 32}

    monkeypatch.setattr(feeds, "_http_json", fake_http)
    assert feed._eth_call("0xto", "0xdata") == "0x" + "00" * 32
    assert calls["n"] == 2  # tried bad1 then good
