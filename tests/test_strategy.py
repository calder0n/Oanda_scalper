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
    # Mercado plano: ADX bajo, no debe disparar entrada pero sí devolver el snapshot
    close = np.full(120, 100.0) + np.random.default_rng(0).normal(0, 0.01, 120)
    df = _df_from_close(close)
    result = ScalpingStrategy(min_adx=25).evaluate(df)
    assert result is not None
    assert result.setup is None
    assert result.price > 0
    assert 0 <= result.rsi <= 100
    assert result.adx >= 0


def test_buy_signal_on_strong_downtrend_then_oversold():
    # Caída pronunciada → ADX alto y RSI bajo → señal de COMPRA
    close = np.linspace(120.0, 100.0, 120)
    df = _df_from_close(close)
    result = ScalpingStrategy(min_adx=20).evaluate(df)
    assert result is not None
    assert result.setup is not None
    setup = result.setup
    assert setup.signal == Signal.BUY
    assert setup.rsi <= 35
    assert setup.adx > 20
    assert setup.stop_loss < setup.entry_price < setup.take_profit


def test_sell_signal_on_strong_uptrend_then_overbought():
    # Subida sostenida → ADX alto y RSI alto → señal de VENTA
    close = np.linspace(100.0, 120.0, 120)
    df = _df_from_close(close)
    result = ScalpingStrategy(min_adx=20).evaluate(df)
    assert result is not None
    assert result.setup is not None
    setup = result.setup
    assert setup.signal == Signal.SELL
    assert setup.rsi >= 60
    assert setup.adx > 20
    assert setup.take_profit < setup.entry_price < setup.stop_loss
