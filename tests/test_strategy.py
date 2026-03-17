from __future__ import annotations

from datetime import datetime, timezone
import unittest

from utbot.models import Candle, Direction, StrategyState
from utbot.strategy import UTBotStrategy, last_signal_bias


class StrategyTests(unittest.TestCase):
    def test_last_signal_bias_uses_latest_buy_sell_state(self) -> None:
        ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        states = [
            StrategyState(ts_utc=ts, trailing_stop=1, buy=False, sell=False),
            StrategyState(ts_utc=ts, trailing_stop=1, buy=True, sell=False),
            StrategyState(ts_utc=ts, trailing_stop=1, buy=False, sell=False),
            StrategyState(ts_utc=ts, trailing_stop=1, buy=False, sell=True),
        ]
        self.assertEqual(last_signal_bias(states), Direction.SHORT)

    def test_ut_strategy_evaluate_returns_state_per_candle(self) -> None:
        strategy = UTBotStrategy(key_value=1.0, atr_period=10, use_heikin=False)
        candles = [
            Candle(datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc), 100, 101, 99, 100),
            Candle(datetime(2026, 3, 1, 0, 1, tzinfo=timezone.utc), 100, 102, 99, 101),
            Candle(datetime(2026, 3, 1, 0, 2, tzinfo=timezone.utc), 101, 103, 100, 102),
        ]

        states = strategy.evaluate(candles)
        self.assertEqual(len(states), len(candles))
        self.assertEqual(states[-1].ts_utc, candles[-1].ts_utc)


if __name__ == "__main__":
    unittest.main()
