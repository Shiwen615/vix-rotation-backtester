"""Grid search over ParameterSets, ranked by total return."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from .domain import ParameterSet
from .engine import run_backtest
from .market_data import MarketData
from .strategies import BuyAndHold, VixRotation


@dataclass(frozen=True)
class Range:
    start: float
    stop: float
    step: float

    def values(self) -> list[float]:
        if self.step <= 0:
            raise ValueError('Step must be positive.')
        return [round(v, 6) for v in np.arange(self.start, self.stop + self.step / 2, self.step)]


@dataclass(frozen=True)
class ParameterGrid:
    buy: Range
    sell: Range
    min_hold_months: Range

    def __iter__(self) -> Iterator[ParameterSet]:
        for b in self.buy.values():
            for s in self.sell.values():
                if b <= s:
                    continue
                for m in self.min_hold_months.values():
                    yield ParameterSet(b, s, int(m))

    def __len__(self) -> int:
        return sum(1 for _ in self)


ProgressFn = Callable[[int, int], None]


def optimize(market: MarketData, grid: ParameterGrid, fee: float,
             in_sample_ratio: float | None = None,
             progress: ProgressFn | None = None) -> pd.DataFrame:
    """Run every ParameterSet. With in_sample_ratio, rank on the first part
    and report the untouched remainder as out-of-sample."""
    train, test = _split(market, in_sample_ratio)
    bench_train = run_backtest(train, BuyAndHold(), fee).total_return
    bench_test = run_backtest(test, BuyAndHold(), fee).total_return if test is not None else None

    params = list(grid)
    rows = []
    for k, p in enumerate(params, 1):
        r = run_backtest(train, VixRotation(p), fee)
        row = {
            'buy': p.buy, 'sell': p.sell, 'min_hold_months': p.min_hold_months,
            'total_return_pct': r.total_return * 100,
            'excess_vs_benchmark_pp': (r.total_return - bench_train) * 100,
            'trades': len(r.trades),
        }
        if test is not None:
            oos = run_backtest(test, VixRotation(p), fee).total_return
            row['oos_return_pct'] = oos * 100
            row['oos_excess_pp'] = (oos - bench_test) * 100
        rows.append(row)
        if progress:
            progress(k, len(params))

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values('total_return_pct', ascending=False).reset_index(drop=True)


def _split(market: MarketData, ratio: float | None):
    if ratio is None:
        return market, None
    if not 0 < ratio < 1:
        raise ValueError('in_sample_ratio must be in (0, 1).')
    cut = int(len(market) * ratio)
    return market.slice(0, cut), market.slice(cut)
