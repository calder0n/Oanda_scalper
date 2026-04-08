"""Notificaciones sencillas a Telegram vía Bot API.

Usa únicamente `requests` para evitar añadir dependencias. Si el bot no está
configurado (sin token o sin chat_id) se convierte en un no-op silencioso y los
errores de red se loggean pero **no** interrumpen el trading.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

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
        instruments: list[str],
        granularity: str,
        balance: float,
    ) -> None:
        text = (
            "🟢 <b>Oanda Scalper arrancado</b>\n"
            f"• Entorno: <code>{html.escape(environment)}</code>\n"
            f"• Instrumentos: <code>{html.escape(', '.join(instruments))}</code>\n"
            f"• Velas: <code>{html.escape(granularity)}</code>\n"
            f"• Balance: <b>{balance:,.2f}</b>"
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
        reason: str,
    ) -> None:
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        text = (
            f"{emoji} <b>Entrada {html.escape(side)}</b> en <code>{html.escape(instrument)}</code>\n"
            f"• Unidades: <b>{units:+,}</b>\n"
            f"• Entry: <code>{entry_price:.5f}</code>\n"
            f"• SL: <code>{stop_loss:.5f}</code>\n"
            f"• TP: <code>{take_profit:.5f}</code>\n"
            f"• Motivo: <i>{html.escape(reason)}</i>"
        )
        self.send(text)

    def notify_error(self, message: str) -> None:
        self.send(f"⚠️ <b>Error</b>\n<code>{html.escape(message)}</code>")
