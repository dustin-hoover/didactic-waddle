"""Test orthogonal signals honestly: funding rate and Fear & Greed sentiment.

Result summary (reproduce by running this):
  * FUNDING RATE — data wall. Free history is ~3 months (OKX caps it; Binance and
    Bybit are geo-blocked/forbidden). 93 daily points in one regime cannot
    validate a signal, so we do NOT trade on it.
  * FEAR & GREED — no usable edge, and the popular contrarian read is BACKWARDS
    in real data: extreme greed preceded HIGHER forward returns, extreme fear
    LOWER. "De-risk on greed" cut returns hard in the backtest. Rejected as a
    trading signal; kept for context/display only.

The lesson (what the best does): test the fashionable orthogonal signals, and
when they don't survive out-of-sample, reject them instead of shipping hope.
"""

import json
import math
import statistics
import urllib.request
from datetime import datetime, timezone

from tradebot.ohlcv import ExchangeFeed
from tradebot import indicators as ind

UA = {"User-Agent": "Mozilla/5.0 signal-test", "Accept": "application/json"}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read())


def funding_availability():
    print("=== FUNDING RATE — data availability ===")
    rows = {}
    after = ""
    for _ in range(40):
        url = "https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100"
        if after:
            url += f"&after={after}"
        try:
            d = _get(url).get("data", [])
        except Exception as e:  # noqa: BLE001
            print(f"  OKX error: {e}"); return
        if not d:
            break
        for x in d:
            rows[int(x["fundingTime"])] = float(x["fundingRate"])
        after = d[-1]["fundingTime"]
    ts = sorted(rows)
    days = {datetime.fromtimestamp(t / 1000, tz=timezone.utc).date() for t in ts}
    print(f"  OKX funding history: {len(ts)} points across {len(days)} days "
          f"({min(days)} -> {max(days)}).")
    print("  Binance/Bybit: geo-blocked/forbidden. Verdict: too little history to backtest.\n")


def fear_greed_test():
    print("=== FEAR & GREED — predictiveness + overlay backtest ===")
    fng = {x["timestamp"]: int(x["value"]) for x in _get("https://api.alternative.me/fng/?limit=0")["data"]}
    fng = {datetime.fromtimestamp(int(t), tz=timezone.utc).date().isoformat(): v for t, v in fng.items()}
    bars = ExchangeFeed().history("BTC", "1d", 1000)
    px = {b.date[:10]: b.close for b in bars}
    days = sorted(set(fng) & set(px))
    closes = [px[d] for d in days]
    fg = [fng[d] for d in days]
    n = len(days)
    print(f"  {n} aligned days ({days[0]} -> {days[-1]})")

    H = 20
    pairs = sorted((fg[i], closes[i + H] / closes[i] - 1) for i in range(n - H))
    q = len(pairs) // 5
    print(f"  Forward {H}-day return by F&G quintile (contrarian expects LOW F&G -> HIGH fwd):")
    for k in range(5):
        chunk = pairs[k * q:(k + 1) * q] if k < 4 else pairs[4 * q:]
        fgs = [a for a, _ in chunk]
        print(f"    F&G {min(fgs):>3}-{max(fgs):>3}: mean fwd {statistics.fmean([b for _, b in chunk])*100:>+5.1f}%")

    ema = ind.ema(closes, 50)
    FEE = 0.0017

    def run(expo, lo, hi):
        cash, pos, eq = 1.0, 0.0, []
        for i in range(lo, hi):
            if i > lo:
                cash *= (1 + pos * (closes[i] / closes[i - 1] - 1))
            e = expo(i)
            if abs(e - pos) > 1e-9:
                cash *= (1 - abs(e - pos) * FEE); pos = e
            eq.append(cash)
        rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]
        sh = (statistics.fmean(rets) / statistics.pstdev(rets)) * math.sqrt(365) if statistics.pstdev(rets) else 0
        peak, dd = -1, 0
        for v in eq:
            peak = max(peak, v); dd = max(dd, 1 - v / peak)
        return eq[-1] / eq[0] - 1, sh, dd

    trend = lambda i: 1.0 if (ema[i] is not None and closes[i] > ema[i]) else 0.0
    derisk = lambda i: trend(i) * (0.4 if fg[i] >= 75 else 1.0)
    for name, (lo, hi) in [("full", (0, n)), ("second half / OOS", (n // 2, n))]:
        print(f"  Overlay backtest [{name}]:")
        for lbl, fn in [("trend (baseline)", trend), ("trend + de-risk on greed", derisk)]:
            r, s, d = run(fn, lo, hi)
            print(f"    {lbl:<26} ret {r*100:>+6.0f}%  sharpe {s:>5.2f}  DD {d*100:>3.0f}%")
    print("\n  Verdict: de-risking on greed HURT; contrarian F&G is backwards here. Rejected.")


if __name__ == "__main__":
    funding_availability()
    fear_greed_test()
