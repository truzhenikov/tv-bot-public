from __future__ import annotations

import unittest
from unittest.mock import patch

from utbot.main import _parse_position_sizes, _parse_symbols, _timeframe_to_seconds


class MainTests(unittest.TestCase):
    def test_timeframe_to_seconds(self) -> None:
        self.assertEqual(_timeframe_to_seconds("15m"), 900)
        self.assertEqual(_timeframe_to_seconds("1h"), 3600)

    def test_timeframe_to_seconds_unsupported(self) -> None:
        with self.assertRaises(ValueError):
            _timeframe_to_seconds("1d")

    def test_parse_symbols_default(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            self.assertEqual(_parse_symbols("HYPEUSDT"), ["HYPEUSDT"])

    def test_parse_symbols_list(self) -> None:
        with patch.dict("os.environ", {"BOT_SYMBOLS": " HYPEUSDT,SOLUSDT,HYPEUSDT "}, clear=False):
            self.assertEqual(_parse_symbols("HYPEUSDT"), ["HYPEUSDT", "SOLUSDT"])

    def test_parse_position_sizes(self) -> None:
        with patch.dict("os.environ", {"BOT_POSITION_SIZES": "HYPEUSDT:50,SOLUSDT:20"}, clear=False):
            sizes = _parse_position_sizes(1.0)
        self.assertEqual(sizes["HYPEUSDT"], 50.0)
        self.assertEqual(sizes["SOLUSDT"], 20.0)


if __name__ == "__main__":
    unittest.main()
