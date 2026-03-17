from __future__ import annotations

from typing import Iterable, Optional

from .models import Candle, Direction, StrategyState


def _true_range(current: Candle, prev_close: float) -> float:
    return max(
        current.high - current.low,
        abs(current.high - prev_close),
        abs(current.low - prev_close),
    )


def _heikin_ashi_close_series(candles: list[Candle]) -> list[float]:
    if not candles:
        return []

    ha_close: list[float] = []
    prev_ha_open = (candles[0].open + candles[0].close) / 2
    prev_ha_close = (candles[0].open + candles[0].high + candles[0].low + candles[0].close) / 4

    for idx, c in enumerate(candles):
        cur_ha_close = (c.open + c.high + c.low + c.close) / 4
        if idx == 0:
            cur_ha_open = prev_ha_open
        else:
            cur_ha_open = (prev_ha_open + prev_ha_close) / 2
        prev_ha_open = cur_ha_open
        prev_ha_close = cur_ha_close
        ha_close.append(cur_ha_close)
    return ha_close


class UTBotStrategy:
    def __init__(self, key_value: float = 1.0, atr_period: int = 10, use_heikin: bool = False):
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        self.key_value = key_value
        self.atr_period = atr_period
        self.use_heikin = use_heikin

    def evaluate(self, candles: Iterable[Candle]) -> list[StrategyState]:
        seq = list(candles)
        if not seq:
            return []

        source_close = _heikin_ashi_close_series(seq) if self.use_heikin else [c.close for c in seq]
        states: list[StrategyState] = []

        atr: Optional[float] = None
        trailing_stop = 0.0
        prev_stop = 0.0
        prev_src = source_close[0]

        for i, candle in enumerate(seq):
            src = source_close[i]
            if i == 0:
                tr = candle.high - candle.low
            else:
                tr = _true_range(candle, seq[i - 1].close)

            if atr is None:
                atr = tr
            else:
                atr = (atr * (self.atr_period - 1) + tr) / self.atr_period

            n_loss = self.key_value * atr

            if src > prev_stop and prev_src > prev_stop:
                trailing_stop = max(prev_stop, src - n_loss)
            elif src < prev_stop and prev_src < prev_stop:
                trailing_stop = min(prev_stop, src + n_loss)
            elif src > prev_stop:
                trailing_stop = src - n_loss
            else:
                trailing_stop = src + n_loss

            above = src > trailing_stop and prev_src <= prev_stop
            below = trailing_stop > src and prev_stop <= prev_src
            buy = above
            sell = below

            states.append(
                StrategyState(
                    ts_utc=candle.ts_utc,
                    trailing_stop=trailing_stop,
                    buy=buy,
                    sell=sell,
                )
            )

            prev_stop = trailing_stop
            prev_src = src

        return states


def last_signal_bias(states: Iterable[StrategyState]) -> Optional[Direction]:
    bias: Optional[Direction] = None
    for state in states:
        if state.buy:
            bias = Direction.LONG
        elif state.sell:
            bias = Direction.SHORT
    return bias
