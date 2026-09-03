"""tradebot: asset-agnostic crypto day/swing trading framework.

Composite technical-signal engine + backtester + risk management + paper
execution, for any coin with public OHLCV. Long/flat spot only. Paper trading by
default; no live-order or key-custody path ships enabled. The AMPL rebase logic
from the original project lives on as an optional plugin (see tradebot/plugins).
"""

__version__ = "0.2.0"
