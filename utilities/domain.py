"""Core value types shared by every layer. No I/O, no pandas logic."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Position(str, Enum):
    CASH = 'CASH'
    GROWTH = 'GROWTH'
    DEFENSIVE = 'DEFENSIVE'


@dataclass(frozen=True)
class Universe:
    """Which tickers play each role."""
    defensive: str = 'QQQ'
    growth: str = 'TQQQ'
    signal: str = '^VIX'

    def label(self, position: Position) -> str:
        return {
            Position.CASH: 'CASH',
            Position.GROWTH: self.growth,
            Position.DEFENSIVE: self.defensive,
        }[position]


@dataclass(frozen=True)
class ParameterSet:
    buy: float
    sell: float
    min_hold_months: int

    def __post_init__(self):
        if self.buy <= self.sell:
            raise ValueError('Buy threshold must exceed sell threshold.')
        if isinstance(self.min_hold_months, bool) or self.min_hold_months < 0:
            raise ValueError('min_hold_months must be a nonnegative integer.')


@dataclass(frozen=True)
class Trade:
    signal_date: str
    trade_date: str
    signal_value: float
    sold: Position
    bought: Position
    return_after_trade_pct: float


@dataclass(frozen=True)
class SignalPreset:
    """A ready-made Signal definition with search ranges suited to its scale.
    `expression` is a ticker or a ratio 'A/B' of two tickers' closes."""
    label: str
    expression: str
    buy: tuple[float, float, float]    # from, to, step
    sell: tuple[float, float, float]
    step_min: float
    help: str = ''


SIGNAL_PRESETS: dict[str, SignalPreset] = {p.label: p for p in (
    SignalPreset('VIX level', '^VIX', (15, 35, 1), (10, 20, 1), 0.1,
                 'Absolute VIX close.'),
    SignalPreset('VIX term structure (VIX ÷ VIX3M)', '^VIX/^VIX3M',
                 (0.95, 1.15, 0.01), (0.80, 0.95, 0.01), 0.001,
                 'Above 1 = backwardation (short-term fear exceeds 3-month). '
                 '^VIX3M history starts Dec 2007.'),
    SignalPreset('Custom', '^VIX', (15, 35, 1), (10, 20, 1), 0.001,
                 'Any ticker, or a ratio written as A/B.'),
)}
