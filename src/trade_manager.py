"""Gestión de trades abiertos: breakeven y trailing stop.

Se ejecuta en cada tick del trader: para cada trade abierto mueve el
``stopLoss`` si se cumplen los umbrales.

- Breakeven: al alcanzar ``breakeven_trigger_r`` a favor, sube el SL al precio
  de entrada (más un pequeño buffer igual al spread si se quiere).
- Trailing: una vez en breakeven, arrastra el SL a
  ``close ± trailing_atr_mult * ATR`` en la dirección del trade.

La comunicación con OANDA se hace via ``TradeCRCDO`` (trade modification).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from oandapyV20.endpoints import trades as trades_ep
from oandapyV20.exceptions import V20Error

from .indicators import atr as atr_indicator

logger = logging.getLogger(__name__)


class TradeManager:
    def __init__(
        self,
        client,
        breakeven_enabled: bool = True,
        breakeven_trigger_r: float = 1.0,
        trailing_enabled: bool = True,
        trailing_atr_mult: float = 1.2,
    ) -> None:
        self.client = client
        self.breakeven_enabled = breakeven_enabled
        self.breakeven_trigger_r = breakeven_trigger_r
        self.trailing_enabled = trailing_enabled
        self.trailing_atr_mult = trailing_atr_mult

    def manage(
        self,
        open_trades: list[Dict[str, Any]],
        candles_by_instrument: Dict[str, pd.DataFrame],
        precision_lookup,
    ) -> None:
        if not (self.breakeven_enabled or self.trailing_enabled):
            return
        for trade in open_trades:
            try:
                self._manage_one(trade, candles_by_instrument, precision_lookup)
            except V20Error as exc:
                logger.warning("V20Error gestionando trade %s: %s", trade.get("id"), exc)
            except Exception as exc:  # pragma: no cover - red
                logger.exception("Error gestionando trade %s: %s", trade.get("id"), exc)

    # ------------------------------------------------------------------ internals
    def _manage_one(
        self,
        trade: Dict[str, Any],
        candles_by_instrument: Dict[str, pd.DataFrame],
        precision_lookup,
    ) -> None:
        instrument = trade["instrument"]
        trade_id = trade["id"]
        units = int(trade["currentUnits"])
        if units == 0:
            return
        entry = float(trade["price"])
        is_long = units > 0

        df = candles_by_instrument.get(instrument)
        if df is None or df.empty or len(df) < 20:
            return
        atr_value = float(atr_indicator(df).iloc[-1])
        if pd.isna(atr_value) or atr_value <= 0:
            return
        close = float(df["close"].iloc[-1])

        current_sl_info = trade.get("stopLossOrder") or {}
        current_sl = float(current_sl_info["price"]) if current_sl_info.get("price") else None
        if current_sl is None:
            return
        risk = abs(entry - current_sl) if current_sl else None
        # Reconstruimos el riesgo original si el SL ya se movió a BE/trail
        # Tomamos max entre SL actual distancia y 1*ATR como proxy.
        if is_long:
            profit = close - entry
        else:
            profit = entry - close

        # Decidir nuevo SL candidato
        new_sl: Optional[float] = None
        reason = ""
        # Breakeven: si el profit ≥ trigger_r * |entry - SL_inicial|
        # Como no conservamos el SL inicial, usamos 1.5*ATR por defecto como R equivalente.
        r_estimate = max(risk or 0.0, 1.5 * atr_value)
        if self.breakeven_enabled and profit >= self.breakeven_trigger_r * r_estimate:
            be_candidate = entry
            if is_long and (current_sl is None or be_candidate > current_sl):
                new_sl = be_candidate
                reason = "breakeven"
            elif (not is_long) and (current_sl is None or be_candidate < current_sl):
                new_sl = be_candidate
                reason = "breakeven"

        # Trailing: se activa una vez el SL ya está ≥ entry (long) o ≤ entry (short)
        in_be = (is_long and current_sl >= entry) or ((not is_long) and current_sl <= entry)
        if self.trailing_enabled and in_be:
            if is_long:
                trail_candidate = close - self.trailing_atr_mult * atr_value
                if trail_candidate > (new_sl if new_sl is not None else current_sl):
                    new_sl = trail_candidate
                    reason = "trailing"
            else:
                trail_candidate = close + self.trailing_atr_mult * atr_value
                if trail_candidate < (new_sl if new_sl is not None else current_sl):
                    new_sl = trail_candidate
                    reason = "trailing"

        if new_sl is None:
            return
        precision = precision_lookup(instrument)
        new_sl_rounded = round(new_sl, precision)
        if round(current_sl, precision) == new_sl_rounded:
            return

        logger.info(
            "%s trade=%s mover SL %s: %.*f → %.*f (close=%.*f ATR=%.*f)",
            instrument,
            trade_id,
            reason,
            precision,
            current_sl,
            precision,
            new_sl_rounded,
            precision,
            close,
            precision,
            atr_value,
        )
        self._update_sl(trade_id, new_sl_rounded, precision)

    def _update_sl(self, trade_id: str, new_sl: float, precision: int) -> None:
        body = {
            "stopLoss": {
                "timeInForce": "GTC",
                "price": f"{new_sl:.{precision}f}",
            }
        }
        request = trades_ep.TradeCRCDO(
            accountID=self.client.account_id,
            tradeID=trade_id,
            data=body,
        )
        self.client.client.request(request)
