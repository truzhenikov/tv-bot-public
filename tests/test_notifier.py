from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from utbot.notifier import TelegramNotifier


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class NotifierTests(unittest.TestCase):
    def test_telegram_notifier_posts_send_message(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = req.data.decode("utf-8") if req.data else ""
            return _FakeHTTPResponse({"ok": True, "result": {"message_id": 1}})

        notifier = TelegramNotifier(bot_token="123:abc", chat_id="456")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            notifier.send("hello")

        self.assertEqual(captured["url"], "https://api.telegram.org/bot123:abc/sendMessage")
        self.assertIn("chat_id=456", captured["body"])
        self.assertIn("text=hello", captured["body"])


if __name__ == "__main__":
    unittest.main()
