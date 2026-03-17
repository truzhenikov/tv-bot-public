from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from utbot.exchange import BitmartCredentials, BitmartPerpRestAdapter
from utbot.models import Direction, Position


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ExchangeTests(unittest.TestCase):
    def setUp(self) -> None:
        creds = BitmartCredentials(api_key="k", api_secret="s", api_memo="m")
        self.adapter = BitmartPerpRestAdapter(credentials=creds)

    def test_signed_request_builds_expected_headers(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["headers"] = dict(req.header_items())
            captured["body"] = req.data.decode("utf-8") if req.data else ""
            return _FakeHTTPResponse({"code": 1000, "message": "OK", "data": {"order_id": "1"}})

        with patch("utbot.exchange.time", return_value=1700000000.0), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.adapter._request(
                "POST",
                "/contract/private/submit-order",
                body={"symbol": "SOLUSDT", "side": 1, "type": "market", "mode": 1, "size": 1},
                signed=True,
            )

        body = captured["body"]
        ts = "1700000000000"
        expected_plain = f"{ts}#m#{body}"
        expected_sign = hmac.new(b"s", expected_plain.encode("utf-8"), hashlib.sha256).hexdigest()

        # urllib normalizes header keys to Title-Case.
        self.assertEqual(captured["headers"]["X-bm-key"], "k")
        self.assertEqual(captured["headers"]["X-bm-timestamp"], ts)
        self.assertEqual(captured["headers"]["X-bm-sign"], expected_sign)

    def test_get_position_parses_long(self) -> None:
        with patch.object(
            self.adapter,
            "_request",
            return_value={"code": 1000, "data": [{"current_amount": "3", "position_type": 1}]},
        ):
            pos = self.adapter.get_position("SOLUSDT")

        self.assertEqual(pos, Position(side=Direction.LONG, size=3.0))

    def test_close_position_uses_reduce_side_codes(self) -> None:
        calls = []

        def fake_request(method, path, params=None, body=None, keyed=False, signed=False):
            calls.append({"method": method, "path": path, "params": params, "body": body, "keyed": keyed, "signed": signed})
            if path.endswith("position-v2"):
                return {"code": 1000, "data": [{"current_amount": "2", "position_type": 1}]}
            return {"code": 1000, "data": {"order_id": "abc"}}

        with patch.object(self.adapter, "_request", side_effect=fake_request):
            order_id = self.adapter.close_position("SOLUSDT")

        self.assertEqual(order_id, "abc")
        self.assertEqual(calls[1]["body"]["side"], 3)

    def test_fetch_recent_candles_parses_bitmart_kline(self) -> None:
        payload = {
            "code": 1000,
            "data": [
                {
                    "open_price": "10",
                    "high_price": "11",
                    "low_price": "9",
                    "close_price": "10.5",
                    "timestamp": 1772064000,
                },
                {
                    "open_price": "10.5",
                    "high_price": "12",
                    "low_price": "10",
                    "close_price": "11.5",
                    "timestamp": 1772150400,
                },
            ],
        }
        with patch.object(self.adapter, "_request", return_value=payload):
            candles = self.adapter.fetch_recent_candles("HYPEUSDT", "1d", 15)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].ts_utc, datetime.fromtimestamp(1772064000, tz=timezone.utc))
        self.assertEqual(candles[1].close, 11.5)


if __name__ == "__main__":
    unittest.main()
