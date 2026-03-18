from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import SignalEvent


class SignalStore:
    def __init__(self, path: str | Path = "utbot.db") -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_close_ts_utc TEXT NOT NULL,
                htf_bias TEXT,
                ltf_signal TEXT,
                ltf_signal_key TEXT NOT NULL,
                action TEXT NOT NULL,
                action_reason TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                UNIQUE(symbol, timeframe, candle_close_ts_utc, ltf_signal_key)
            );
            """
        )
        self._conn.commit()

    def upsert_event(self, event: SignalEvent) -> bool:
        signal_key = event.ltf_signal.value if event.ltf_signal else "NONE"
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO signal_events (
                symbol, timeframe, candle_close_ts_utc, htf_bias, ltf_signal, ltf_signal_key, action, action_reason, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.symbol,
                event.timeframe,
                event.candle_close_ts_utc.isoformat(),
                event.htf_bias.value if event.htf_bias else None,
                event.ltf_signal.value if event.ltf_signal else None,
                signal_key,
                event.action.value,
                event.action_reason,
                datetime.utcnow().replace(microsecond=0).isoformat(),
            ),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def has_event(self, symbol: str, timeframe: str, candle_close_ts_utc: datetime, ltf_signal: str | None) -> bool:
        signal_key = ltf_signal or "NONE"
        cur = self._conn.execute(
            """
            SELECT 1 FROM signal_events
            WHERE symbol = ? AND timeframe = ? AND candle_close_ts_utc = ? AND ltf_signal_key = ?
            LIMIT 1
            """,
            (symbol, timeframe, candle_close_ts_utc.isoformat(), signal_key),
        )
        return cur.fetchone() is not None

    def close(self) -> None:
        self._conn.close()

    def list_symbols(self) -> list[str]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT symbol
            FROM signal_events
            ORDER BY symbol ASC
            """
        )
        return [row[0] for row in cur.fetchall()]

    def list_events(self, symbol: str | None = None, limit: int = 300) -> list[dict]:
        if limit < 1:
            return []
        if symbol:
            cur = self._conn.execute(
                """
                SELECT symbol, timeframe, candle_close_ts_utc, htf_bias, ltf_signal, action, action_reason, created_at_utc
                FROM signal_events
                WHERE symbol = ?
                ORDER BY candle_close_ts_utc DESC
                LIMIT ?
                """,
                (symbol, limit),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT symbol, timeframe, candle_close_ts_utc, htf_bias, ltf_signal, action, action_reason, created_at_utc
                FROM signal_events
                ORDER BY candle_close_ts_utc DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = cur.fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "symbol": row[0],
                    "timeframe": row[1],
                    "candle_close_ts_utc": row[2],
                    "htf_bias": row[3],
                    "ltf_signal": row[4],
                    "action": row[5],
                    "action_reason": row[6],
                    "created_at_utc": row[7],
                }
            )
        return out
