"""Is delta-neutral CARRY real? An honest look at perp funding as coin-agnostic income.

The idea that matches "sustainable profits regardless of the coin, from a measurable
signal": hold spot long + short the perpetual future of the same coin. You're
delta-neutral (price up or down doesn't matter), and you EARN the funding rate —
a published number longs pay shorts, typically positive in bull markets.

This pulls the real numbers and reports them honestly:
  * current funding across the liquid perp universe (annualized), and
  * the REALIZED ~90-day average funding APR for the majors (the number that matters,
    since a single 8h reading is noise),
then nets out trading fees and states the risks plainly. No position is taken; this
is research, same test-before-trust bar as everything else.

Data: Binance USDⓈ-M futures (deepest funding history, public API). The venue that
would actually FIT this app's non-custodial model is an on-chain perp DEX
(Hyperliquid) — we also probe its funding to confirm it's in the same ballpark.
"""

from __future__ import annotations

import json
import os
import ssl
import statistics
import urllib.request

_CA = "/root/.ccr/ca-bundle.crt"


def _ctx():
    return ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else None


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
        return json.loads(r.read())


def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
        return json.loads(r.read())


FUND_PER_DAY = 3           # OKX/most venues fund every 8h
FEE_ROUNDTRIP = 0.0016     # ~4 legs (spot in/out + perp in/out) × ~0.04% taker ≈ 0.16%


def hl_cross_section():
    """Current funding across Hyperliquid's perp universe (the non-custodial-fit venue).
    HL funds HOURLY, so annualize ×24×365."""
    try:
        meta, ctxs = _post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
        rows = []
        for a, c in zip(meta["universe"], ctxs):
            fr = float(c.get("funding") or 0)
            rows.append((a["name"], fr * 24 * 365 * 100))
        rows.sort(key=lambda r: r[1], reverse=True)
        print("=== Hyperliquid current funding, annualized (short perp earns the + side) ===")
        print("  highest payers:", ", ".join(f"{s} {a:+.0f}%" for s, a in rows[:6]))
        print("  negative (you'd PAY):", ", ".join(f"{s} {a:+.0f}%" for s, a in rows[-4:]))
        mj = {s: a for s, a in rows}
        print("  majors:", ", ".join(f"{m} {mj.get(m,0):+.0f}%" for m in ("BTC", "ETH", "SOL")))
    except Exception as e:  # noqa: BLE001
        print("  Hyperliquid cross-section failed:", str(e)[:70])


def okx_realized_apr(inst, periods=270):   # ~90 days × 3/day (8h)
    """OKX realized funding history -> annualized APR + % positive."""
    d = _get(f"https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&limit=100")
    rates = [float(x["realizedRate"]) for x in d.get("data", [])]
    # OKX caps history at 100/call; page back a couple times for ~90d
    before = d.get("data", [])[-1]["fundingTime"] if d.get("data") else None
    for _ in range(2):
        if not before:
            break
        d2 = _get(f"https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&before={before}&limit=100")
        more = d2.get("data", [])
        if not more:
            break
        rates += [float(x["realizedRate"]) for x in more]
        before = more[-1]["fundingTime"]
    if not rates:
        return None
    apr = statistics.mean(rates) * FUND_PER_DAY * 365 * 100
    pos = sum(1 for r in rates if r > 0) / len(rates)
    return apr, pos, len(rates)


def main():
    hl_cross_section()
    print("\n=== OKX realized ~90d average funding APR (the honest number) ===")
    print(f"{'coin':<6}{'grossAPR':>10}{'netAPR*':>10}{'% periods +':>13}")
    for inst in ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
                 "BNB-USDT-SWAP", "XRP-USDT-SWAP", "DOGE-USDT-SWAP"):
        try:
            r = okx_realized_apr(inst)
        except Exception as e:  # noqa: BLE001
            print(f"{inst.split('-')[0]:<6}  (failed: {str(e)[:40]})"); continue
        if r:
            apr, pos, n = r
            net = apr - FEE_ROUNDTRIP * 12 * 100      # ~monthly hedge rebalance fees
            print(f"{inst.split('-')[0]:<6}{apr:>9.1f}%{net:>9.1f}%{pos*100:>11.0f}%  (n={n})")
    print("\n* net assumes ~monthly hedge rebalance fees; real drags: spot-perp execution"
          " spread and funding turning NEGATIVE in bears.")
    print("RISKS (why this isn't free money): needs a PERP venue (on-chain perp DEX like"
          " Hyperliquid fits our non-custodial model; a CEX is custodial); the short leg can"
          " be LIQUIDATED on a sharp rip if under-collateralized; venue/counterparty risk;"
          " funding flips negative in downturns; a DIFFERENT architecture than our spot flow.")


if __name__ == "__main__":
    main()
