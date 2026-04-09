"""Tests del logger CSV de operaciones."""
from __future__ import annotations

import csv
from pathlib import Path

from src.trade_logger import TradeCSVLogger


def test_creates_file_with_headers(tmp_path: Path):
    path = tmp_path / "trades.csv"
    TradeCSVLogger(path)
    assert path.exists()
    with path.open() as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == TradeCSVLogger.HEADERS


def test_log_entry_appends_row(tmp_path: Path):
    path = tmp_path / "trades.csv"
    logger_ = TradeCSVLogger(path)
    logger_.log_entry(
        instrument="EUR_USD",
        signal="BUY",
        units=10_000,
        entry_price="1.10000",
        stop_loss="1.09850",
        take_profit="1.10250",
        atr="0.00100",
        rsi="32.50",
        adx="28.10",
        spread="0.00010",
        balance="10000.00",
        session="Londres",
        reason="RSI<=35",
        order_id="123",
    )
    with path.open() as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 2  # header + 1 entry
    assert rows[1][TradeCSVLogger.HEADERS.index("instrument")] == "EUR_USD"
    assert rows[1][TradeCSVLogger.HEADERS.index("signal")] == "BUY"
    # timestamp_utc se rellena automáticamente
    assert rows[1][TradeCSVLogger.HEADERS.index("timestamp_utc")] != ""
