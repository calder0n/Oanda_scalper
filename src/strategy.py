"""Estrategia de scalping con dos modos seleccionables.

Modo por defecto: ``trend_pullback``
------------------------------------
Scalping en dirección de la tendencia (mayor win-rate para M1).

Reglas:

1. **Tendencia** por cruce de EMAs (rápida > lenta) y pendiente positiva de la
   EMA lenta → permitimos **COMPRAS**. Caso inverso → sólo **VENTAS**.
2. **Fuerza mínima**: ADX(14) ≥ ``min_adx`` (default 20, más bajo que el modo
   antiguo: queremos una tendencia viva pero no necesitamos que esté en
   explosión).
3. **Pullback**: esperamos a que el RSI entre en zona de corrección contra
   la tendencia para entrar a favor:
   - COMPRA: ``RSI ≤ rsi_buy_threshold`` (default 40)
   - VENTA: ``RSI ≥ rsi_sell_threshold`` (default 60)
4. **Confirmación de retroceso hacia la EMA rápida**: el precio debe haber
   tocado o cruzado la EMA rápida en la última barra o la anterior.

SL y TP con ATR: SL=ATR*atr_sl_mult | TP=ATR*atr_tp_mult.

Modo ``mean_reversion`` (legacy)
--------------------------------
Mantenemos la lógica original para compatibilidad. OJO: funciona mejor con
``min_adx`` BAJO (mercado lateral), nunca con ADX alto.
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
    rsi: float
    adx: float
    reason: str


@dataclass
class EvaluationResult:
    price: float
    rsi: float
    adx: float
    atr: float
    setup: Optional[TradeSetup]


class ScalpingStrategy:
    """Estrategia parametrizable.

    ``mode`` puede ser ``"trend_pullback"`` (default) o ``"mean_reversion"``.
    """

    VALID_MODES = ("trend_pullback", "mean_reversion")

    def __init__(
        self,
        atr_sl_mult: float = 1.2,
        atr_tp_mult: float = 2.0,
        min_adx: float = 20.0,
        rsi_buy_threshold: float = 40.0,
        rsi_sell_threshold: float = 60.0,
        mode: str = "trend_pullback",
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_slope_lookback: int = 5,
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(f"mode debe ser uno de {self.VALID_MODES}, recibido {mode!r}")
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.min_adx = min_adx
        self.rsi_buy = rsi_buy_threshold
        self.rsi_sell = rsi_sell_threshold
        self.mode = mode
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_slope_lookback = ema_slope_lookback

    # ------------------------------------------------------------------ Public
    def evaluate(self, df: pd.DataFrame) -> Optional[EvaluationResult]:
        min_len = max(self.ema_slow + self.ema_slope_lookback + 5, 30)
        if df is None or len(df) < min_len:
            return None

        data = add_indicators(df, self.ema_fast, self.ema_slow).dropna()
        if data.empty or len(data) < self.ema_slope_lookback + 2:
            return None

        last = data.iloc[-1]
        prev = data.iloc[-2]
        price = float(last["close"])
        atr_value = float(last["atr"])
        rsi_value = float(last["rsi"])
        adx_value = float(last["adx"])

        setup: Optional[TradeSetup] = None
        if atr_value > 0:
            if self.mode == "trend_pullback":
                setup = self._trend_pullback_setup(data, last, prev, price, atr_value, rsi_value, adx_value)
            else:
                setup = self._mean_reversion_setup(price, atr_value, rsi_value, adx_value)

        return EvaluationResult(
            price=price,
            rsi=rsi_value,
            adx=adx_value,
            atr=atr_value,
            setup=setup,
        )

    # ------------------------------------------------------------------ Modos
    def _mean_reversion_setup(
        self,
        price: float,
        atr_value: float,
        rsi_value: float,
        adx_value: float,
    ) -> Optional[TradeSetup]:
        """Lógica original: reversión sobre RSI con filtro ADX.

        Recomendado con ADX BAJO (lateral). Si ``min_adx`` es alto, el bot
        casi no opera; si es 0 dispara en cualquier rango.
        """
        if adx_value < self.min_adx:
            return None
        if rsi_value <= self.rsi_buy:
            sl = price - self.atr_sl_mult * atr_value
            tp = price + self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.BUY,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                rsi=rsi_value,
                adx=adx_value,
                reason=(
                    f"MR | RSI={rsi_value:.1f} ≤ {self.rsi_buy:.0f} "
                    f"& ADX={adx_value:.1f} ≥ {self.min_adx:.0f}"
                ),
            )
        if rsi_value >= self.rsi_sell:
            sl = price + self.atr_sl_mult * atr_value
            tp = price - self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.SELL,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                rsi=rsi_value,
                adx=adx_value,
                reason=(
                    f"MR | RSI={rsi_value:.1f} ≥ {self.rsi_sell:.0f} "
                    f"& ADX={adx_value:.1f} ≥ {self.min_adx:.0f}"
                ),
            )
        return None

    def _trend_pullback_setup(
        self,
        data: pd.DataFrame,
        last: pd.Series,
        prev: pd.Series,
        price: float,
        atr_value: float,
        rsi_value: float,
        adx_value: float,
    ) -> Optional[TradeSetup]:
        """Pullback a favor de tendencia."""
        if adx_value < self.min_adx:
            return None

        ema_fast_now = float(last["ema_fast"])
        ema_slow_now = float(last["ema_slow"])
        slope_series = data["ema_slow"].iloc[-self.ema_slope_lookback - 1 : -1]
        if len(slope_series) < 2:
            return None
        slope = ema_slow_now - float(slope_series.iloc[0])

        uptrend = ema_fast_now > ema_slow_now and slope > 0
        downtrend = ema_fast_now < ema_slow_now and slope < 0

        # Pullback reciente: en las últimas `ema_slope_lookback` barras el precio
        # se acercó a la EMA rápida. Aceptamos tanto un toque (low ≤ EMA ≤ high)
        # como un cruce por debajo (para longs) / por encima (para shorts), que
        # es lo típico en pullbacks más profundos.
        lookback = min(self.ema_slope_lookback, len(data) - 1)
        recent = data.iloc[-lookback - 1 :]
        touched_fast = ((recent["low"] <= recent["ema_fast"]) & (recent["high"] >= recent["ema_fast"])).any()
        dipped_below = (recent["low"] <= recent["ema_fast"]).any()
        spiked_above = (recent["high"] >= recent["ema_fast"]).any()

        if uptrend and rsi_value <= self.rsi_buy and (touched_fast or dipped_below):
            sl = price - self.atr_sl_mult * atr_value
            tp = price + self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.BUY,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                rsi=rsi_value,
                adx=adx_value,
                reason=(
                    f"TP | EMA{self.ema_fast}>EMA{self.ema_slow} slope+ "
                    f"RSI={rsi_value:.1f} ≤ {self.rsi_buy:.0f} ADX={adx_value:.1f}"
                ),
            )

        if downtrend and rsi_value >= self.rsi_sell and (touched_fast or spiked_above):
            sl = price + self.atr_sl_mult * atr_value
            tp = price - self.atr_tp_mult * atr_value
            return TradeSetup(
                signal=Signal.SELL,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                atr=atr_value,
                rsi=rsi_value,
                adx=adx_value,
                reason=(
                    f"TP | EMA{self.ema_fast}<EMA{self.ema_slow} slope- "
                    f"RSI={rsi_value:.1f} ≥ {self.rsi_sell:.0f} ADX={adx_value:.1f}"
                ),
            )
        return None
