from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    symbol: str
    htf_timeframe: str = "1d"
    ltf_timeframe: str = "15m"
    htf_bias_mode: str = "last_signal"
    counter_signal_action: str = "close_only"
    position_size: float = 1.0
    order_type: str = "market"
    ut_key_value: float = 1.0
    ut_atr_period: int = 10
    ut_use_heikin: bool = False
    htf_lookback: int = 15
    ltf_lookback: int = 300
    dry_run: bool = True

    def validate(self) -> None:
        if self.position_size <= 0:
            raise ValueError("position_size must be > 0")
        if self.order_type != "market":
            raise ValueError("Only market order_type is supported in v1")
        if self.htf_bias_mode != "last_signal":
            raise ValueError("Only htf_bias_mode=last_signal is supported in v1")
        if self.counter_signal_action != "close_only":
            raise ValueError("Only counter_signal_action=close_only is supported in v1")
        if self.ut_atr_period < 1:
            raise ValueError("ut_atr_period must be >= 1")
        if self.htf_lookback < 1:
            raise ValueError("htf_lookback must be >= 1")
        if self.ltf_lookback < 1:
            raise ValueError("ltf_lookback must be >= 1")
