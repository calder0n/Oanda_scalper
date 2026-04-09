"""Estrategia de scalping mean-reversion con filtro de fuerza de tendencia.

Reglas (puramente sobre indicadores; los filtros de horario y spread se
aplican en el `Trader`):

1. **ADX(14) > MIN_ADX (default 25)** → solo se opera cuando el mercado se
   está moviendo con fuerza, no en lateral.
2. **RSI(14) ≤ RSI_BUY (default 35)** → señal de COMPRA (mean-reversion al alza).
3. **RSI(14) ≥ RSI_SELL (default 60)** → señal de VENTA (mean-reversion a la baja).

SL y TP se calculan con ATR:
    SL = entry ± ATR × ATR_SL_MULT
    TP = entry ± ATR × ATR_TP_MULT
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
    """Resultado de evaluar la estrategia para una vela.

    Siempre incluye los últimos valores de indicadores para poder loggearlos
    aunque no haya señal. ``setup`` es ``None`` si no se cumple la lógica de
    entrada.
    """

    price: float
    rsi: float
    adx: float
    atr: float
    setup: Optional[TradeSetup]


class ScalpingStrategy:
    def __init__(
        self,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        min_adx: float = 25.0,
        rsi_buy_threshold: float = 35.0,
        rsi_sell_threshold: float = 60.0,
    ) -> None:
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.min_adx = min_adx
        self.rsi_buy = rsi_buy_threshold
        self.rsi_sell = rsi_sell_threshold

    def evaluate(self, df: pd.DataFrame) -> Optional[EvaluationResult]:
        if df is None or len(df) < 30:
            return None

        data = add_indicators(df).dropna()
        if data.empty:
            return None

        last = data.iloc[-1]
        price = float(last["close"])
        atr_value = float(last["atr"])
        rsi_value = float(last["rsi"])
        adx_value = float(last["adx"])

        setup: Optional[TradeSetup] = None

        if atr_value > 0 and adx_value >= self.min_adx:
            if rsi_value <= self.rsi_buy:
                sl = price - self.atr_sl_mult * atr_value
                tp = price + self.atr_tp_mult * atr_value
                setup = TradeSetup(
                    signal=Signal.BUY,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    atr=atr_value,
                    rsi=rsi_value,
                    adx=adx_value,
                    reason=(
                        f"RSI={rsi_value:.1f} ≤ {self.rsi_buy:.0f} "
                        f"y ADX={adx_value:.1f} > {self.min_adx:.0f}"
                    ),
                )
            elif rsi_value >= self.rsi_sell:
                sl = price + self.atr_sl_mult * atr_value
                tp = price - self.atr_tp_mult * atr_value
                setup = TradeSetup(
                    signal=Signal.SELL,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    atr=atr_value,
                    rsi=rsi_value,
                    adx=adx_value,
                    reason=(
                        f"RSI={rsi_value:.1f} ≥ {self.rsi_sell:.0f} "
                        f"y ADX={adx_value:.1f} > {self.min_adx:.0f}"
                    ),
                )

        return EvaluationResult(
            price=price,
            rsi=rsi_value,
            adx=adx_value,
            atr=atr_value,
            setup=setup,
        )
