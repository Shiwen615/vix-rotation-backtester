"""Streamlit UI. Run: streamlit run app.py"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import pandas as pd
import streamlit as st

from utilities.charts import equity_figure, heatmap_figure
from utilities.domain import SIGNAL_PRESETS, ParameterSet, Universe
from utilities.engine import run_backtest
from utilities.market_data import MarketData, fetch_market_data
from utilities.metrics import compute_metrics
from utilities.optimizer import ParameterGrid, Range, optimize
from utilities.strategies import BuyAndHold, VixRotation

TOP_N = 10
PCT_DECIMALS = 1
EARLIEST_DATE = dt.date(1990, 1, 1)  # first ^VIX history
DEFAULT_LOOKBACK_YEARS = 10

st.set_page_config(page_title='VIX Rotation Backtester', layout='wide')
st.title('VIX Rotation Backtester')


@st.cache_data(show_spinner='Downloading prices…')
def load_market(defensive: str, growth: str, signal: str, start: str, end: str) -> MarketData:
    return fetch_market_data(Universe(defensive, growth, signal), start, end)


def range_input(label: str, start: float, stop: float, step: float, integer=False,
                step_min: float = 0.1, key: str = '') -> Range:
    """`key` scopes widget state, so switching Signal preset resets the defaults."""
    c1, c2, c3 = st.sidebar.columns(3)
    cast = int if integer else float
    fmt = None if integer else ('%.2f' if step_min < 0.1 else '%.1f')
    k = f'{label}{key}'
    s = c1.number_input(f'{label} from', value=cast(start), format=fmt, key=f'{k}a')
    e = c2.number_input('to', value=cast(stop), format=fmt, key=f'{k}b')
    p = c3.number_input('step', value=cast(step), min_value=cast(1 if integer else step_min),
                        format=fmt, key=f'{k}c')
    return Range(s, e, p)


def midpoint(bounds: tuple[float, float], step: float) -> float:
    """Range midpoint snapped to `step`, used as the Fixed-mode default."""
    return round(round(sum(bounds) / 2 / step) * step, 6)


def round_pct(df: pd.DataFrame) -> pd.DataFrame:
    """Display-only rounding of percentage columns to one decimal."""
    cols = [c for c in df.columns if c.endswith(('_pct', '_pp'))]
    return df.round({c: PCT_DECIMALS for c in cols})


# ---------- Sidebar inputs ----------
st.sidebar.header('Assets')
universe = Universe(
    defensive=st.sidebar.text_input('Defensive asset', 'QQQ').strip().upper(),
    growth=st.sidebar.text_input('Growth asset', 'TQQQ').strip().upper(),
    signal='',
)
preset = SIGNAL_PRESETS[st.sidebar.selectbox('Signal', list(SIGNAL_PRESETS),
                                             help='Each choice loads its own BUY/SELL ranges.')]
signal_expr = preset.expression
if preset.label == 'Custom':
    signal_expr = st.sidebar.text_input('Signal ticker or ratio A/B', preset.expression)
st.sidebar.caption(f'`{signal_expr.strip().upper()}` · {preset.help}')
universe = Universe(universe.defensive, universe.growth, signal_expr.strip().upper())
st.sidebar.header('Period & cost')
TODAY = dt.date.today()
# Explicit bounds: Streamlit otherwise limits picks to ±10 years of the default.
DEFAULT_START = (pd.Timestamp(TODAY) - pd.DateOffset(years=DEFAULT_LOOKBACK_YEARS)).date()
start = st.sidebar.date_input('Start', DEFAULT_START,
                              min_value=EARLIEST_DATE, max_value=TODAY,
                              help='Data starts at the earliest common date automatically.')
end = st.sidebar.date_input('End', TODAY, min_value=EARLIEST_DATE, max_value=TODAY)
if start >= end:
    st.sidebar.error('Start must be before End.')
    st.stop()
fee = st.sidebar.number_input('Fee per side (%)', value=0.05, min_value=0.0,
                              step=0.01, format='%.3f') / 100

st.sidebar.header('Search ranges')
fixed = st.sidebar.radio('Mode', ['Range', 'Fixed'], horizontal=True,
                         help='Fixed: backtest one parameter set, no search.') == 'Fixed'
if fixed:
    fmt = '%.2f' if preset.step_min < 0.1 else '%.1f'
    c1, c2, c3 = st.sidebar.columns(3)
    buy_v = c1.number_input('BUY', value=midpoint(preset.buy[:2], preset.step_min),
                            format=fmt, key=f'fixBUY{preset.label}')
    sell_v = c2.number_input('SELL', value=midpoint(preset.sell[:2], preset.step_min),
                             format=fmt, key=f'fixSELL{preset.label}')
    hold_v = c3.number_input('Hold months', value=0, min_value=0, step=1)
    if buy_v <= sell_v:  # matches ParameterGrid, which skips BUY ≤ SELL
        st.sidebar.error('BUY must be above SELL.')
        st.stop()
    grid = ParameterGrid(buy=Range(buy_v, buy_v, 1.0), sell=Range(sell_v, sell_v, 1.0),
                         min_hold_months=Range(hold_v, hold_v, 1))
    use_oos = False
else:
    grid = ParameterGrid(
        buy=range_input('BUY', *preset.buy, step_min=preset.step_min, key=preset.label),
        sell=range_input('SELL', *preset.sell, step_min=preset.step_min, key=preset.label),
        min_hold_months=range_input('Hold months', 0, 12, 1, integer=True),
    )
    use_oos = st.sidebar.checkbox('Out-of-sample validation (rank on first 70%)')
    try:
        combos = len(grid)
    except ValueError as exc:
        st.sidebar.error(str(exc))
        st.stop()
    st.sidebar.caption(f'{combos} parameter sets (BUY ≤ SELL skipped)')
run_label = 'Run backtest' if fixed else 'Run optimization'
run = st.sidebar.button(run_label, type='primary', width='stretch')

# ---------- Run ----------
if run:
    try:
        market = load_market(universe.defensive, universe.growth, universe.signal,
                             str(start), str(end + dt.timedelta(days=1)))
    except Exception as exc:  # surface data errors to the user
        st.error(f'Data error: {exc}')
        st.stop()
    bar = st.progress(0.0, text='Optimizing…')
    table = optimize(market, grid, fee, 0.7 if use_oos else None,
                     progress=lambda k, n: bar.progress(k / n, text=f'{k}/{n}'))
    bar.empty()
    st.session_state.update(market=market, table=table, universe=universe,
                            fee=fee, oos=use_oos, fixed=fixed)

if 'table' not in st.session_state:
    st.info(f'Set parameters in the sidebar and press **{run_label}**.')
    st.stop()

market: MarketData = st.session_state.market
table: pd.DataFrame = st.session_state.table
universe = st.session_state.universe
fee = st.session_state.fee
if table.empty:
    st.warning('No valid parameter sets.')
    st.stop()

period = f'{market.dates[0].date()} → {market.dates[-1].date()} ({len(market)} trading days)'
if st.session_state.oos:
    cut = int(len(market) * 0.7)
    period += f' · in-sample ends {market.dates[cut - 1].date()}'
st.caption(period)

top = table.head(TOP_N)
if st.session_state.get('fixed'):
    row = top.iloc[0]
    st.subheader(f'BUY {row.buy:g} / SELL {row.sell:g} / {row.min_hold_months}m')
else:
    st.subheader(f'Top {TOP_N} by total return')
    st.dataframe(round_pct(top), width='stretch', hide_index=True)

    st.subheader('Heatmap: excess return vs buy & hold')
    months = sorted(table['min_hold_months'].unique())
    m = st.select_slider('Min hold months', options=months, value=months[0]) \
        if len(months) > 1 else months[0]
    st.plotly_chart(heatmap_figure(table, m), width='stretch')

    st.subheader('Inspect a parameter set')
    labels = [f"#{i+1}  BUY {r.buy:g} / SELL {r.sell:g} / {r.min_hold_months}m"
              for i, r in top.iterrows()]
    choice = st.selectbox('Inspect parameter set', range(len(labels)),
                          format_func=labels.__getitem__)
    row = top.iloc[choice]
params = ParameterSet(float(row.buy), float(row.sell), int(row.min_hold_months))
strategy = run_backtest(market, VixRotation(params), fee)
benchmark = run_backtest(market, BuyAndHold(), fee)
s_m, b_m = compute_metrics(strategy), compute_metrics(benchmark)
st.caption('Full period (in-sample + out-of-sample).')
c = st.columns(4)
c[0].metric('Total return', f'{s_m.total_return_pct:.1f}%',
            f'{s_m.total_return_pct - b_m.total_return_pct:+.1f} pp vs benchmark')
c[1].metric('CAGR', f'{s_m.cagr_pct:.1f}%', f'{s_m.cagr_pct - b_m.cagr_pct:+.1f} pp')
c[2].metric('Max drawdown', f'{s_m.max_drawdown_pct:.1f}%')
c[3].metric('Trades', s_m.trade_count)
st.plotly_chart(equity_figure(strategy, benchmark, universe, params), width='stretch')
st.dataframe(round_pct(pd.DataFrame([asdict(m) for m in (s_m, b_m)],
                          index=['Rotation', f'Buy & hold {universe.defensive}'])),
             width='stretch')
log = pd.DataFrame([{**asdict(t), 'sold': universe.label(t.sold),
                     'bought': universe.label(t.bought)} for t in strategy.trades])
st.dataframe(round_pct(log), width='stretch', hide_index=True)

