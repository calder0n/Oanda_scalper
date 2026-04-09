"""Notificaciones a Telegram vía Bot API.

Usa únicamente `requests` para evitar añadir dependencias. Si el bot no está
configurado (sin token o sin chat_id) se convierte en un no-op silencioso y
los errores de red se loggean pero **no** interrumpen el trading.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str],
        chat_id: Optional[str],
        timeout: float = 5.0,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.enabled = bool(token and chat_id)
        if not self.enabled:
            logger.info("Telegram desactivado (falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")

    def send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            response = requests.post(
                _API_URL.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout,
            )
            if response.status_code != 200:
                logger.warning(
                    "Telegram respondió %s: %s", response.status_code, response.text
                )
        except requests.RequestException as exc:
            logger.warning("No se pudo enviar mensaje a Telegram: %s", exc)

    # ------------------------------------------------------------------ helpers
    def notify_startup(
        self,
        environment: str,
        instruments: List[str],
        granularity: str,
        balance: float,
        sessions_label: str,
    ) -> None:
        text = (
            "🟢 <b>Oanda Scalper arrancado</b>\n"
            f"• Entorno: <code>{html.escape(environment)}</code>\n"
            f"• Instrumentos: <code>{html.escape(', '.join(instruments))}</code>\n"
            f"• Velas: <code>{html.escape(granularity)}</code>\n"
            f"• Sesiones: <code>{html.escape(sessions_label)}</code>\n"
            f"• Balance: <b>{balance:,.2f}</b>"
        )
        self.send(text)

    def notify_session_start(
        self,
        session_name: str,
        start_hour: int,
        end_hour: int,
        instruments: List[str],
        balance: float,
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = (
            "📈 <b>Sesión abierta</b>\n"
            f"• Sesión: <b>{html.escape(session_name)}</b>\n"
            f"• Horario: <code>{start_hour:02d}:00 - {end_hour:02d}:00 UTC</code>\n"
            f"• Hora actual: <code>{now}</code>\n"
            f"• Instrumentos: <code>{html.escape(', '.join(instruments))}</code>\n"
            f"• Balance: <b>{balance:,.2f}</b>\n"
            "Comenzando a operar…"
        )
        self.send(text)

    def notify_session_end(self, session_name: str, balance: float) -> None:
        text = (
            "🌙 <b>Sesión cerrada</b>\n"
            f"• Sesión: <b>{html.escape(session_name)}</b>\n"
            f"• Balance: <b>{balance:,.2f}</b>\n"
            "Bot en pausa hasta la siguiente sesión."
        )
        self.send(text)

    def notify_entry(
        self,
        instrument: str,
        side: str,
        units: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        atr: float,
        rsi: float,
        adx: float,
        spread: float,
        balance: float,
        session: str,
        reason: str,
        order_id: str = "",
    ) -> None:
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        risk_pips = abs(entry_price - stop_loss)
        reward_pips = abs(take_profit - entry_price)
        rr = reward_pips / risk_pips if risk_pips else 0.0
        text = (
            f"{emoji} <b>Entrada {html.escape(side)}</b> — <code>{html.escape(instrument)}</code>\n"
            f"• Sesión: <b>{html.escape(session)}</b>\n"
            f"• Unidades: <b>{units:+,}</b>\n"
            f"• Entry: <code>{entry_price:.5f}</code>\n"
            f"• SL: <code>{stop_loss:.5f}</code>  (riesgo {risk_pips:.5f})\n"
            f"• TP: <code>{take_profit:.5f}</code>  (objetivo {reward_pips:.5f})\n"
            f"• R:R: <b>1:{rr:.2f}</b>\n"
            "—— <b>Indicadores</b> ——\n"
            f"• RSI(14): <b>{rsi:.2f}</b>\n"
            f"• ADX(14): <b>{adx:.2f}</b>\n"
            f"• ATR(14): <code>{atr:.5f}</code>\n"
            f"• Spread: <code>{spread:.5f}</code> (límite {atr * 0.15:.5f})\n"
            f"• Balance: <b>{balance:,.2f}</b>\n"
            f"• Decisión: <i>{html.escape(reason)}</i>"
            + (f"\n• Order ID: <code>{html.escape(str(order_id))}</code>" if order_id else "")
        )
        self.send(text)

    def notify_error(self, message: str) -> None:
        self.send(f"⚠️ <b>Error</b>\n<code>{html.escape(message)}</code>")
