"""Plotly figures for the UI layer."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .domain import ParameterSet, Position, Universe
from .engine import BacktestResult

BUY_COLOR = '#16834C'
SELL_COLOR = '#CF6710'


def equity_figure(strategy: BacktestResult, benchmark: BacktestResult,
                  universe: Universe, params: ParameterSet,
                  growth_benchmark: BacktestResult | None = None) -> go.Figure:
    """Return curves on top, signal with thresholds below; shared x-axis."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        row_heights=[0.68, 0.32])
    pct = lambda r: (r.equity - 1) * 100
    fig.add_scatter(x=strategy.dates, y=pct(strategy), name='Rotation',
                    line=dict(width=2.5), row=1, col=1)
    fig.add_scatter(x=benchmark.dates, y=pct(benchmark), name=f'Buy & hold {universe.defensive}',
                    line=dict(width=2, color='gray'), row=1, col=1)
    if growth_benchmark is not None:
        fig.add_scatter(x=growth_benchmark.dates, y=pct(growth_benchmark),
                        name=f'Buy & hold {universe.growth}',
                        line=dict(width=2, color='#C2410C', dash='dash'), row=1, col=1)
    _add_trade_markers(fig, strategy, universe)

    fig.add_scatter(x=strategy.dates, y=strategy.signal, name=universe.signal,
                    line=dict(width=1.2, color='#6A5ACD'), row=2, col=1)
    fig.add_hline(y=params.buy, line=dict(dash='dash', color=BUY_COLOR, width=1),
                  annotation_text=f'BUY {params.buy:g}', row=2, col=1)
    fig.add_hline(y=params.sell, line=dict(dash='dash', color=SELL_COLOR, width=1),
                  annotation_text=f'SELL {params.sell:g}', row=2, col=1)

    _shade_growth(fig, strategy)
    fig.update_yaxes(title_text='Return (%)', tickformat='.1f', row=1, col=1)
    fig.update_yaxes(title_text=universe.signal, row=2, col=1)
    fig.update_traces(hovertemplate='%{y:.1f}', selector=dict(mode='lines'))
    fig.update_layout(height=650, hovermode='x unified',
                      legend=dict(orientation='h', y=1.06), margin=dict(t=40))
    return fig


def _add_trade_markers(fig: go.Figure, result: BacktestResult, universe: Universe) -> None:
    idx = {d: i for i, d in enumerate(result.dates)}
    for to_growth, symbol, color in ((True, 'triangle-up', BUY_COLOR),
                                        (False, 'triangle-down', SELL_COLOR)):
        xs, ys, texts = [], [], []
        for t in result.trades:
            is_opening_defensive = t.sold is Position.CASH and t.bought is Position.DEFENSIVE
            if is_opening_defensive or (t.bought is Position.GROWTH) != to_growth:
                continue
            day = pd.Timestamp(t.trade_date)
            xs.append(day)
            ys.append((result.equity[idx[day]] - 1) * 100)
            texts.append(f'{universe.label(t.sold)} → {universe.label(t.bought)}'
                         f' (signal {t.signal_value:.3g})')
        name = (f'Buy {universe.growth}' if to_growth
                else f'Sell {universe.growth} / Buy {universe.defensive}')
        fig.add_scatter(x=xs, y=ys, mode='markers', hovertext=texts, hoverinfo='text',
                        marker=dict(symbol=symbol, size=13, color=color), name=name,
                        row=1, col=1)


def _shade_growth(fig: go.Figure, result: BacktestResult) -> None:
    """Shade Growth holding intervals across both panels."""
    def shade(x0, x1):
        fig.add_vrect(x0=x0, x1=x1, fillcolor='#2E8B57', opacity=0.12,
                      line_width=0, row='all', col=1)

    start = None
    for d, p in zip(result.dates, result.positions):
        if p is Position.GROWTH and start is None:
            start = d
        elif p is not Position.GROWTH and start is not None:
            shade(start, d)
            start = None
    if start is not None:
        shade(start, result.dates[-1])


def heatmap_figure(table: pd.DataFrame, min_hold_months: int) -> go.Figure:
    sub = table[table['min_hold_months'] == min_hold_months]
    pivot = sub.pivot(index='sell', columns='buy',
                      values='excess_vs_benchmark_pp').sort_index()
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index,
                               colorscale='RdYlGn', zmid=0,
                               colorbar=dict(title='vs B&H (pp)', tickformat='.1f'),
                               hovertemplate='BUY %{x}<br>SELL %{y}<br>'
                                             '%{z:+.1f} pp vs buy & hold<extra></extra>'))
    fig.update_layout(xaxis_title='BUY threshold', yaxis_title='SELL threshold',
                      margin=dict(t=20))
    return fig
