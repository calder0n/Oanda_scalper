"""Estrategia de scalping multi-confirmación.

La idea es operar a favor de la tendencia (EMA 9 > EMA 21 > EMA 50 para largos
y al revés para cortos), entrar cuando el precio retrocede a la EMA rápida y
confirmar momento con RSI y MACD. Se filtra la volatilidad mínima con la
anchura de las bandas de Bollinger y el ATR.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from .indicators import add_indicators


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSetup:
    signal: Signal
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    reason: str


class ScalpingStrategy:
    """Estrategia de scalping basada en EMA + RSI + MACD + ATR."""

    def __init__(
        self,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        min_bb_width: float = 0.0008,
        rsi_long_min: float = 40.0,
        rsi_long_max: float = 70.0,
        rsi_short_min: float = 30.0,
        rsi_short_max: float = 60.0,
    ) -> None:
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.min_bb_width = min_bb_width
        self.rsi_long_min = rsi_long_min
        self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min
        self.rsi_short_max = rsi_short_max

    def evaluate(self, df: pd.DataFrame) -> Optional[TradeSetup]:
        if df is None or len(df) < 60:
            return None

        data = add_indicators(df).dropna()
        if len(data) < 3:
            return None

        last = data.iloc[-1]
        prev = data.iloc[-2]

        # Filtro de volatilidad: evitar mercado lateral aburrido
        if pd.isna(last["bb_width"]) or last["bb_width"] < self.min_bb_width:
            return None
        if pd.isna(last["atr"]) or last["atr"] <= 0:
            return None

        price = float(last["close"])
        atr_value = float(last["atr"])

        long_trend = last["ema_fast"] > last["ema_slow"] > last["ema_trend"]
        short_trend = last["ema_fast"] < last["ema_slow"] < last["ema_trend"]

        macd_bull = last["macd"] > last["signal"] and last["hist"] > prev["hist"]
        macd_bear = last["macd"] < last["signal"] and last["hist"] < prev["hist"]

        # Buscamos un retroceso a la EMA rápida, no una entrada extendida
        pullback_long = prev["low"] <= prev["ema_fast"] and last["close"] > last["ema_fast"]
        pullback_short = prev["high"] >= prev["ema_fast"] and last["close"] < last["ema_fast"]

        rsi_long_ok = self.rsi_long_min < last["rsi"] < self.rsi_long_max
        rsi_short_ok = self.rsi_short_min < last["rsi"] < self.rsi_short_max

        if long_trend and pullback_long and macd_bull and rsi_long_ok:
            sl = price - self.atr_sl_mult * atr_value
            tp = price + self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.BUY,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                reason="EMA alcista + pullback + MACD alcista + RSI ok",
            )

        if short_trend and pullback_short and macd_bear and rsi_short_ok:
            sl = price + self.atr_sl_mult * atr_value
            tp = price - self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.SELL,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                reason="EMA bajista + pullback + MACD bajista + RSI ok",
            )

        return None
