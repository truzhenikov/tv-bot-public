from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import time
from typing import Iterable, Optional

from .config import BotConfig
from .exchange import ExchangeAdapter
from .models import ActionType, Candle, Direction, SignalEvent, StrategyState
from .storage import SignalStore
from .strategy import UTBotStrategy


@dataclass(frozen=True)
class EngineResult:
    events: list[SignalEvent]


class StrategyEngine:
    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeAdapter,
        store: SignalStore,
        strategy: UTBotStrategy,
    ) -> None:
        config.validate()
        self.config = config
        self.exchange = exchange
        self.store = store
        self.strategy = strategy

    def run(self, htf_candles: Iterable[Candle], ltf_candles: Iterable[Candle]) -> EngineResult:
        htf_states = self.strategy.evaluate(htf_candles)
        ltf_states = self.strategy.evaluate(ltf_candles)
        if not ltf_states:
            return EngineResult(events=[])

        events: list[SignalEvent] = []
        # Process a short tail of most recent closed candles to avoid missing a signal
        # when a cycle was delayed (network/API hiccup), while still preventing replay
        # via store.has_event/upsert uniqueness.
        try:
            tail = int(os.getenv('BOT_LTF_CATCHUP_CANDLES', '3'))
        except Exception:
            tail = 3
        if tail < 1:
            tail = 1
        for state in ltf_states[-tail:]:
            ltf_signal = _state_signal(state)
            if ltf_signal is None:
                continue

            if self.store.has_event(
                self.config.symbol,
                self.config.ltf_timeframe,
                state.ts_utc,
                ltf_signal.value,
            ):
                continue

            htf_bias = _bias_at(htf_states, state.ts_utc)
            action, reason = self._decide_action(htf_bias, ltf_signal)

            event = SignalEvent(
                symbol=self.config.symbol,
                timeframe=self.config.ltf_timeframe,
                candle_close_ts_utc=state.ts_utc,
                htf_bias=htf_bias,
                ltf_signal=ltf_signal,
                action=action,
                action_reason=reason,
            )
            if self.store.upsert_event(event):
                events.append(event)
        return EngineResult(events=events)

    def _exec_retries(self) -> int:
        try:
            n = int(os.getenv("BOT_ORDER_RETRIES", "3"))
        except Exception:
            n = 3
        return max(1, n)

    def _verify_delay_sec(self) -> float:
        try:
            v = float(os.getenv("BOT_ORDER_VERIFY_DELAY_SEC", "1.5"))
        except Exception:
            v = 1.5
        return max(0.1, v)

    def _close_and_verify(self) -> bool:
        retries = self._exec_retries()
        delay = self._verify_delay_sec()
        for _ in range(retries):
            self.exchange.close_position(self.config.symbol)
            time.sleep(delay)
            pos = self.exchange.get_position(self.config.symbol)
            if pos is None:
                return True
        return False

    def _open_and_verify(self, side: Direction) -> bool:
        retries = self._exec_retries()
        delay = self._verify_delay_sec()
        for _ in range(retries):
            self.exchange.place_market_order(self.config.symbol, side, self.config.position_size)
            time.sleep(delay)
            pos = self.exchange.get_position(self.config.symbol)
            if pos is not None and pos.side == side:
                return True
        return False

    def _decide_action(self, htf_bias: Optional[Direction], ltf_signal: Direction) -> tuple[ActionType, str]:
        position = self.exchange.get_position(self.config.symbol)

        if htf_bias is None:
            return ActionType.SKIP, "skip_no_htf_bias"

        if ltf_signal != htf_bias:
            if position is None:
                return ActionType.SKIP, "skip_counter_signal_no_position"
            if self._close_and_verify():
                return ActionType.CLOSE, "close_on_counter_ltf_signal"
            return ActionType.SKIP, "close_failed_not_verified"

        if position is None:
            if self._open_and_verify(ltf_signal):
                return ActionType.OPEN, "open_on_aligned_signal"
            return ActionType.SKIP, "open_failed_not_verified"

        if position.side == ltf_signal:
            return ActionType.SKIP, "skip_same_side_position"

        if not self._close_and_verify():
            return ActionType.SKIP, "flip_close_failed_not_verified"
        if self._open_and_verify(ltf_signal):
            return ActionType.OPEN, "close_opposite_then_open_aligned"
        return ActionType.SKIP, "flip_open_failed_not_verified"


def _state_signal(state: StrategyState) -> Optional[Direction]:
    if state.buy:
        return Direction.LONG
    if state.sell:
        return Direction.SHORT
    return None


def _bias_at(htf_states: Iterable[StrategyState], ts: datetime) -> Optional[Direction]:
    bias: Optional[Direction] = None
    for s in htf_states:
        if s.ts_utc > ts:
            break
        if s.buy:
            bias = Direction.LONG
        elif s.sell:
            bias = Direction.SHORT
    return bias
