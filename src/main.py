"""Punto de entrada del bot."""
from __future__ import annotations

import logging

from .config import Config
from .trader import Trader


def main() -> None:
    config = Config()
    config.configure_logging()
    logger = logging.getLogger("oanda_scalper")
    logger.info("Cargando configuración…")
    Trader(config).run()


if __name__ == "__main__":
    main()
