from __future__ import annotations

import unittest

from utbot.main import _timeframe_to_seconds


class MainTests(unittest.TestCase):
    def test_timeframe_to_seconds(self) -> None:
        self.assertEqual(_timeframe_to_seconds("15m"), 900)
        self.assertEqual(_timeframe_to_seconds("1h"), 3600)

    def test_timeframe_to_seconds_unsupported(self) -> None:
        with self.assertRaises(ValueError):
            _timeframe_to_seconds("1d")


if __name__ == "__main__":
    unittest.main()
