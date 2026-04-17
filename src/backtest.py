"""Backtester vectorial para la estrategia de scalping.

Simula vela a vela contra un DataFrame OHLC con columnas
``open, high, low, close`` indexado por timestamp UTC.

Limitaciones conocidas (asumidas para simplificar):

* Entradas y cierres al precio de ``close`` de la vela de señal / a ``high``/``low``
  si SL o TP se tocan durante la siguiente vela.
* No modela spread variable salvo como un ``spread_ticks`` constante restado del
  R:R (pesimista).
* No modela slippage.
* Un único instrumento por backtest y una operación abierta a la vez.

A pesar de esas simplificaciones es suficiente para comparar variantes de la
estrategia y decidir parámetros antes de poner dinero en la cuenta demo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from .indicators import add_indicators
from .strategy import EvaluationResult, ScalpingStrategy, Signal, TradeSetup

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    side: str
    entry: float
    stop_loss: float
    take_profit: float
    exit_price: float
    pnl_r: float  # pérdida/ganancia en múltiplos de R (riesgo)
    outcome: str  # "TP", "SL", "BE", "TIMEOUT"


@dataclass
class BacktestResult:
    trades: List[BacktestTrade] = field(default_factory=list)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.pnl_r > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.pnl_r < 0)

    @property
    def breakevens(self) -> int:
        return sum(1 for t in self.trades if t.pnl_r == 0)

    @property
    def win_rate(self) -> float:
        n = len(self.trades)
        return (self.wins / n) if n else 0.0

    @property
    def total_r(self) -> float:
        return float(sum(t.pnl_r for t in self.trades))

    @property
    def expectancy_r(self) -> float:
        return (self.total_r / len(self.trades)) if self.trades else 0.0

    def trades_per_day(self) -> float:
        if not self.trades:
            return 0.0
        days = {t.entry_time.date() for t in self.trades}
        return len(self.trades) / max(len(days), 1)

    def summary(self) -> str:
        if not self.trades:
            return "Sin trades generados."
        return (
            f"trades={len(self.trades)} | "
            f"wins={self.wins} | losses={self.losses} | BE={self.breakevens} | "
            f"win_rate={self.win_rate * 100:.1f}% | "
            f"total_R={self.total_r:+.2f} | "
            f"expectancy={self.expectancy_r:+.2f}R | "
            f"trades/día={self.trades_per_day():.1f}"
        )


def _evaluate_at(strategy: ScalpingStrategy, data: pd.DataFrame, i: int) -> Optional[EvaluationResult]:
    """Réplica rápida de ``ScalpingStrategy.evaluate`` sobre datos pre-calculados.

    Importante mantener la lógica sincronizada con ``strategy._trend_pullback_setup``
    y ``strategy._mean_reversion_setup``.
    """
    row = data.iloc[i]
    price = float(row["close"])
    atr_value = float(row["atr"])
    rsi_value = float(row["rsi"])
    adx_value = float(row["adx"])

    if atr_value <= 0:
        return EvaluationResult(price=price, rsi=rsi_value, adx=adx_value, atr=atr_value, setup=None)

    setup: Optional[TradeSetup] = None
    if strategy.mode == "mean_reversion":
        if adx_value >= strategy.min_adx:
            if rsi_value <= strategy.rsi_buy:
                sl = price - strategy.atr_sl_mult * atr_value
                tp = price + strategy.atr_tp_mult * atr_value
                setup = TradeSetup(Signal.BUY, price, sl, tp, atr_value, rsi_value, adx_value, "MR")
            elif rsi_value >= strategy.rsi_sell:
                sl = price + strategy.atr_sl_mult * atr_value
                tp = price - strategy.atr_tp_mult * atr_value
                setup = TradeSetup(Signal.SELL, price, sl, tp, atr_value, rsi_value, adx_value, "MR")
    else:  # trend_pullback
        if adx_value >= strategy.min_adx and i >= strategy.ema_slope_lookback:
            ema_fast_now = float(row["ema_fast"])
            ema_slow_now = float(row["ema_slow"])
            slope = ema_slow_now - float(data.iloc[i - strategy.ema_slope_lookback]["ema_slow"])
            uptrend = ema_fast_now > ema_slow_now and slope > 0
            downtrend = ema_fast_now < ema_slow_now and slope < 0
            lookback = min(strategy.ema_slope_lookback, i)
            recent = data.iloc[i - lookback : i + 1]
            touched_fast = (
                (recent["low"] <= recent["ema_fast"]) & (recent["high"] >= recent["ema_fast"])
            ).any()
            dipped_below = (recent["low"] <= recent["ema_fast"]).any()
            spiked_above = (recent["high"] >= recent["ema_fast"]).any()

            if uptrend and rsi_value <= strategy.rsi_buy and (touched_fast or dipped_below):
                sl = price - strategy.atr_sl_mult * atr_value
                tp = price + strategy.atr_tp_mult * atr_value
                setup = TradeSetup(Signal.BUY, price, sl, tp, atr_value, rsi_value, adx_value, "TP")
            elif downtrend and rsi_value >= strategy.rsi_sell and (touched_fast or spiked_above):
                sl = price + strategy.atr_sl_mult * atr_value
                tp = price - strategy.atr_tp_mult * atr_value
                setup = TradeSetup(Signal.SELL, price, sl, tp, atr_value, rsi_value, adx_value, "TP")

    return EvaluationResult(price=price, rsi=rsi_value, adx=adx_value, atr=atr_value, setup=setup)


def _in_hours(ts: pd.Timestamp, hours: Optional[List[range]]) -> bool:
    if not hours:
        return True
    hour = ts.tz_convert("UTC").hour if ts.tzinfo else ts.hour
    return any(hour in h for h in hours)


def backtest(
    df: pd.DataFrame,
    strategy: ScalpingStrategy,
    session_hours: Optional[List[range]] = None,
    warmup: int = 30,
    max_bars_in_trade: int = 120,
    spread_price: float = 0.0,
    cooldown_bars: int = 5,
    use_breakeven: bool = True,
    be_trigger_r: float = 1.0,
    use_trailing: bool = True,
    trail_atr_mult: float = 1.0,
) -> BacktestResult:
    """Ejecuta la estrategia vela a vela sobre ``df``.

    * ``session_hours``: lista de ``range`` de horas UTC permitidas (ej.
      ``[range(7, 12), range(13, 17)]``).
    * ``cooldown_bars``: barras a esperar antes de volver a disparar después
      de cerrar un trade.
    * ``use_breakeven`` / ``be_trigger_r``: mueve el SL a entry cuando el precio
      alcanza ``be_trigger_r * R`` a favor.
    * ``use_trailing`` / ``trail_atr_mult``: después del BE, arrastra el SL a
      ``close - trail_atr_mult * ATR`` (long) o ``close + trail_atr_mult * ATR``.
    """
    if df.empty or len(df) < warmup + 2:
        return BacktestResult()

    # Pre-calculamos indicadores UNA vez y llamamos a un helper por barra para
    # evitar O(n²). Incluimos EMAs si la estrategia está en modo trend_pullback.
    data = add_indicators(df, strategy.ema_fast, strategy.ema_slow).reset_index()
    data = data.rename(columns={data.columns[0]: "time"}) if "time" not in data.columns else data

    result = BacktestResult()
    i = warmup
    n = len(data)

    while i < n - 1:
        row = data.iloc[i]
        ts = row["time"]
        if isinstance(ts, pd.Timestamp) and _in_hours(ts, session_hours) is False:
            i += 1
            continue
        if any(pd.isna(row[c]) for c in ("rsi", "adx", "atr", "ema_fast", "ema_slow")):
            i += 1
            continue

        eval_result = _evaluate_at(strategy, data, i)
        if eval_result is None or eval_result.setup is None:
            i += 1
            continue

        setup: TradeSetup = eval_result.setup

        # Ajuste pesimista por spread
        if setup.signal == Signal.BUY:
            entry_px = setup.entry_price + spread_price / 2
            sl = setup.stop_loss
            tp = setup.take_profit
        else:
            entry_px = setup.entry_price - spread_price / 2
            sl = setup.stop_loss
            tp = setup.take_profit

        risk = abs(entry_px - sl)
        if risk <= 0:
            i += 1
            continue

        be_trigger_price = (
            entry_px + be_trigger_r * risk
            if setup.signal == Signal.BUY
            else entry_px - be_trigger_r * risk
        )

        # Simulamos vela a vela hasta SL/TP o timeout
        exit_price: Optional[float] = None
        outcome: str = "TIMEOUT"
        exit_idx = i
        current_sl = sl
        be_armed = False
        for j in range(1, max_bars_in_trade + 1):
            if i + j >= n:
                break
            candle = data.iloc[i + j]
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]
            atr_value = candle["atr"] if not pd.isna(candle["atr"]) else setup.atr

            if setup.signal == Signal.BUY:
                # Prioridad pesimista: si vela abarca SL y TP, asumimos SL primero
                if low <= current_sl:
                    exit_price = current_sl
                    outcome = "BE" if be_armed and current_sl >= entry_px else "SL"
                    exit_idx = i + j
                    break
                if high >= tp:
                    exit_price = tp
                    outcome = "TP"
                    exit_idx = i + j
                    break
                if use_breakeven and not be_armed and high >= be_trigger_price:
                    current_sl = max(current_sl, entry_px)
                    be_armed = True
                if use_trailing and be_armed:
                    new_sl = close - trail_atr_mult * atr_value
                    if new_sl > current_sl:
                        current_sl = new_sl
            else:  # SELL
                if high >= current_sl:
                    exit_price = current_sl
                    outcome = "BE" if be_armed and current_sl <= entry_px else "SL"
                    exit_idx = i + j
                    break
                if low <= tp:
                    exit_price = tp
                    outcome = "TP"
                    exit_idx = i + j
                    break
                if use_breakeven and not be_armed and low <= be_trigger_price:
                    current_sl = min(current_sl, entry_px)
                    be_armed = True
                if use_trailing and be_armed:
                    new_sl = close + trail_atr_mult * atr_value
                    if new_sl < current_sl:
                        current_sl = new_sl

        if exit_price is None:
            exit_idx = min(i + max_bars_in_trade, n - 1)
            exit_price = float(data.iloc[exit_idx]["close"])
            outcome = "TIMEOUT"

        pnl_price = (
            exit_price - entry_px if setup.signal == Signal.BUY else entry_px - exit_price
        )
        pnl_r = pnl_price / risk

        result.trades.append(
            BacktestTrade(
                entry_time=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                exit_time=(
                    data.iloc[exit_idx]["time"].to_pydatetime()
                    if hasattr(data.iloc[exit_idx]["time"], "to_pydatetime")
                    else data.iloc[exit_idx]["time"]
                ),
                side=setup.signal.value,
                entry=entry_px,
                stop_loss=sl,
                take_profit=tp,
                exit_price=exit_price,
                pnl_r=pnl_r,
                outcome=outcome,
            )
        )

        i = exit_idx + cooldown_bars

    return result


# ---------------------------------------------------------------- generadores
def synthetic_ohlc(
    n: int = 5000,
    seed: int = 0,
    start_price: float = 1.1000,
    vol: float = 0.0004,
    drift: float = 0.0,
    freq: str = "1min",
) -> pd.DataFrame:
    """Genera una serie OHLC sintética tipo forex M1 (random-walk con ruido)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, size=n)
    close = start_price * np.exp(np.cumsum(returns))
    noise_high = rng.uniform(0.0, vol * start_price, size=n)
    noise_low = rng.uniform(0.0, vol * start_price, size=n)
    open_ = np.concatenate([[start_price], close[:-1]])
    high = np.maximum(open_, close) + noise_high
    low = np.minimum(open_, close) - noise_low
    index = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


if __name__ == "__main__":
    # Demo rápida con datos sintéticos
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = synthetic_ohlc(n=10_000, seed=7, vol=0.0006)
    strat = ScalpingStrategy()
    res = backtest(df, strat)
    logger.info("Baseline | %s", res.summary())
