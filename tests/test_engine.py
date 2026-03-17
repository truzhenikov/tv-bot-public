from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from utbot.config import BotConfig
from utbot.engine import StrategyEngine, _bias_at
from utbot.exchange import InMemoryBitmartPerpAdapter
from utbot.models import Candle, Direction, StrategyState
from utbot.storage import SignalStore


@dataclass
class FakeStrategy:
    result_sets: list[list[StrategyState]]

    def evaluate(self, candles):
        return self.result_sets.pop(0)


def _ts(day: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, 0, minute, tzinfo=timezone.utc)


def _candle(ts: datetime) -> Candle:
    return Candle(ts_utc=ts, open=100, high=101, low=99, close=100)


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def _store(self, name: str) -> SignalStore:
        return SignalStore(Path(self.tmpdir.name) / name)

    def test_bias_updates_only_on_new_signal_and_persists(self) -> None:
        htf_states = [
            StrategyState(ts_utc=_ts(1), trailing_stop=0, buy=True, sell=False),
            StrategyState(ts_utc=_ts(2), trailing_stop=0, buy=False, sell=False),
            StrategyState(ts_utc=_ts(3), trailing_stop=0, buy=False, sell=True),
        ]

        self.assertEqual(_bias_at(htf_states, _ts(1, 1)), Direction.LONG)
        self.assertEqual(_bias_at(htf_states, _ts(2, 30)), Direction.LONG)
        self.assertEqual(_bias_at(htf_states, _ts(3, 1)), Direction.SHORT)

    def test_open_when_ltf_signal_matches_htf_bias(self) -> None:
        cfg = BotConfig(symbol="SOLUSDT", ltf_timeframe="15m", position_size=2)
        exchange = InMemoryBitmartPerpAdapter()
        store = self._store("test1.db")

        htf = [StrategyState(ts_utc=_ts(1), trailing_stop=0, buy=True, sell=False)]
        ltf = [StrategyState(ts_utc=_ts(1, 15), trailing_stop=0, buy=True, sell=False)]
        strategy = FakeStrategy([htf, ltf])

        engine = StrategyEngine(cfg, exchange, store, strategy)  # type: ignore[arg-type]
        result = engine.run([_candle(_ts(1))], [_candle(_ts(1, 15))])

        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].action.value, "OPEN")
        pos = exchange.get_position("SOLUSDT")
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertEqual(pos.side, Direction.LONG)
        self.assertEqual(pos.size, 2)

    def test_counter_signal_closes_only(self) -> None:
        cfg = BotConfig(symbol="SOLUSDT", ltf_timeframe="15m", position_size=1)
        exchange = InMemoryBitmartPerpAdapter()
        exchange.place_market_order("SOLUSDT", Direction.LONG, 1)
        store = self._store("test2.db")

        htf = [StrategyState(ts_utc=_ts(1), trailing_stop=0, buy=True, sell=False)]
        ltf = [StrategyState(ts_utc=_ts(1, 30), trailing_stop=0, buy=False, sell=True)]
        strategy = FakeStrategy([htf, ltf])

        engine = StrategyEngine(cfg, exchange, store, strategy)  # type: ignore[arg-type]
        result = engine.run([_candle(_ts(1))], [_candle(_ts(1, 30))])

        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].action.value, "CLOSE")
        self.assertIsNone(exchange.get_position("SOLUSDT"))

    def test_htf_flip_does_not_force_close_without_ltf_signal(self) -> None:
        cfg = BotConfig(symbol="SOLUSDT", ltf_timeframe="15m", position_size=1)
        exchange = InMemoryBitmartPerpAdapter()
        exchange.place_market_order("SOLUSDT", Direction.LONG, 1)
        store = self._store("test3.db")

        htf = [
            StrategyState(ts_utc=_ts(1), trailing_stop=0, buy=True, sell=False),
            StrategyState(ts_utc=_ts(2), trailing_stop=0, buy=False, sell=True),
        ]
        ltf = [
            StrategyState(ts_utc=_ts(2, 15), trailing_stop=0, buy=False, sell=False),
            StrategyState(ts_utc=_ts(2, 30), trailing_stop=0, buy=False, sell=False),
        ]
        strategy = FakeStrategy([htf, ltf])

        engine = StrategyEngine(cfg, exchange, store, strategy)  # type: ignore[arg-type]
        result = engine.run([_candle(_ts(1)), _candle(_ts(2))], [_candle(_ts(2, 15)), _candle(_ts(2, 30))])

        self.assertEqual(result.events, [])
        pos = exchange.get_position("SOLUSDT")
        self.assertIsNotNone(pos)
        assert pos is not None
        self.assertEqual(pos.side, Direction.LONG)

    def test_dedup_skips_repeated_ltf_signal_on_same_candle(self) -> None:
        cfg = BotConfig(symbol="SOLUSDT", ltf_timeframe="15m", position_size=1)
        exchange = InMemoryBitmartPerpAdapter()
        store = self._store("test4.db")

        htf = [StrategyState(ts_utc=_ts(1), trailing_stop=0, buy=True, sell=False)]
        ltf = [StrategyState(ts_utc=_ts(1, 45), trailing_stop=0, buy=True, sell=False)]
        strategy = FakeStrategy([htf, ltf])

        engine = StrategyEngine(cfg, exchange, store, strategy)  # type: ignore[arg-type]
        result1 = engine.run([_candle(_ts(1))], [_candle(_ts(1, 45))])

        strategy2 = FakeStrategy([[*htf], [*ltf]])
        engine2 = StrategyEngine(cfg, exchange, store, strategy2)  # type: ignore[arg-type]
        result2 = engine2.run([_candle(_ts(1))], [_candle(_ts(1, 45))])

        self.assertEqual(len(result1.events), 1)
        self.assertEqual(result2.events, [])


if __name__ == "__main__":
    unittest.main()
