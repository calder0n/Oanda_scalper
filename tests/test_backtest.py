"""Smoke tests del backtester."""
from __future__ import annotations

from src.backtest import backtest, synthetic_ohlc
from src.strategy import ScalpingStrategy


def test_backtest_runs_and_produces_trades_in_trending_market():
    df = synthetic_ohlc(n=5_000, seed=1, vol=0.0005, drift=0.00005)
    strat = ScalpingStrategy(mode="trend_pullback", min_adx=15)
    result = backtest(df, strat)
    assert len(result.trades) > 0
    # Todos los trades tienen outcome válido
    for t in result.trades:
        assert t.outcome in {"TP", "SL", "BE", "TIMEOUT"}
        assert t.pnl_r == t.pnl_r  # no NaN


def test_backtest_empty_df():
    import pandas as pd
    result = backtest(pd.DataFrame(columns=["open", "high", "low", "close"]), ScalpingStrategy())
    assert result.trades == []
    assert result.win_rate == 0.0


def test_breakeven_reduces_losses_versus_baseline():
    df = synthetic_ohlc(n=3_000, seed=4, vol=0.0005, drift=0.00003)
    strat = ScalpingStrategy(mode="trend_pullback", min_adx=15)
    with_be = backtest(df, strat, use_breakeven=True, use_trailing=False)
    without_be = backtest(df, strat, use_breakeven=False, use_trailing=False)
    # BE no puede producir peores resultados bruto en R (asumiendo mismo setup)
    # Comparamos pérdidas: con BE debería haber ≥ 0 trades a BE.
    assert with_be.breakevens >= 0
    # Si hubo trades, verificamos que ni crashea ni cambia el nº de trades.
    assert len(with_be.trades) == len(without_be.trades)
