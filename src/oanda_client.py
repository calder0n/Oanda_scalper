"""Wrapper alrededor de oandapyV20 con las llamadas que necesita el bot."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from oandapyV20 import API
from oandapyV20.endpoints import accounts, instruments, orders, positions, pricing, trades
from oandapyV20.exceptions import V20Error

logger = logging.getLogger(__name__)


class OandaClient:
    """Cliente fino sobre la API REST de OANDA."""

    def __init__(self, api_key: str, account_id: str, environment: str = "practice") -> None:
        self.account_id = account_id
        self.client = API(access_token=api_key, environment=environment)

    # ------------------------------------------------------------------ Cuenta
    def get_account_summary(self) -> Dict[str, Any]:
        request = accounts.AccountSummary(accountID=self.account_id)
        self.client.request(request)
        return request.response["account"]

    def get_balance(self) -> float:
        return float(self.get_account_summary()["balance"])

    def get_nav(self) -> float:
        return float(self.get_account_summary()["NAV"])

    def get_open_trades(self) -> List[Dict[str, Any]]:
        request = trades.OpenTrades(accountID=self.account_id)
        self.client.request(request)
        return request.response.get("trades", [])

    def get_open_positions(self) -> List[Dict[str, Any]]:
        request = positions.OpenPositions(accountID=self.account_id)
        self.client.request(request)
        return request.response.get("positions", [])

    # ----------------------------------------------------------------- Velas
    def get_candles(
        self, instrument: str, granularity: str = "M1", count: int = 200
    ) -> pd.DataFrame:
        params = {"granularity": granularity, "count": count, "price": "M"}
        request = instruments.InstrumentsCandles(instrument=instrument, params=params)
        self.client.request(request)
        candles = request.response.get("candles", [])

        rows = []
        for candle in candles:
            if not candle.get("complete", False):
                continue
            mid = candle["mid"]
            rows.append(
                {
                    "time": pd.to_datetime(candle["time"]),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(candle.get("volume", 0)),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("time", inplace=True)
        return df

    # ----------------------------------------------------------------- Precios
    def get_current_price(self, instrument: str) -> Dict[str, float]:
        params = {"instruments": instrument}
        request = pricing.PricingInfo(accountID=self.account_id, params=params)
        self.client.request(request)
        price_info = request.response["prices"][0]
        return {
            "bid": float(price_info["bids"][0]["price"]),
            "ask": float(price_info["asks"][0]["price"]),
            "spread": float(price_info["asks"][0]["price"]) - float(price_info["bids"][0]["price"]),
        }

    # ------------------------------------------------------------------ Instrumento
    def get_instrument_details(self, instrument: str) -> Dict[str, Any]:
        request = accounts.AccountInstruments(
            accountID=self.account_id, params={"instruments": instrument}
        )
        self.client.request(request)
        items = request.response.get("instruments", [])
        if not items:
            raise ValueError(f"Instrumento {instrument} no disponible en la cuenta")
        return items[0]

    # ------------------------------------------------------------------ Órdenes
    def create_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        precision: int = 5,
    ) -> Dict[str, Any]:
        order: Dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order["order"]["stopLossOnFill"] = {
                "price": f"{stop_loss:.{precision}f}",
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order["order"]["takeProfitOnFill"] = {
                "price": f"{take_profit:.{precision}f}",
                "timeInForce": "GTC",
            }
        try:
            request = orders.OrderCreate(accountID=self.account_id, data=order)
            self.client.request(request)
            return request.response
        except V20Error as exc:
            logger.error("Error al crear orden de mercado en %s: %s", instrument, exc)
            raise

    def close_trade(self, trade_id: str) -> Dict[str, Any]:
        request = trades.TradeClose(accountID=self.account_id, tradeID=trade_id)
        self.client.request(request)
        return request.response
