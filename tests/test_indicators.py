"""Smoke tests para los indicadores."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators import add_indicators, adx, atr, rsi


def _sample_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close + rng.uniform(0.1, 0.5, n)
    low = close - rng.uniform(0.1, 0.5, n)
    open_ = close + rng.uniform(-0.2, 0.2, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_rsi_bounds():
    df = _sample_df()
    values = rsi(df["close"]).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def test_atr_positive():
    df = _sample_df()
    values = atr(df).dropna()
    assert (values > 0).all()


def test_adx_bounds():
    df = _sample_df()
    values = adx(df).dropna()
    assert (values >= 0).all()
    assert (values <= 100).all()


def test_add_indicators_columns():
    df = _sample_df()
    out = add_indicators(df)
    assert {"rsi", "atr", "adx"}.issubset(out.columns)
