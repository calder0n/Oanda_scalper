"""Indicadores técnicos vectorizados con pandas/numpy.

Indicadores usados por la estrategia: RSI(14), ATR(14), ADX(14) y EMAs
(por defecto 20/50) para detección de tendencia.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_values = 100 - (100 / (1 + rs))
    rsi_values = rsi_values.where(~((avg_loss == 0) & (avg_gain > 0)), other=100.0)
    rsi_values = rsi_values.where(~((avg_loss == 0) & (avg_gain == 0)), other=50.0)
    return rsi_values


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    atr_val = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_val

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def add_indicators(
    df: pd.DataFrame,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
) -> pd.DataFrame:
    """Devuelve una copia del DataFrame con RSI, ATR, ADX y EMAs añadidos."""
    out = df.copy()
    out["rsi"] = rsi(out["close"], 14)
    out["atr"] = atr(out, 14)
    out["adx"] = adx(out, 14)
    out["ema_fast"] = ema(out["close"], ema_fast_period)
    out["ema_slow"] = ema(out["close"], ema_slow_period)
    return out
