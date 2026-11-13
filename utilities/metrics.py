"""Performance metrics, all expressed as percentages."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .domain import Position
from .engine import BacktestResult


@dataclass(frozen=True)
class Metrics:
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    annual_volatility_pct: float
    days_growth: int
    days_defensive: int
    trade_count: int


def compute_metrics(result: BacktestResult) -> Metrics:
    equity = result.equity
    track = np.r_[1.0, equity]
    drawdown = track / np.maximum.accumulate(track) - 1
    years = max((result.dates[-1] - result.dates[0]).days / 365.25, 1 / 365.25)
    daily = np.diff(equity) / equity[:-1]
    vol = float(np.std(daily, ddof=1) * np.sqrt(252) * 100) if len(daily) > 1 else np.nan
    return Metrics(
        total_return_pct=round(result.total_return * 100, 2),
        cagr_pct=round((equity[-1] ** (1 / years) - 1) * 100, 2),
        max_drawdown_pct=round(float(drawdown.min()) * 100, 2),
        annual_volatility_pct=round(vol, 2),
        days_growth=result.positions.count(Position.GROWTH),
        days_defensive=result.positions.count(Position.DEFENSIVE),
        trade_count=len(result.trades),
    )
