"""Pluggable strategies. Add a new rule by subclassing Strategy."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from .domain import ParameterSet, Position
from .market_data import MarketData


class Strategy(ABC):
    """Decides tomorrow-open position from information known at today's close.

    Every run starts in CASH on an observation day; the first decision
    (from day 0's close) executes at day 1's open."""

    def prepare(self, market: MarketData) -> None:
        """Optional precomputation before the daily loop."""

    @abstractmethod
    def decide(self, signal_idx: int, position: Position,
               growth_entry_idx: int | None) -> Position:
        """Return the position to hold from the open of day signal_idx + 1."""


class BuyAndHold(Strategy):
    def decide(self, signal_idx, position, growth_entry_idx):
        return Position.DEFENSIVE


class BuyAndHoldGrowth(Strategy):
    def decide(self, signal_idx, position, growth_entry_idx):
        return Position.GROWTH


class VixRotation(Strategy):
    """CASH -> GROWTH if signal > buy, otherwise DEFENSIVE.
    DEFENSIVE -> GROWTH when signal > buy; GROWTH -> DEFENSIVE when
    signal < sell AND the signal date is at least min_hold_months after the
    latest GROWTH entry. Early low signals are ignored, not deferred."""

    def __init__(self, params: ParameterSet):
        self.params = params
        self._signal: np.ndarray | None = None
        self._unlock_idx: np.ndarray | None = None

    def prepare(self, market: MarketData) -> None:
        self._signal = market.signal
        self._unlock_idx = unlock_indices(market.dates, self.params.min_hold_months)

    def decide(self, signal_idx, position, growth_entry_idx):
        value = self._signal[signal_idx]
        if position is not Position.GROWTH and value > self.params.buy:
            return Position.GROWTH
        if position is Position.CASH:
            return Position.DEFENSIVE
        if (position is Position.GROWTH and value < self.params.sell
                and growth_entry_idx is not None
                and signal_idx >= self._unlock_idx[growth_entry_idx]):
            return Position.DEFENSIVE
        return position


def unlock_indices(dates: pd.DatetimeIndex, months: int) -> np.ndarray:
    """For each entry day i, the first index whose date >= date[i] + months."""
    targets = dates + pd.DateOffset(months=months)
    return np.searchsorted(dates.values, targets.values, side='left')
