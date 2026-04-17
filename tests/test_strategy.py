"""Tests del motor de estrategia con datos sintéticos."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategy import ScalpingStrategy, Signal


def _df_from_close(close: np.ndarray) -> pd.DataFrame:
    high = close + 0.1
    low = close - 0.1
    open_ = close
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_snapshot_always_returned_even_without_setup():
    # Mercado plano: sin tendencia ni condiciones de pullback → snapshot sin setup
    close = np.full(200, 100.0) + np.random.default_rng(0).normal(0, 0.01, 200)
    df = _df_from_close(close)
    result = ScalpingStrategy().evaluate(df)
    assert result is not None
    assert result.setup is None
    assert result.price > 0
    assert 0 <= result.rsi <= 100
    assert result.adx >= 0


# ------------------------------------------------------------- Trend pullback
def test_trend_pullback_buy_on_uptrend_with_pullback():
    # Subida escalonada con pullbacks amplios → EMA rápida > lenta, RSI baja en los retrocesos → BUY
    rng = np.random.default_rng(5)
    trend = np.linspace(100.0, 110.0, 300)
    pullback_noise = np.sin(np.linspace(0, 14 * np.pi, 300)) * 2.5
    close = trend + pullback_noise + rng.normal(0, 0.1, 300)
    df = _df_from_close(close)
    strat = ScalpingStrategy(
        mode="trend_pullback",
        min_adx=10,
        rsi_buy_threshold=45,
        rsi_sell_threshold=55,
        ema_fast=10,
        ema_slow=30,
    )
    saw_buy = False
    for i in range(80, len(df)):
        res = strat.evaluate(df.iloc[: i + 1])
        if res and res.setup and res.setup.signal == Signal.BUY:
            saw_buy = True
            break
    assert saw_buy, "Debería emerger al menos una señal BUY en una subida con pullbacks"


def test_trend_pullback_sell_on_downtrend_with_pullback():
    rng = np.random.default_rng(6)
    trend = np.linspace(110.0, 100.0, 300)
    pullback_noise = np.sin(np.linspace(0, 14 * np.pi, 300)) * 2.5
    close = trend + pullback_noise + rng.normal(0, 0.1, 300)
    df = _df_from_close(close)
    strat = ScalpingStrategy(
        mode="trend_pullback",
        min_adx=10,
        rsi_buy_threshold=45,
        rsi_sell_threshold=55,
        ema_fast=10,
        ema_slow=30,
    )
    saw_sell = False
    for i in range(80, len(df)):
        res = strat.evaluate(df.iloc[: i + 1])
        if res and res.setup and res.setup.signal == Signal.SELL:
            saw_sell = True
            break
    assert saw_sell, "Debería emerger al menos una señal SELL en una bajada con pullbacks"


# ------------------------------------------------------------- Mean reversion
def test_mean_reversion_buy_on_strong_downtrend_then_oversold():
    close = np.linspace(120.0, 100.0, 120)
    df = _df_from_close(close)
    strat = ScalpingStrategy(mode="mean_reversion", min_adx=20, rsi_buy_threshold=35, rsi_sell_threshold=65)
    result = strat.evaluate(df)
    assert result is not None
    assert result.setup is not None
    assert result.setup.signal == Signal.BUY
    assert result.setup.rsi <= 35
    assert result.setup.stop_loss < result.setup.entry_price < result.setup.take_profit


def test_mean_reversion_sell_on_strong_uptrend_then_overbought():
    close = np.linspace(100.0, 120.0, 120)
    df = _df_from_close(close)
    strat = ScalpingStrategy(mode="mean_reversion", min_adx=20, rsi_buy_threshold=35, rsi_sell_threshold=65)
    result = strat.evaluate(df)
    assert result is not None
    assert result.setup is not None
    assert result.setup.signal == Signal.SELL
    assert result.setup.rsi >= 65
    assert result.setup.take_profit < result.setup.entry_price < result.setup.stop_loss


def test_invalid_mode_raises():
    import pytest

    with pytest.raises(ValueError):
        ScalpingStrategy(mode="foobar")
