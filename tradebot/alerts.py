"""Trade alerts — so an opportunity never slips past you.

Watch-and-execute done right: the bot runs the same reliable function every
candle and, when the actionable state *changes* (flat→long, long→flat, a stop,
a profit-skim), it fires a notification telling you exactly what to do. You keep
custody and place the trade; the bot just makes sure you never miss the signal.

Push delivery uses ntfy.sh — free, no account: pick a hard-to-guess topic, POST
to https://ntfy.sh/<topic>, and subscribe to that topic in the ntfy phone app.
State is persisted so you only get alerted on a genuine change, not every tick.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from .config import BotConfig, StrategyConfig
from .ohlcv import ExchangeFeed
from .signals import CompositeStrategy, TrendFilterStrategy


@dataclass
class Alert:
    symbol: str
    action: str        # BUY / EXIT / HOLD / (info)
    urgency: str       # high / normal / low
    message: str


def _state_path(symbol: str, interval: str) -> str:
    return f"data/alert_state_{symbol}_{interval}.json"


def _load_state(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


def push_ntfy(topic: str, title: str, message: str, priority: str = "default") -> bool:
    """Send a push via ntfy.sh. Returns True on success. Never raises."""
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=message.encode(),
            headers={"Title": title, "Priority": priority, "Tags": "chart_with_upwards_trend"})
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:  # noqa: BLE001
        return False


def check(symbol: str, interval: str = "4h", style: str = "swing",
          feed: Optional[ExchangeFeed] = None) -> Alert:
    """Compare the current regime to the last seen state; emit an alert on change."""
    feed = feed or ExchangeFeed()
    bars = feed.history(symbol, interval, 400)
    trend = TrendFilterStrategy(style).generate(bars)
    comp = CompositeStrategy(style).generate(bars)
    now_long = trend.target_exposure > 0
    price = bars[-1].close

    path = _state_path(symbol, interval)
    state = _load_state(path)
    was_long = state.get("long")

    if was_long is None:
        action, urgency = "HOLD", "low"
        msg = f"{symbol} {interval}: tracking started — currently {'LONG' if now_long else 'FLAT/cash'} @ ${price:,.2f}"
    elif now_long and not was_long:
        action, urgency = "BUY", "high"
        msg = (f"{symbol} {interval}: trend flipped UP → BUY @ ${price:,.2f}. "
               f"Conviction {comp.score:+.2f}. Place a spot buy in your wallet.")
    elif was_long and not now_long:
        action, urgency = "EXIT", "high"
        msg = (f"{symbol} {interval}: trend broke DOWN → EXIT to cash/stable @ ${price:,.2f}. "
               f"Close the position in your wallet.")
    else:
        action, urgency = "HOLD", "low"
        msg = f"{symbol} {interval}: no change — {'holding LONG' if now_long else 'in cash'} @ ${price:,.2f}"

    state["long"] = now_long
    state["price"] = price
    _save_state(path, state)
    return Alert(symbol, action, urgency, msg)


def check_many(symbols: List[str], interval: str, style: str,
               ntfy_topic: Optional[str] = None) -> List[Alert]:
    feed = ExchangeFeed()
    out: List[Alert] = []
    for sym in symbols:
        try:
            a = check(sym, interval, style, feed)
        except Exception as e:  # noqa: BLE001
            a = Alert(sym, "ERROR", "low", f"{sym}: {str(e)[:80]}")
        out.append(a)
        if ntfy_topic and a.action in ("BUY", "EXIT"):
            push_ntfy(ntfy_topic, f"{a.action} {a.symbol}", a.message,
                      priority="high" if a.urgency == "high" else "default")
    return out
