"""Daily simulation. Equity is a growth index starting at 1.0 (no capital)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .domain import Position, Trade
from .market_data import MarketData
from .strategies import Strategy


@dataclass(frozen=True)
class BacktestResult:
    dates: pd.DatetimeIndex
    equity: np.ndarray            # 1.0 == starting value
    positions: list[Position]
    trades: list[Trade]
    signal: np.ndarray

    @property
    def total_return(self) -> float:
        return float(self.equity[-1] - 1.0)


def run_backtest(market: MarketData, strategy: Strategy, fee: float) -> BacktestResult:
    """Signals use day i-1 close; trades execute at day i open; fee per side.
    Day 0 is held in CASH so every strategy starts trading on the same open."""
    if not 0 <= fee < 1:
        raise ValueError('Fee must be in the range [0, 1).')
    strategy.prepare(market)
    dates = market.dates
    n = len(market)
    equity = np.empty(n)
    positions: list[Position] = []
    trades: list[Trade] = []

    # Day 0 is an observation day: no prior signal exists yet.
    position = Position.CASH
    value = 1.0
    entry_idx = None
    equity[0] = value
    positions.append(position)

    for i in range(1, n):
        old = position
        if old is not Position.CASH:
            value *= market.open(old)[i] / market.close(old)[i - 1]

        position = strategy.decide(i - 1, old, entry_idx)
        if position is not old:
            value *= (1 - fee) if old is Position.CASH else (1 - fee) ** 2
            entry_idx = i if position is Position.GROWTH else None
            trades.append(Trade(_d(dates[i - 1]), _d(dates[i]),
                                round(float(market.signal[i - 1]), 3),
                                old, position, _pct(value)))

        if position is not Position.CASH:
            value *= market.close(position)[i] / market.open(position)[i]
        equity[i] = value
        positions.append(position)

    return BacktestResult(dates, equity, positions, trades, market.signal)


def _d(ts) -> str:
    return str(pd.Timestamp(ts).date())


def _pct(value: float) -> float:
    return round((value - 1) * 100, 4)
