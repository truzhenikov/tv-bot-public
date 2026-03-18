from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from utbot.models import ActionType, Direction, SignalEvent
from utbot.storage import SignalStore


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.store = SignalStore(Path(self.tmpdir.name) / "db.sqlite")

    def test_list_symbols_and_events(self) -> None:
        ts = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
        ev = SignalEvent(
            symbol="HYPEUSDT",
            timeframe="15m",
            candle_close_ts_utc=ts,
            htf_bias=Direction.LONG,
            ltf_signal=Direction.LONG,
            action=ActionType.OPEN,
            action_reason="open_on_aligned_signal",
        )
        self.assertTrue(self.store.upsert_event(ev))

        symbols = self.store.list_symbols()
        self.assertIn("HYPEUSDT", symbols)

        events = self.store.list_events(symbol="HYPEUSDT", limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["symbol"], "HYPEUSDT")


if __name__ == "__main__":
    unittest.main()
