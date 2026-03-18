# UT Bot (HTF -> LTF) for BitMart Perpetual

Local UT Bot strategy engine with multi-timeframe filtering:
- `1D` defines directional bias from the latest UT signal (`last_signal` mode)
- `LTF` (`5m/15m/1h`) executes entries only in the same direction as HTF bias
- Counter LTF signals are `close_only`

## Config (env)

- `BOT_DRY_RUN` (`true`/`false`)
- `BOT_RUN_MODE` (`once` или `loop`, для 24/7 используйте `loop`)
- `BOT_SYMBOL` (default `SOLUSDT`)
- `BOT_SYMBOLS` (опционально, CSV: `HYPEUSDT,SOLUSDT`; до 5 символов)
- `BOT_POSITION_SIZES` (опционально, per-symbol в USDT: `HYPEUSDT:50,SOLUSDT:20`)
- `BOT_HTF_TIMEFRAME` (default `1d`)
- `BOT_LTF_TIMEFRAME` (default `15m`)
- `BOT_HTF_LOOKBACK` (default `15`, для определения HTF bias перед стартом)
- `BOT_LTF_LOOKBACK` (default `300`, окно расчета сигнала LTF)
- `BOT_POSITION_SIZE` (размер позиции в USDT, default `50`)
- `BOT_ORDER_TYPE` (default `market`)
- `BOT_UT_KEY_VALUE` (default `1.0`)
- `BOT_UT_ATR_PERIOD` (default `10`)
- `BOT_UT_USE_HEIKIN` (default `false`)
- `BOT_DB_PATH` (default `utbot.db`)
- `TG_ENABLED` (default `false`, включить Telegram-уведомления)
- `TG_BOT_TOKEN` (токен Telegram-бота)
- `TG_CHAT_ID` (id чата для уведомлений)

BitMart credentials (live mode):
- `BITMART_API_KEY`
- `BITMART_API_SECRET`
- `BITMART_API_MEMO`
- `BITMART_BASE_URL` (default `https://api-cloud-v2.bitmart.com`)
- `BITMART_ACCOUNT` (default `futures`)

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Security

- Never commit `.env`, `config.yaml`, or API keys.
- If an API key was exposed, revoke it and create a new one before live trading.

## Notes

- `InMemoryBitmartPerpAdapter` is used in dry-run mode.
- `BitmartPerpRestAdapter` is enabled when `BOT_DRY_RUN=false` and credentials are set.


## Dashboard API (для интерфейса)

Запуск API на VPS:

```bash
set -a && source .env && set +a
PYTHONPATH=src python3 -m utbot.api_server
```

По умолчанию API слушает `0.0.0.0:8787`.

Эндпоинты:
- `/api/health`
- `/api/symbols`
- `/api/events?symbol=HYPEUSDT&limit=300`
- `/api/candles?symbol=HYPEUSDT&timeframe=15m&limit=250`

## Vercel Dashboard

Папка `dashboard/` — статический фронтенд.

- Деплойте папку `dashboard` в Vercel как Static Site.
- В интерфейсе задайте `API Base URL` вашего VPS, например `http://YOUR_SERVER_IP:8787`.


### Режим интерфейса

Текущий dashboard работает только как live-мониторинг (без управления ботом):
- автоматически подхватывает все символы из `/api/symbols`
- показывает график и сигналы по каждой включенной валюте
- автообновление каждые N секунд
