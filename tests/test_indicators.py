"""Smoke tests para los indicadores."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators import add_indicators, atr, ema, macd, rsi


def _sample_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close + rng.uniform(0.1, 0.5, n)
    low = close - rng.uniform(0.1, 0.5, n)
    open_ = close + rng.uniform(-0.2, 0.2, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_ema_length():
    df = _sample_df()
    assert len(ema(df["close"], 9)) == len(df)


def test_rsi_bounds():
    df = _sample_df()
    values = rsi(df["close"]).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def test_atr_positive():
    df = _sample_df()
    values = atr(df).dropna()
    assert (values > 0).all()


def test_macd_columns():
    df = _sample_df()
    out = macd(df["close"])
    assert {"macd", "signal", "hist"}.issubset(out.columns)


def test_add_indicators_columns():
    df = _sample_df()
    out = add_indicators(df)
    expected = {
        "ema_fast",
        "ema_slow",
        "ema_trend",
        "rsi",
        "atr",
        "macd",
        "signal",
        "hist",
        "bb_mid",
        "bb_upper",
        "bb_lower",
        "bb_width",
    }
    assert expected.issubset(out.columns)
