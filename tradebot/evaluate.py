"""Evaluation harness (Phase 1.2) — the referee that comes before the players.

A backtest number means nothing on its own. With enough configs tried, SOMETHING will
look great by luck. This module measures whether an apparent edge survives honest
scrutiny, using only the stdlib so it runs anywhere:

  * walk-forward splits (expanding train, fixed forward test);
  * CPCV — combinatorial purged cross-validation, with purge + embargo around every
    test block so overlapping labels can't leak train into test;
  * the Deflated Sharpe Ratio (Bailey & López de Prado) — the probability the observed
    Sharpe is real once you account for how many trials were run and for non-normal
    returns. DSR < 0.5 means "indistinguishable from the luckiest of N random tries";
  * PBO via CSCV — the probability of backtest overfitting: how often the in-sample
    best config underperforms the median out-of-sample. ~0.5 or above = overfit;
  * a stationary block bootstrap — resampling blocks (preserving autocorrelation) to
    get DISTRIBUTIONS of CAGR, max drawdown and ruin probability, not point estimates;
  * benchmarks every result is reported against: BTC buy-and-hold and a BTC 200-day
    SMA rule, net of costs.

Everything operates on plain per-period return series (lists of floats), so any
strategy — trend, carry, a bag — can be judged on equal footing. Nothing here trades.
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

_EULER = 0.5772156649015329            # Euler-Mascheroni constant (for E[max Sharpe])


# --------------------------------------------------------------------------- #
# Normal distribution helpers (stdlib only)                                   #
# --------------------------------------------------------------------------- #
def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation; |err| < 1.2e-9)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# --------------------------------------------------------------------------- #
# Return-series statistics                                                    #
# --------------------------------------------------------------------------- #
def _moments(returns: Sequence[float]) -> Tuple[float, float, float, float]:
    """(mean, std, skew, kurtosis) — population std, full (non-excess) kurtosis."""
    n = len(returns)
    if n < 2:
        return (returns[0] if returns else 0.0, 0.0, 0.0, 3.0)
    mu = statistics.fmean(returns)
    var = statistics.pvariance(returns, mu)
    sd = math.sqrt(var)
    if sd == 0:
        return (mu, 0.0, 0.0, 3.0)
    m3 = sum((r - mu) ** 3 for r in returns) / n
    m4 = sum((r - mu) ** 4 for r in returns) / n
    return (mu, sd, m3 / sd ** 3, m4 / sd ** 4)


def sharpe(returns: Sequence[float], periods_per_year: float = 365.0) -> float:
    """Annualized Sharpe of a per-period return series (rf=0)."""
    mu, sd, _, _ = _moments(returns)
    return 0.0 if sd == 0 else (mu / sd) * math.sqrt(periods_per_year)


def sharpe_per_period(returns: Sequence[float]) -> float:
    mu, sd, _, _ = _moments(returns)
    return 0.0 if sd == 0 else mu / sd


def probabilistic_sharpe_ratio(returns: Sequence[float], sr_benchmark: float = 0.0) -> float:
    """PSR: P(true per-period Sharpe > sr_benchmark), correcting for skew/kurtosis.
    sr_benchmark is a PER-PERIOD Sharpe threshold."""
    n = len(returns)
    if n < 2:
        return 0.5
    _, sd, skew, kurt = _moments(returns)
    if sd == 0:
        return 0.5
    sr = sharpe_per_period(returns)
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr))
    return norm_cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom)


def expected_max_sharpe(n_trials: int, trial_sharpe_std: float) -> float:
    """E[max per-period Sharpe] over `n_trials` independent strategies whose Sharpes have
    std `trial_sharpe_std` — the benchmark the winner must beat (Bailey & LdP)."""
    if n_trials < 1 or trial_sharpe_std <= 0:
        return 0.0
    n = max(2, n_trials)
    return trial_sharpe_std * ((1 - _EULER) * norm_ppf(1 - 1.0 / n)
                               + _EULER * norm_ppf(1 - 1.0 / (n * math.e)))


def deflated_sharpe_ratio(returns: Sequence[float], n_trials: int,
                          trial_sharpe_std: Optional[float] = None) -> float:
    """DSR: PSR evaluated against the expected-max Sharpe of `n_trials` tries.

    `trial_sharpe_std` is the std of per-period Sharpe across the trials you ran; when
    unknown, a conservative default (0.5 annualized → per-period) inflates the hurdle.
    DSR < 0.5 means the result is not distinguishable from the best of random luck."""
    if trial_sharpe_std is None:
        trial_sharpe_std = 0.5 / math.sqrt(365.0)        # ~0.5 annualized, conservative
    sr0 = expected_max_sharpe(n_trials, trial_sharpe_std)
    return probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)


# --------------------------------------------------------------------------- #
# Equity-curve statistics                                                     #
# --------------------------------------------------------------------------- #
def equity_curve(returns: Sequence[float], start: float = 1.0) -> List[float]:
    eq, v = [], start
    for r in returns:
        v *= (1.0 + r)
        eq.append(v)
    return eq


def max_drawdown(returns: Sequence[float]) -> float:
    peak, mdd, v = -math.inf, 0.0, 1.0
    for r in returns:
        v *= (1.0 + r)
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def cagr(returns: Sequence[float], periods_per_year: float = 365.0) -> float:
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= (1.0 + r)
    if total <= 0:
        return -1.0
    return total ** (periods_per_year / len(returns)) - 1.0


# --------------------------------------------------------------------------- #
# Splitters: walk-forward and CPCV                                            #
# --------------------------------------------------------------------------- #
def walk_forward_splits(n: int, train_min: int, test_size: int,
                        step: Optional[int] = None) -> List[Tuple[List[int], List[int]]]:
    """Expanding-train / fixed-test walk-forward over indices [0, n)."""
    step = step or test_size
    out = []
    start = train_min
    while start + test_size <= n:
        train = list(range(0, start))
        test = list(range(start, start + test_size))
        out.append((train, test))
        start += step
    return out


def cpcv_splits(n: int, n_groups: int, k_test: int, purge: int = 1,
                embargo: int = 1) -> List[Tuple[List[int], List[int]]]:
    """Combinatorial purged cross-validation splits over [0, n).

    Partition the timeline into `n_groups` contiguous groups; every combination of
    `k_test` groups forms the test set. Train is everything else MINUS a `purge` band
    adjacent to each test group and an `embargo` band after it, so a label that spans
    the boundary can't leak train knowledge into test."""
    if not (1 <= k_test < n_groups) or n_groups > n:
        raise ValueError("need 1 <= k_test < n_groups <= n")
    bounds = [(round(i * n / n_groups), round((i + 1) * n / n_groups)) for i in range(n_groups)]
    out = []
    for combo in combinations(range(n_groups), k_test):
        test_idx: List[int] = []
        for g in combo:
            test_idx.extend(range(*bounds[g]))
        test_set = set(test_idx)
        blocked = set(test_idx)
        for g in combo:
            lo, hi = bounds[g]
            for j in range(max(0, lo - purge), lo):
                blocked.add(j)
            for j in range(hi, min(n, hi + embargo)):
                blocked.add(j)
        train_idx = [i for i in range(n) if i not in blocked and i not in test_set]
        out.append((sorted(train_idx), sorted(test_idx)))
    return out


# --------------------------------------------------------------------------- #
# PBO via CSCV                                                                 #
# --------------------------------------------------------------------------- #
@dataclass
class PBOResult:
    pbo: float                    # probability of backtest overfitting (0..1)
    n_combinations: int
    logits: List[float]
    median_logit: float


def pbo_cscv(returns_matrix: Sequence[Sequence[float]], n_blocks: int = 16,
             metric: Optional[Callable[[Sequence[float]], float]] = None) -> PBOResult:
    """Probability of backtest overfitting (Bailey et al., CSCV).

    `returns_matrix` is N strategies x T periods. Split T into `n_blocks` equal blocks;
    for each way to split the blocks into equal IS/OOS halves, pick the IS-best strategy
    and record its relative rank OOS. PBO is the fraction of splits where that strategy
    lands in the OOS BOTTOM half (logit <= 0). ~0.5 or higher = the selection process
    overfits. Pure-noise strategies give PBO around or above 0.5; a real persistent edge
    gives PBO near 0."""
    metric = metric or sharpe_per_period
    n_strat = len(returns_matrix)
    T = len(returns_matrix[0]) if n_strat else 0
    if n_strat < 2 or T < n_blocks or n_blocks % 2 != 0:
        raise ValueError("need >=2 strategies, T>=n_blocks, and an even n_blocks")
    bnd = [(round(i * T / n_blocks), round((i + 1) * T / n_blocks)) for i in range(n_blocks)]

    def slice_metric(rows_cols: List[int]) -> List[float]:
        cols: List[int] = []
        for b in rows_cols:
            cols.extend(range(*bnd[b]))
        return [metric([returns_matrix[s][c] for c in cols]) for s in range(n_strat)]

    logits: List[float] = []
    half = n_blocks // 2
    for is_blocks in combinations(range(n_blocks), half):
        oos_blocks = [b for b in range(n_blocks) if b not in is_blocks]
        is_perf = slice_metric(list(is_blocks))
        oos_perf = slice_metric(oos_blocks)
        best = max(range(n_strat), key=lambda s: is_perf[s])
        # relative rank of the IS-best among OOS performances, in (0,1)
        rank = sum(1 for s in range(n_strat) if oos_perf[s] <= oos_perf[best])
        omega = rank / (n_strat + 1)
        omega = min(1 - 1e-6, max(1e-6, omega))
        logits.append(math.log(omega / (1 - omega)))
    pbo = sum(1 for la in logits if la <= 0) / len(logits)
    return PBOResult(pbo=pbo, n_combinations=len(logits), logits=logits,
                     median_logit=statistics.median(logits))


# --------------------------------------------------------------------------- #
# Stationary block bootstrap                                                   #
# --------------------------------------------------------------------------- #
def stationary_block_bootstrap(returns: Sequence[float], mean_block: float,
                               length: Optional[int] = None,
                               rng: Optional[random.Random] = None) -> List[float]:
    """One Politis-Romano stationary-bootstrap resample (geometric block lengths with
    mean `mean_block`), preserving short-range autocorrelation."""
    rng = rng or random
    n = len(returns)
    if n == 0:
        return []
    length = length or n
    p = 1.0 / max(1.0, mean_block)
    out: List[float] = []
    i = rng.randrange(n)
    while len(out) < length:
        out.append(returns[i])
        if rng.random() < p:
            i = rng.randrange(n)
        else:
            i = (i + 1) % n
    return out


@dataclass
class BootstrapDistribution:
    n_paths: int
    cagr: Dict[str, float]
    max_drawdown: Dict[str, float]
    ruin_prob: float              # fraction of paths breaching the ruin drawdown
    ruin_dd: float


def _pctiles(xs: List[float]) -> Dict[str, float]:
    s = sorted(xs)
    def q(p):
        if not s:
            return 0.0
        return s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))]
    return {"p05": q(0.05), "p25": q(0.25), "median": q(0.50),
            "p75": q(0.75), "p95": q(0.95), "mean": statistics.fmean(s) if s else 0.0}


def bootstrap_distribution(returns: Sequence[float], n_paths: int = 1000,
                           mean_block: float = 10.0, periods_per_year: float = 365.0,
                           ruin_dd: float = 0.5, seed: int = 0) -> BootstrapDistribution:
    """Distributions of CAGR, max drawdown and ruin probability over bootstrap paths."""
    rng = random.Random(seed)
    cagrs, dds = [], []
    ruined = 0
    for _ in range(n_paths):
        path = stationary_block_bootstrap(returns, mean_block, rng=rng)
        cagrs.append(cagr(path, periods_per_year))
        dd = max_drawdown(path)
        dds.append(dd)
        if dd >= ruin_dd:
            ruined += 1
    return BootstrapDistribution(
        n_paths=n_paths, cagr=_pctiles(cagrs), max_drawdown=_pctiles(dds),
        ruin_prob=ruined / n_paths if n_paths else 0.0, ruin_dd=ruin_dd)


# --------------------------------------------------------------------------- #
# Benchmarks                                                                   #
# --------------------------------------------------------------------------- #
def returns_from_closes(closes: Sequence[float]) -> List[float]:
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def buy_hold_returns(closes: Sequence[float]) -> List[float]:
    return returns_from_closes(closes)


def sma_rule_returns(closes: Sequence[float], window: int = 200,
                     fee_frac: float = 0.001) -> List[float]:
    """Long BTC only while close > its `window`-SMA, else flat. Charges `fee_frac` on
    each state change. The plain, honest trend benchmark every edge must beat."""
    out: List[float] = []
    pos = 0
    for i in range(1, len(closes)):
        if i >= window:
            sma = statistics.fmean(closes[i - window:i])
            desired = 1 if closes[i - 1] > sma else 0
        else:
            desired = 0
        r = (closes[i] / closes[i - 1] - 1.0) * pos
        if desired != pos:
            r -= fee_frac
        out.append(r)
        pos = desired
    return out


# --------------------------------------------------------------------------- #
# Trial registry                                                               #
# --------------------------------------------------------------------------- #
class TrialRegistry:
    """Append-only log of every evaluated strategy trial (docs/trials.jsonl). The DSR
    needs an honest count of how many configurations were tried — this is that count,
    so it can't be quietly forgotten. Each trial is pinned to a config hash and the git
    commit it ran at, so a number is always traceable to frozen code + config."""

    def __init__(self, path: str = "docs/trials.jsonl"):
        self.path = path

    def record(self, config_hash: str, git_commit: str, metrics: Dict,
               note: str = "") -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        row = {"config_hash": config_hash, "git_commit": git_commit,
               "metrics": metrics, "note": note}
        with open(self.path, "a") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    def all(self) -> List[dict]:
        out: List[dict] = []
        try:
            with open(self.path) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            return []
        return out

    def count(self) -> int:
        return len(self.all())

    def distinct_configs(self) -> int:
        return len({r.get("config_hash") for r in self.all()})
