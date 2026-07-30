"""Price data providers.

Pluggable so the same strategy/backtester code runs against a CSV file, a
synthetic series, or (later) a live feed. Live adapters are stubs on purpose:
wiring real API keys is a deliberate step the operator takes, not a default.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol


@dataclass(frozen=True)
class PriceBar:
    timestamp: str  # ISO date string.
    price: float  # AMPL/USD.


class PriceProvider(Protocol):
    def history(self) -> List[PriceBar]:
        ...

    def latest(self) -> PriceBar:
        ...


class CsvPriceProvider:
    """Reads a two-column CSV: timestamp,price."""

    def __init__(self, path: str):
        self.path = path
        self._bars: List[PriceBar] = []
        self._load()

    def _load(self) -> None:
        bars: List[PriceBar] = []
        with open(self.path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bars.append(PriceBar(row["timestamp"], float(row["price"])))
        if not bars:
            raise ValueError(f"No rows in {self.path}")
        self._bars = bars

    def history(self) -> List[PriceBar]:
        return list(self._bars)

    def latest(self) -> PriceBar:
        return self._bars[-1]


class SyntheticPriceProvider:
    """Generates a plausible mean-reverting-around-target AMPL series.

    For demos/tests only. Clearly NOT real market data.
    """

    def __init__(self, days: int = 365, target: float = 1.019, seed: int = 7):
        self.days = days
        self.target = target
        self.seed = seed
        self._bars = self._generate()

    def _generate(self) -> List[PriceBar]:
        rng = random.Random(self.seed)
        price = self.target
        bars: List[PriceBar] = []
        # Ornstein-Uhlenbeck-ish reversion to target with fat-ish tails.
        kappa, sigma = 0.05, 0.06
        from datetime import date, timedelta

        start = date(2023, 1, 1)
        for i in range(self.days):
            shock = rng.gauss(0, 1)
            # occasional regime jump
            jump = 0.0
            if rng.random() < 0.03:
                jump = rng.choice([-1, 1]) * rng.uniform(0.05, 0.20)
            price += kappa * (self.target - price) + sigma * price * shock + jump * price
            price = max(0.10, price)
            bars.append(PriceBar((start + timedelta(days=i)).isoformat(), round(price, 6)))
        return bars

    def history(self) -> List[PriceBar]:
        return list(self._bars)

    def latest(self) -> PriceBar:
        return self._bars[-1]


class LivePriceProvider:
    """Deprecated shim. Real feeds now live in ampl_bot.feeds.

    Use CoinGeckoFeed (history) or OnChainFeed (live spot) instead. This class
    forwards to them so older imports keep working.
    """

    def __init__(self, source: str = "coingecko"):
        self.source = source

    def _provider(self):
        from .feeds import CoinGeckoFeed, OnChainFeed

        return OnChainFeed() if self.source == "onchain" else CoinGeckoFeed()

    def history(self) -> List[PriceBar]:
        return self._provider().history()

    def latest(self) -> PriceBar:
        return self._provider().latest()


def write_csv(bars: Iterable[PriceBar], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price"])
        for b in bars:
            writer.writerow([b.timestamp, b.price])
