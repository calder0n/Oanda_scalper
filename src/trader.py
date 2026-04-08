"""Bucle principal de trading."""
from __future__ import annotations

import logging
import time
from typing import Dict

from .config import Config
from .oanda_client import OandaClient
from .risk_manager import RiskManager
from .strategy import ScalpingStrategy, Signal, TradeSetup

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = OandaClient(
            api_key=config.api_key,
            account_id=config.account_id,
            environment=config.environment,
        )
        self.strategy = ScalpingStrategy(
            atr_sl_mult=config.atr_sl_mult,
            atr_tp_mult=config.atr_tp_mult,
        )
        self.risk = RiskManager(max_daily_loss=config.max_daily_loss)
        self.precision_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------ Setup
    def _instrument_precision(self, instrument: str) -> int:
        if instrument in self.precision_cache:
            return self.precision_cache[instrument]
        details = self.client.get_instrument_details(instrument)
        precision = int(details.get("displayPrecision", 5))
        self.precision_cache[instrument] = precision
        return precision

    # ------------------------------------------------------------------ Loop
    def run(self) -> None:
        logger.info(
            "Iniciando trader | env=%s | instrumentos=%s | granularidad=%s",
            self.config.environment,
            self.config.instruments,
            self.config.granularity,
        )
        try:
            balance = self.client.get_balance()
            logger.info("Balance inicial cuenta: %.2f", balance)
            self.risk.update_day(balance)
        except Exception as exc:  # pragma: no cover - red
            logger.exception("No se pudo obtener el balance inicial: %s", exc)
            raise

        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                logger.info("Interrumpido por el usuario, saliendo…")
                break
            except Exception as exc:  # pragma: no cover - red
                logger.exception("Error en el ciclo principal: %s", exc)
            time.sleep(self.config.loop_interval)

    def _tick(self) -> None:
        balance = self.client.get_balance()
        self.risk.update_day(balance)
        self.risk.register_pnl(balance)

        if self.risk.is_halted():
            logger.info("Trader pausado por límite de pérdida diaria.")
            return

        open_trades = self.client.get_open_trades()
        if len(open_trades) >= self.config.max_concurrent_trades:
            logger.debug(
                "Operaciones abiertas (%d) >= máximo (%d). Esperando.",
                len(open_trades),
                self.config.max_concurrent_trades,
            )
            return

        instruments_in_position = {t["instrument"] for t in open_trades}

        for instrument in self.config.instruments:
            if instrument in instruments_in_position:
                continue
            try:
                self._evaluate_instrument(instrument, balance)
            except Exception as exc:  # pragma: no cover - red
                logger.exception("Fallo al analizar %s: %s", instrument, exc)

    def _evaluate_instrument(self, instrument: str, balance: float) -> None:
        df = self.client.get_candles(
            instrument=instrument,
            granularity=self.config.granularity,
            count=self.config.candles_count,
        )
        if df.empty:
            logger.warning("Sin datos de velas para %s", instrument)
            return

        setup = self.strategy.evaluate(df)
        if not setup or setup.signal == Signal.HOLD:
            logger.debug("%s sin señal", instrument)
            return

        price_info = self.client.get_current_price(instrument)
        live_price = price_info["ask"] if setup.signal == Signal.BUY else price_info["bid"]

        # Recalculamos SL/TP usando el precio en vivo para no quedar desalineados
        if setup.signal == Signal.BUY:
            stop_loss = live_price - self.config.atr_sl_mult * setup.atr
            take_profit = live_price + self.config.atr_tp_mult * setup.atr
        else:
            stop_loss = live_price + self.config.atr_sl_mult * setup.atr
            take_profit = live_price - self.config.atr_tp_mult * setup.atr

        units = self.risk.calculate_position_size(
            balance=balance,
            risk_per_trade=self.config.risk_per_trade,
            entry_price=live_price,
            stop_loss=stop_loss,
            instrument=instrument,
        )
        if units <= 0:
            logger.info("%s tamaño calculado = 0, descartando trade", instrument)
            return

        if setup.signal == Signal.SELL:
            units = -units

        precision = self._instrument_precision(instrument)
        logger.info(
            "%s SEÑAL %s | entry=%.5f sl=%.5f tp=%.5f units=%d motivo=%s",
            instrument,
            setup.signal.value,
            live_price,
            stop_loss,
            take_profit,
            units,
            setup.reason,
        )
        response = self.client.create_market_order(
            instrument=instrument,
            units=units,
            stop_loss=round(stop_loss, precision),
            take_profit=round(take_profit, precision),
            precision=precision,
        )
        fill = response.get("orderFillTransaction") or response.get("orderCreateTransaction")
        if fill:
            logger.info("Orden ejecutada: id=%s", fill.get("id"))
        else:
            logger.warning("Respuesta inesperada al crear orden: %s", response)
