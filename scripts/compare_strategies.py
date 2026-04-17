"""Compara variantes de la estrategia sobre varios escenarios sintéticos.

Ejecutar desde la raíz del repo:

    PYTHONPATH=. python scripts/compare_strategies.py

Se usan seeds fijas para que los resultados sean reproducibles. El objetivo
NO es predecir el P&L real, sino comparar de forma relativa diferentes
configuraciones sobre escenarios trending / ranging / mixtos.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import List

import numpy as np
import pandas as pd

from src.backtest import backtest, synthetic_ohlc
from src.strategy import ScalpingStrategy

logger = logging.getLogger("compare")


def scenario_trending(n: int = 8_000, seed: int = 1) -> pd.DataFrame:
    return synthetic_ohlc(n=n, seed=seed, vol=0.0004, drift=0.00005)


def scenario_ranging(n: int = 8_000, seed: int = 2) -> pd.DataFrame:
    # Sin deriva y vol moderada → rango
    return synthetic_ohlc(n=n, seed=seed, vol=0.0005, drift=0.0)


def scenario_choppy(n: int = 8_000, seed: int = 3) -> pd.DataFrame:
    return synthetic_ohlc(n=n, seed=seed, vol=0.0009, drift=0.0)


SCENARIOS = {
    "trending": scenario_trending(),
    "ranging": scenario_ranging(),
    "choppy": scenario_choppy(),
}


def run_variant(label: str, strategy: ScalpingStrategy, **backtest_kwargs) -> None:
    print(f"\n=== {label} ===")
    for name, df in SCENARIOS.items():
        res = backtest(df, strategy, **backtest_kwargs)
        print(f"  [{name:9}] {res.summary()}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # -------------------------------------------------------------- Baseline
    baseline = ScalpingStrategy(
        atr_sl_mult=1.5,
        atr_tp_mult=2.5,
        min_adx=25,
        rsi_buy_threshold=35,
        rsi_sell_threshold=60,
    )
    run_variant(
        "Baseline (mean-reversion + ADX>25 + RSI 35/60, sin BE/trail)",
        baseline,
        use_breakeven=False,
        use_trailing=False,
    )

    # -------------------------------------------------------------- RSI simétrico
    symmetric = ScalpingStrategy(
        atr_sl_mult=1.5,
        atr_tp_mult=2.5,
        min_adx=25,
        rsi_buy_threshold=30,
        rsi_sell_threshold=70,
    )
    run_variant(
        "RSI 30/70 simétrico (sin BE/trail)",
        symmetric,
        use_breakeven=False,
        use_trailing=False,
    )

    # -------------------------------------------------------------- Pro-trend pullback
    pro_trend = ScalpingStrategy(
        atr_sl_mult=1.2,
        atr_tp_mult=2.0,
        min_adx=20,
        rsi_buy_threshold=40,
        rsi_sell_threshold=60,
        mode="trend_pullback",
        ema_fast=20,
        ema_slow=50,
    )
    run_variant(
        "Trend-pullback (EMA20/50 + RSI pullback 40/60) + BE@1R + trailing",
        pro_trend,
        use_breakeven=True,
        be_trigger_r=1.0,
        use_trailing=True,
        trail_atr_mult=1.2,
    )


if __name__ == "__main__":
    main()
