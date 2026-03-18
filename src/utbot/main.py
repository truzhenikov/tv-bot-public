from __future__ import annotations

import os
import time
from dataclasses import replace
from datetime import datetime, timezone

from .config import BotConfig
from .engine import StrategyEngine
from .exchange import BitmartCredentials, BitmartPerpRestAdapter, InMemoryBitmartPerpAdapter
from .notifier import Notifier, NullNotifier, TelegramNotifier
from .storage import SignalStore
from .strategy import UTBotStrategy, last_signal_bias


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _timeframe_to_seconds(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    mapping = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
    }
    if tf not in mapping:
        raise ValueError(f"Unsupported LTF for loop scheduler: {timeframe}")
    return mapping[tf]


def _sleep_until_next_candle_close(timeframe: str, safety_delay_seconds: int = 2) -> None:
    step = _timeframe_to_seconds(timeframe)
    now_ts = int(time.time())
    next_close = ((now_ts // step) + 1) * step
    sleep_for = max(1, next_close - now_ts + safety_delay_seconds)
    time.sleep(sleep_for)


def _parse_symbols(default_symbol: str) -> list[str]:
    raw = os.getenv("BOT_SYMBOLS", "").strip()
    if not raw:
        return [default_symbol]
    symbols = [x.strip().upper() for x in raw.split(",") if x.strip()]
    uniq: list[str] = []
    for s in symbols:
        if s not in uniq:
            uniq.append(s)
    if len(uniq) > 5:
        raise ValueError("BOT_SYMBOLS supports up to 5 symbols")
    return uniq


def _parse_position_sizes(default_size: float) -> dict[str, float]:
    raw = os.getenv("BOT_POSITION_SIZES", "").strip()
    if not raw:
        return {}
    parsed: dict[str, float] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError("BOT_POSITION_SIZES format: SYMBOL:SIZE,SYMBOL:SIZE")
        symbol, size = item.split(":", 1)
        parsed[symbol.strip().upper()] = float(size)
    return parsed


def load_config_from_env() -> BotConfig:
    return BotConfig(
        symbol=os.getenv("BOT_SYMBOL", "SOLUSDT"),
        htf_timeframe=os.getenv("BOT_HTF_TIMEFRAME", "1d"),
        ltf_timeframe=os.getenv("BOT_LTF_TIMEFRAME", "15m"),
        htf_bias_mode=os.getenv("BOT_HTF_BIAS_MODE", "last_signal"),
        counter_signal_action=os.getenv("BOT_COUNTER_SIGNAL_ACTION", "close_only"),
        position_size=float(os.getenv("BOT_POSITION_SIZE", "1.0")),
        order_type=os.getenv("BOT_ORDER_TYPE", "market"),
        ut_key_value=float(os.getenv("BOT_UT_KEY_VALUE", "1.0")),
        ut_atr_period=int(os.getenv("BOT_UT_ATR_PERIOD", "10")),
        ut_use_heikin=_env_bool("BOT_UT_USE_HEIKIN", False),
        htf_lookback=int(os.getenv("BOT_HTF_LOOKBACK", "15")),
        ltf_lookback=int(os.getenv("BOT_LTF_LOOKBACK", "300")),
        dry_run=_env_bool("BOT_DRY_RUN", True),
    )


def make_exchange_adapter(dry_run: bool):
    if dry_run:
        return InMemoryBitmartPerpAdapter()

    api_key = os.getenv("BITMART_API_KEY", "")
    api_secret = os.getenv("BITMART_API_SECRET", "")
    api_memo = os.getenv("BITMART_API_MEMO", "")

    if not api_key or not api_secret or not api_memo:
        raise RuntimeError("Missing BitMart credentials. Set BITMART_API_KEY, BITMART_API_SECRET, BITMART_API_MEMO")

    creds = BitmartCredentials(api_key=api_key, api_secret=api_secret, api_memo=api_memo)
    return BitmartPerpRestAdapter(
        credentials=creds,
        base_url=os.getenv("BITMART_BASE_URL", "https://api-cloud-v2.bitmart.com"),
        account=os.getenv("BITMART_ACCOUNT", "futures"),
    )


def make_notifier() -> Notifier:
    enabled = _env_bool("TG_ENABLED", False)
    if not enabled:
        return NullNotifier()
    bot_token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        raise RuntimeError("TG_ENABLED=true requires TG_BOT_TOKEN and TG_CHAT_ID")
    return TelegramNotifier(bot_token=bot_token, chat_id=chat_id)


def _run_cycle_for_symbol(
    symbol_config: BotConfig,
    exchange,
    store: SignalStore,
    strategy: UTBotStrategy,
    notifier: Notifier,
) -> int:
    htf_candles = exchange.fetch_recent_candles(symbol_config.symbol, symbol_config.htf_timeframe, symbol_config.htf_lookback)
    ltf_candles = exchange.fetch_recent_candles(symbol_config.symbol, symbol_config.ltf_timeframe, symbol_config.ltf_lookback)

    htf_bias = last_signal_bias(strategy.evaluate(htf_candles))
    bias_text = htf_bias.value if htf_bias else "UNDEFINED"
    notifier.send(
        f"[{symbol_config.symbol}] Направление {symbol_config.htf_timeframe}: {bias_text} "
        f"(lookback={symbol_config.htf_lookback})"
    )

    engine = StrategyEngine(config=symbol_config, exchange=exchange, store=store, strategy=strategy)
    result = engine.run(htf_candles=htf_candles, ltf_candles=ltf_candles)
    if not result.events:
        notifier.send(f"[{symbol_config.symbol}] Событий по последней LTF-свече нет.")
    for event in result.events:
        print(event)
        notifier.send(
            " | ".join(
                [
                    f"{event.symbol} {event.timeframe}",
                    f"LTF={event.ltf_signal.value if event.ltf_signal else 'NONE'}",
                    f"HTF={event.htf_bias.value if event.htf_bias else 'NONE'}",
                    f"ACTION={event.action.value}",
                    f"REASON={event.action_reason}",
                    f"TS={event.candle_close_ts_utc.isoformat()}",
                ]
            )
        )
    return len(result.events)


def _build_symbol_configs(base: BotConfig) -> list[BotConfig]:
    symbols = _parse_symbols(base.symbol)
    sizes = _parse_position_sizes(base.position_size)
    out: list[BotConfig] = []
    for symbol in symbols:
        size = sizes.get(symbol, base.position_size)
        out.append(replace(base, symbol=symbol, position_size=size))
    return out


def run_once() -> None:
    base_config = load_config_from_env()
    notifier = make_notifier()
    exchange = make_exchange_adapter(base_config.dry_run)
    store = SignalStore(os.getenv("BOT_DB_PATH", "utbot.db"))
    strategy = UTBotStrategy(
        key_value=base_config.ut_key_value,
        atr_period=base_config.ut_atr_period,
        use_heikin=base_config.ut_use_heikin,
    )

    symbol_configs = _build_symbol_configs(base_config)
    symbol_list = ", ".join(c.symbol for c in symbol_configs)

    for cfg in symbol_configs:
        exchange.get_symbol_meta(cfg.symbol)

    notifier.send(
        "\n".join(
            [
                "UT Bot запущен",
                f"Символы: {symbol_list}",
                f"HTF/LTF: {base_config.htf_timeframe}/{base_config.ltf_timeframe}",
                f"Dry-run: {base_config.dry_run}",
                f"Мультивалютный режим: {len(symbol_configs)} инструмент(а)",
            ]
        )
    )

    for cfg in symbol_configs:
        _run_cycle_for_symbol(symbol_config=cfg, exchange=exchange, store=store, strategy=strategy, notifier=notifier)


def run_forever() -> None:
    base_config = load_config_from_env()
    notifier = make_notifier()
    exchange = make_exchange_adapter(base_config.dry_run)
    store = SignalStore(os.getenv("BOT_DB_PATH", "utbot.db"))
    strategy = UTBotStrategy(
        key_value=base_config.ut_key_value,
        atr_period=base_config.ut_atr_period,
        use_heikin=base_config.ut_use_heikin,
    )

    symbol_configs = _build_symbol_configs(base_config)
    symbol_list = ", ".join(c.symbol for c in symbol_configs)

    for cfg in symbol_configs:
        exchange.get_symbol_meta(cfg.symbol)

    notifier.send(
        "\n".join(
            [
                "UT Bot запущен (loop)",
                f"Символы: {symbol_list}",
                f"HTF/LTF: {base_config.htf_timeframe}/{base_config.ltf_timeframe}",
                f"Dry-run: {base_config.dry_run}",
                "Режим: непрерывный",
            ]
        )
    )

    while True:
        try:
            for cfg in symbol_configs:
                _run_cycle_for_symbol(symbol_config=cfg, exchange=exchange, store=store, strategy=strategy, notifier=notifier)
        except Exception as exc:
            now = datetime.now(tz=timezone.utc).isoformat()
            notifier.send(f"Ошибка цикла: {exc} | {now}")
            time.sleep(20)
            continue

        _sleep_until_next_candle_close(base_config.ltf_timeframe)


def main() -> None:
    mode = os.getenv("BOT_RUN_MODE", "once").strip().lower()
    if mode == "loop":
        run_forever()
        return
    run_once()


if __name__ == "__main__":
    main()
