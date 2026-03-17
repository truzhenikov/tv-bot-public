from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ActionType(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Candle:
    ts_utc: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class StrategyState:
    ts_utc: datetime
    trailing_stop: float
    buy: bool
    sell: bool


@dataclass(frozen=True)
class Position:
    side: Direction
    size: float


@dataclass(frozen=True)
class SignalEvent:
    symbol: str
    timeframe: str
    candle_close_ts_utc: datetime
    htf_bias: Optional[Direction]
    ltf_signal: Optional[Direction]
    action: ActionType
    action_reason: str
