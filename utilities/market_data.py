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
    """Download adjusted prices: Taiwan codes from FinMind, others from Yahoo
    Finance. Nothing is written to disk."""
    import yfinance as yf

    def history(ticker: str) -> pd.DataFrame:
        if is_taiwan(ticker):
            hist = taiwan_history(ticker, start, end)
        else:
            hist = yf.Ticker(ticker).history(start=start, end=end, interval='1d',
                                             auto_adjust=True, actions=False)
            if hist is None or hist.empty:
                raise RuntimeError(f'No historical prices for {ticker}.')
        hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
        # Sources report some missing prices as 0; treat those days as missing.
        hist = hist[(hist[['Open', 'Close']] > 0).all(axis=1)]
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


def is_taiwan(ticker: str) -> bool:
    """Taiwan codes start with a digit (0050, 00631L, 2330); US ones don't."""
    return ticker[:1].isdigit()


_FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'


def _finmind(dataset: str, ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    import os
    import requests

    params = {'dataset': dataset, 'data_id': ticker, 'start_date': start}
    if end:
        params['end_date'] = end
    headers = {}
    if token := os.environ.get('FINMIND_TOKEN'):
        headers['Authorization'] = f'Bearer {token}'
    resp = requests.get(_FINMIND_URL, params=params, headers=headers, timeout=60)
    body = resp.json()
    if resp.status_code != 200:
        raise RuntimeError(f'FinMind {dataset} for {ticker}: {body.get("msg")}')
    return pd.DataFrame(body.get('data', []))


def taiwan_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Listed or OTC Taiwan prices from FinMind, back-adjusted for dividends and splits.

    Each ex-dividend / split event scales all earlier prices by
    after_price / before_price, approximating total return with reinvestment.
    """
    raw = _finmind('TaiwanStockPrice', ticker, start, end)
    if raw.empty:
        raise RuntimeError(f'No historical prices for {ticker}.')
    hist = raw.rename(columns={'open': 'Open', 'close': 'Close'})
    hist.index = pd.to_datetime(hist['date'])
    hist = hist[['Open', 'Close']].astype(float)

    # Events after `end` don't matter; earlier ones only matter after `start`.
    events = pd.concat([_finmind(ds, ticker, start)
                        for ds in ('TaiwanStockDividendResult', 'TaiwanStockSplitPrice')])
    if not events.empty:
        for _, ev in events.iterrows():
            before, after = float(ev['before_price']), float(ev['after_price'])
            if before > 0 and after > 0:
                hist.loc[hist.index < pd.Timestamp(ev['date'])] *= after / before
    return hist


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
