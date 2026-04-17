"""Cálculo de tamaño de posición, drawdown diario y cooldown por instrumento."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    day: str
    starting_balance: float
    realized_pnl: float = 0.0
    halted: bool = False
    cooldowns: Dict[str, datetime] = field(default_factory=dict)


class RiskManager:
    def __init__(
        self,
        max_daily_loss: float = 0.05,
        cooldown_seconds: int = 300,
    ) -> None:
        self.max_daily_loss = max_daily_loss
        self.cooldown_seconds = cooldown_seconds
        self.state: RiskState | None = None
        self._trade_instrument_map: Dict[str, str] = {}

    def update_day(self, balance: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state is None or self.state.day != today:
            self.state = RiskState(day=today, starting_balance=balance)
            logger.info("Nuevo día de trading %s | balance inicial=%.2f", today, balance)

    def register_pnl(self, equity: float) -> None:
        """Recalcula el PnL del día usando equity (NAV) para capturar flotante.

        Pasar ``equity`` (NAV) en lugar de balance para que las pérdidas no
        realizadas también disparen el halt diario.
        """
        if self.state is None:
            return
        self.state.realized_pnl = equity - self.state.starting_balance
        loss_pct = -self.state.realized_pnl / self.state.starting_balance
        if loss_pct >= self.max_daily_loss and not self.state.halted:
            self.state.halted = True
            logger.warning(
                "Pérdida diaria %.2f%% supera el límite %.2f%%. Bot pausado hasta mañana.",
                loss_pct * 100,
                self.max_daily_loss * 100,
            )

    def is_halted(self) -> bool:
        return bool(self.state and self.state.halted)

    # ---------------------------------------------------------------- cooldown
    def mark_trade_closed(self, instrument: str, now: Optional[datetime] = None) -> None:
        if self.state is None:
            return
        self.state.cooldowns[instrument] = now or datetime.now(timezone.utc)

    def detect_closures(self, open_trade_ids: set[str], id_to_instrument: Dict[str, str]) -> None:
        """Detecta trades cerrados desde el último tick y activa su cooldown."""
        # Conservamos el mapeo histórico para resolver el instrumento aunque
        # el trade ya no esté en la lista de abiertos.
        self._trade_instrument_map.update(id_to_instrument)
        previously_known = set(self._trade_instrument_map.keys())
        closed_ids = previously_known & (previously_known - open_trade_ids)
        # Sólo consideramos cerrados los que estaban abiertos en el tick anterior
        # (no los que nunca vimos). Para ello filtramos contra los abiertos actuales.
        truly_closed = {tid for tid in closed_ids if tid not in open_trade_ids}
        for tid in truly_closed:
            instrument = self._trade_instrument_map.pop(tid, None)
            if instrument:
                self.mark_trade_closed(instrument)

    def in_cooldown(self, instrument: str, now: Optional[datetime] = None) -> bool:
        if self.state is None or self.cooldown_seconds <= 0:
            return False
        last = self.state.cooldowns.get(instrument)
        if not last:
            return False
        now = now or datetime.now(timezone.utc)
        return (now - last).total_seconds() < self.cooldown_seconds

    # ---------------------------------------------------------------- sizing
    @staticmethod
    def calculate_position_size(
        balance: float,
        risk_per_trade: float,
        entry_price: float,
        stop_loss: float,
        instrument: str,
        min_units: int = 1,
        max_units: int = 1_000_000,
    ) -> int:
        """Devuelve el número de unidades a operar para arriesgar `risk_per_trade`.

        Para pares en USD (cuenta en USD) el riesgo en USD por unidad es
        |entry - stop_loss|. Para XAU_USD también, ya que se cotiza en USD por
        onza.
        """
        risk_amount = balance * risk_per_trade
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0

        units = risk_amount / stop_distance
        units = round(units, 0)
        units = int(max(min_units, min(units, max_units)))
        return units
