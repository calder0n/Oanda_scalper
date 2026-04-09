"""Persistencia de las operaciones a un fichero CSV.

El fichero se monta dentro del contenedor en ``/app/logs/trades.csv`` y se
expone al host vía el volumen ``./logs:/app/logs`` definido en
``docker-compose.yml``. Cada entrada se escribe como una nueva línea con la
totalidad de los valores que dispararon la decisión.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TradeCSVLogger:
    HEADERS = [
        "timestamp_utc",
        "session",
        "instrument",
        "signal",
        "units",
        "entry_price",
        "stop_loss",
        "take_profit",
        "atr",
        "rsi",
        "adx",
        "spread",
        "balance",
        "reason",
        "order_id",
    ]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(self.HEADERS)
            logger.info("Inicializado fichero de trades en %s", self.path)

    def log_entry(self, **fields: Any) -> None:
        row: Dict[str, Any] = {h: "" for h in self.HEADERS}
        row.update(fields)
        if not row["timestamp_utc"]:
            row["timestamp_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self.path.open("a", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow([row[h] for h in self.HEADERS])
        except OSError as exc:
            logger.warning("No se pudo escribir en %s: %s", self.path, exc)
