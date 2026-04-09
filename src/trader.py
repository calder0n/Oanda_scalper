"""Bucle principal de trading."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from .config import Config
from .notifier import TelegramNotifier
from .oanda_client import OandaClient
from .risk_manager import RiskManager
from .sessions import TradingSession, current_session, parse_sessions
from .strategy import ScalpingStrategy, Signal
from .trade_logger import TradeCSVLogger

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
            min_adx=config.min_adx,
            rsi_buy_threshold=config.rsi_buy_threshold,
            rsi_sell_threshold=config.rsi_sell_threshold,
        )
        self.risk = RiskManager(max_daily_loss=config.max_daily_loss)
        self.notifier = TelegramNotifier(
            token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        )
        self.trade_log = TradeCSVLogger(config.trade_log_path)
        self.sessions = parse_sessions(config.sessions_spec)
        self.precision_cache: Dict[str, int] = {}
        self._last_session: Optional[TradingSession] = None

    # ------------------------------------------------------------------ Setup
    def _instrument_precision(self, instrument: str) -> int:
        if instrument in self.precision_cache:
            return self.precision_cache[instrument]
        details = self.client.get_instrument_details(instrument)
        precision = int(details.get("displayPrecision", 5))
        self.precision_cache[instrument] = precision
        return precision

    def _sessions_label(self) -> str:
        return ", ".join(s.label() for s in self.sessions)

    # ------------------------------------------------------------------ Loop
    def run(self) -> None:
        logger.info(
            "Iniciando trader | env=%s | instrumentos=%s | granularidad=%s | sesiones=%s",
            self.config.environment,
            self.config.instruments,
            self.config.granularity,
            self._sessions_label(),
        )
        try:
            balance = self.client.get_balance()
            logger.info("Balance inicial cuenta: %.2f", balance)
            self.risk.update_day(balance)
            self.notifier.notify_startup(
                environment=self.config.environment,
                instruments=self.config.instruments,
                granularity=self.config.granularity,
                balance=balance,
                sessions_label=self._sessions_label(),
            )
        except Exception as exc:  # pragma: no cover - red
            logger.exception("No se pudo obtener el balance inicial: %s", exc)
            self.notifier.notify_error(f"Fallo al arrancar: {exc}")
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

        session = current_session(sessions=self.sessions)
        self._handle_session_transition(session, balance)

        if session is None:
            logger.debug("Fuera de sesión, esperando.")
            return

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
                self._evaluate_instrument(instrument, balance, session)
            except Exception as exc:  # pragma: no cover - red
                logger.exception("Fallo al analizar %s: %s", instrument, exc)

    # ------------------------------------------------------------------ Sesiones
    def _handle_session_transition(
        self, session: Optional[TradingSession], balance: float
    ) -> None:
        if session == self._last_session:
            return
        # Cierre de sesión anterior
        if self._last_session is not None and session != self._last_session:
            logger.info("Sesión %s cerrada", self._last_session.name)
            self.notifier.notify_session_end(self._last_session.name, balance)
        # Apertura de la nueva
        if session is not None:
            logger.info(
                "Iniciando sesión %s (%02d-%02d UTC)",
                session.name,
                session.start_hour_utc,
                session.end_hour_utc,
            )
            self.notifier.notify_session_start(
                session_name=session.name,
                start_hour=session.start_hour_utc,
                end_hour=session.end_hour_utc,
                instruments=self.config.instruments,
                balance=balance,
            )
        self._last_session = session

    # ------------------------------------------------------------------ Análisis
    def _evaluate_instrument(
        self, instrument: str, balance: float, session: TradingSession
    ) -> None:
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

        # Filtro 3: spread dinámico
        price_info = self.client.get_current_price(instrument)
        spread = price_info["spread"]
        max_spread = setup.atr * self.config.spread_atr_ratio
        if spread > max_spread:
            logger.info(
                "%s descartado por spread alto: spread=%.5f > %.5f (ATR*%.2f)",
                instrument,
                spread,
                max_spread,
                self.config.spread_atr_ratio,
            )
            return

        live_price = price_info["ask"] if setup.signal == Signal.BUY else price_info["bid"]

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
            "%s SEÑAL %s | entry=%.5f sl=%.5f tp=%.5f units=%d rsi=%.2f adx=%.2f spread=%.5f motivo=%s",
            instrument,
            setup.signal.value,
            live_price,
            stop_loss,
            take_profit,
            units,
            setup.rsi,
            setup.adx,
            spread,
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
        order_id = fill.get("id") if fill else ""
        if fill:
            logger.info("Orden ejecutada: id=%s", order_id)
        else:
            logger.warning("Respuesta inesperada al crear orden: %s", response)

        # Notificación + persistencia
        self.notifier.notify_entry(
            instrument=instrument,
            side=setup.signal.value,
            units=units,
            entry_price=live_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=setup.atr,
            rsi=setup.rsi,
            adx=setup.adx,
            spread=spread,
            balance=balance,
            session=session.name,
            reason=setup.reason,
            order_id=order_id,
        )
        self.trade_log.log_entry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            session=session.name,
            instrument=instrument,
            signal=setup.signal.value,
            units=units,
            entry_price=f"{live_price:.5f}",
            stop_loss=f"{stop_loss:.5f}",
            take_profit=f"{take_profit:.5f}",
            atr=f"{setup.atr:.5f}",
            rsi=f"{setup.rsi:.2f}",
            adx=f"{setup.adx:.2f}",
            spread=f"{spread:.5f}",
            balance=f"{balance:.2f}",
            reason=setup.reason,
            order_id=order_id,
        )
