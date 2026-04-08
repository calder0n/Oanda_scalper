"""Cálculo de tamaño de posición y control de drawdown diario."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    day: str
    starting_balance: float
    realized_pnl: float = 0.0
    halted: bool = False


class RiskManager:
    def __init__(self, max_daily_loss: float = 0.05) -> None:
        self.max_daily_loss = max_daily_loss
        self.state: RiskState | None = None

    def update_day(self, balance: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state is None or self.state.day != today:
            self.state = RiskState(day=today, starting_balance=balance)
            logger.info("Nuevo día de trading %s | balance inicial=%.2f", today, balance)

    def register_pnl(self, balance: float) -> None:
        """Recalcula el PnL del día comparando con el balance inicial."""
        if self.state is None:
            return
        self.state.realized_pnl = balance - self.state.starting_balance
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
        onza. Es una aproximación suficiente para una cuenta demo.
        """
        risk_amount = balance * risk_per_trade
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0

        units = risk_amount / stop_distance

        # Redondeo razonable según el tipo de instrumento
        if instrument.startswith("XAU"):
            units = round(units, 0)  # Onzas enteras
        else:
            units = round(units, 0)  # Unidades enteras de la divisa base

        units = int(max(min_units, min(units, max_units)))
        return units
