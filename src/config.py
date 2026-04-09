"""Configuración del bot cargada desde variables de entorno."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"La variable de entorno {name} es obligatoria")
    return value  # type: ignore[return-value]


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: _get_env("OANDA_API_KEY", required=True))
    account_id: str = field(default_factory=lambda: _get_env("OANDA_ACCOUNT_ID", required=True))
    environment: str = field(default_factory=lambda: _get_env("OANDA_ENVIRONMENT", "practice"))

    instruments: List[str] = field(
        default_factory=lambda: [
            i.strip() for i in _get_env("INSTRUMENTS", "XAU_USD,EUR_USD").split(",") if i.strip()
        ]
    )
    granularity: str = field(default_factory=lambda: _get_env("GRANULARITY", "M1"))

    risk_per_trade: float = field(default_factory=lambda: float(_get_env("RISK_PER_TRADE", "0.01")))
    max_concurrent_trades: int = field(
        default_factory=lambda: int(_get_env("MAX_CONCURRENT_TRADES", "2"))
    )
    max_daily_loss: float = field(default_factory=lambda: float(_get_env("MAX_DAILY_LOSS", "0.05")))
    atr_sl_mult: float = field(default_factory=lambda: float(_get_env("ATR_SL_MULT", "1.5")))
    atr_tp_mult: float = field(default_factory=lambda: float(_get_env("ATR_TP_MULT", "2.5")))

    # Filtros de la estrategia
    min_adx: float = field(default_factory=lambda: float(_get_env("MIN_ADX", "25")))
    rsi_buy_threshold: float = field(
        default_factory=lambda: float(_get_env("RSI_BUY_THRESHOLD", "35"))
    )
    rsi_sell_threshold: float = field(
        default_factory=lambda: float(_get_env("RSI_SELL_THRESHOLD", "60"))
    )
    spread_atr_ratio: float = field(
        default_factory=lambda: float(_get_env("SPREAD_ATR_RATIO", "0.15"))
    )
    sessions_spec: str = field(
        default_factory=lambda: _get_env("SESSIONS_UTC", "Londres:7-12,Nueva York:13-17")
    )

    loop_interval: int = field(default_factory=lambda: int(_get_env("LOOP_INTERVAL", "20")))
    log_level: str = field(default_factory=lambda: _get_env("LOG_LEVEL", "INFO"))

    telegram_bot_token: str = field(
        default_factory=lambda: _get_env("TELEGRAM_BOT_TOKEN", "") or ""
    )
    telegram_chat_id: str = field(
        default_factory=lambda: _get_env("TELEGRAM_CHAT_ID", "") or ""
    )

    trade_log_path: str = field(
        default_factory=lambda: _get_env("TRADE_LOG_PATH", "/app/logs/trades.csv")
    )

    candles_count: int = 200  # número de velas históricas para los indicadores

    def configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
