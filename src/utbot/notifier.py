from __future__ import annotations

import json
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod


class Notifier(ABC):
    @abstractmethod
    def send(self, text: str) -> None:
        raise NotImplementedError


class NullNotifier(Notifier):
    def send(self, text: str) -> None:
        _ = text


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: float = 10.0) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Telegram send failed: {exc}") from exc

        if not payload.get("ok", False):
            raise RuntimeError(f"Telegram API error: {payload}")
