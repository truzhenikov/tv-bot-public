from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        # Live safety: evaluate only the latest closed LTF candle to avoid replaying
        # historical trades at process startup.
        for state in ltf_states[-1:]:
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

    def _decide_action(self, htf_bias: Optional[Direction], ltf_signal: Direction) -> tuple[ActionType, str]:
        position = self.exchange.get_position(self.config.symbol)

        if htf_bias is None:
            return ActionType.SKIP, "skip_no_htf_bias"

        if ltf_signal != htf_bias:
            if position is None:
                return ActionType.SKIP, "skip_counter_signal_no_position"
            self.exchange.close_position(self.config.symbol)
            return ActionType.CLOSE, "close_on_counter_ltf_signal"

        if position is None:
            self.exchange.place_market_order(self.config.symbol, ltf_signal, self.config.position_size)
            return ActionType.OPEN, "open_on_aligned_signal"

        if position.side == ltf_signal:
            return ActionType.SKIP, "skip_same_side_position"

        self.exchange.close_position(self.config.symbol)
        self.exchange.place_market_order(self.config.symbol, ltf_signal, self.config.position_size)
        return ActionType.OPEN, "close_opposite_then_open_aligned"


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
