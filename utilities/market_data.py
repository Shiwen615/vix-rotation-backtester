"""Market data container and the yfinance loader (in-memory only)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .domain import Position, Universe

_COLUMNS = ('defensive_open', 'defensive_close', 'growth_open', 'growth_close', 'signal')


@dataclass(frozen=True)
class MarketData:
    """Aligned daily prices as numpy arrays for fast simulation."""
    dates: pd.DatetimeIndex
    defensive_open: np.ndarray
    defensive_close: np.ndarray
    growth_open: np.ndarray
    growth_close: np.ndarray
    signal: np.ndarray

    def __post_init__(self):
        if len(self.dates) < 2:
            raise ValueError('Need at least two trading days.')
        for name in _COLUMNS:
            arr = getattr(self, name)
            if len(arr) != len(self.dates):
                raise ValueError(f'{name} length mismatch.')
            if (arr <= 0).any():
                raise ValueError(f'Non-positive market data found: {name}')

    def __len__(self) -> int:
        return len(self.dates)

    def open(self, position: Position) -> np.ndarray:
        return self.defensive_open if position is Position.DEFENSIVE else self.growth_open

    def close(self, position: Position) -> np.ndarray:
        return self.defensive_close if position is Position.DEFENSIVE else self.growth_close

    def slice(self, start: int, stop: int | None = None) -> 'MarketData':
        return MarketData(self.dates[start:stop],
                          *(getattr(self, n)[start:stop] for n in _COLUMNS))

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> 'MarketData':
        """Build from a frame with columns named like _COLUMNS."""
        df = df.sort_index()
        return cls(pd.DatetimeIndex(df.index),
                   *(df[n].to_numpy(dtype=float) for n in _COLUMNS))


def fetch_market_data(universe: Universe, start: str, end: str) -> MarketData:
    """Download adjusted OHLC from Yahoo Finance. Nothing is written to disk."""
    import yfinance as yf

    def history(ticker: str) -> pd.DataFrame:
        hist = yf.Ticker(ticker).history(start=start, end=end, interval='1d',
                                         auto_adjust=True, actions=False)
        if hist is None or hist.empty:
            raise RuntimeError(f'No historical prices for {ticker}.')
        hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
        return hist.loc[~hist.index.duplicated(keep='last')].sort_index()

    defensive = history(universe.defensive)[['Open', 'Close']].rename(
        columns={'Open': 'defensive_open', 'Close': 'defensive_close'})
    growth = history(universe.growth)[['Open', 'Close']].rename(
        columns={'Open': 'growth_open', 'Close': 'growth_close'})
    signal = signal_series(universe.signal, lambda t: history(t)['Close'])

    # Only days both assets traded; signal forward-filled (never from the future).
    df = defensive.join(growth, how='inner')
    df = df.join(signal.reindex(df.index, method='ffill')).dropna()
    return MarketData.from_frame(df)


def parse_signal(expression: str) -> list[str]:
    """'^VIX' -> ['^VIX']; '^VIX/^VIX3M' -> ['^VIX', '^VIX3M']."""
    parts = [p.strip().upper() for p in expression.split('/')]
    if not 1 <= len(parts) <= 2 or not all(parts):
        raise ValueError(f'Signal must be TICKER or A/B, got {expression!r}.')
    return parts


def signal_series(expression: str, close_of) -> pd.Series:
    """Signal close series; a ratio uses only dates where both legs exist."""
    parts = parse_signal(expression)
    if len(parts) == 1:
        return close_of(parts[0]).rename('signal')
    num, den = (close_of(t) for t in parts)
    both = pd.concat([num, den], axis=1, join='inner').dropna()
    if both.empty:
        raise RuntimeError(f'No overlapping history for {expression}.')
    return (both.iloc[:, 0] / both.iloc[:, 1]).rename('signal')
