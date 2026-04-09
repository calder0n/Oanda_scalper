"""Detector de sesiones de trading.

Las sesiones se definen en horas UTC. Por defecto se incluyen Londres y
Nueva York, que son las dos ventanas de mayor liquidez para EUR_USD y
XAU_USD. Se puede sobreescribir desde la variable de entorno
``SESSIONS_UTC`` con formato ``Londres:7-12,NewYork:13-17``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class TradingSession:
    name: str
    start_hour_utc: int  # inclusivo
    end_hour_utc: int    # exclusivo

    def contains(self, dt: datetime) -> bool:
        hour = dt.astimezone(timezone.utc).hour
        return self.start_hour_utc <= hour < self.end_hour_utc

    def label(self) -> str:
        return f"{self.name} ({self.start_hour_utc:02d}-{self.end_hour_utc:02d} UTC)"


DEFAULT_SESSIONS: List[TradingSession] = [
    TradingSession("Londres", 7, 12),
    TradingSession("Nueva York", 13, 17),
]


def parse_sessions(spec: str) -> List[TradingSession]:
    """Parsea ``Londres:7-12,NewYork:13-17`` en una lista de sesiones."""
    if not spec or not spec.strip():
        return list(DEFAULT_SESSIONS)
    sessions: List[TradingSession] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk or "-" not in chunk:
            raise ValueError(f"Sesión inválida: {chunk!r}. Formato esperado 'Nombre:H-H'.")
        name, hours = chunk.split(":", 1)
        start_str, end_str = hours.split("-", 1)
        sessions.append(
            TradingSession(
                name=name.strip(),
                start_hour_utc=int(start_str),
                end_hour_utc=int(end_str),
            )
        )
    return sessions or list(DEFAULT_SESSIONS)


def current_session(
    now: Optional[datetime] = None,
    sessions: Optional[List[TradingSession]] = None,
) -> Optional[TradingSession]:
    now = now or datetime.now(timezone.utc)
    for session in sessions or DEFAULT_SESSIONS:
        if session.contains(now):
            return session
    return None
