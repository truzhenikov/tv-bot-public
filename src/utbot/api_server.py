from __future__ import annotations

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .exchange import BitmartCredentials, BitmartPerpRestAdapter, InMemoryBitmartPerpAdapter
from .storage import SignalStore


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _make_exchange():
    dry_run = _env_bool("BOT_DRY_RUN", True)
    if dry_run:
        return InMemoryBitmartPerpAdapter()

    api_key = os.getenv("BITMART_API_KEY", "")
    api_secret = os.getenv("BITMART_API_SECRET", "")
    api_memo = os.getenv("BITMART_API_MEMO", "")
    if not api_key or not api_secret or not api_memo:
        raise RuntimeError("Missing BitMart credentials for API server")

    creds = BitmartCredentials(api_key=api_key, api_secret=api_secret, api_memo=api_memo)
    return BitmartPerpRestAdapter(
        credentials=creds,
        base_url=os.getenv("BITMART_BASE_URL", "https://api-cloud-v2.bitmart.com"),
        account=os.getenv("BITMART_ACCOUNT", "futures"),
    )


class DashboardAPIHandler(BaseHTTPRequestHandler):
    store = SignalStore(os.getenv("BOT_DB_PATH", "utbot.db"))
    exchange = _make_exchange()

    def _json(self, data: dict, code: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/health":
                self._json({"ok": True, "ts_utc": datetime.utcnow().isoformat()})
                return

            if parsed.path == "/api/symbols":
                db_symbols = self.store.list_symbols()
                env_symbols = [s.strip().upper() for s in os.getenv("BOT_SYMBOLS", "").split(",") if s.strip()]
                merged = sorted(set(db_symbols + env_symbols))
                self._json({"symbols": merged})
                return

            if parsed.path == "/api/events":
                symbol = qs.get("symbol", [None])[0]
                limit = int(qs.get("limit", ["300"])[0])
                events = self.store.list_events(symbol=symbol, limit=limit)
                self._json({"events": events})
                return

            if parsed.path == "/api/candles":
                symbol = qs.get("symbol", [None])[0]
                timeframe = qs.get("timeframe", ["15m"])[0]
                req_limit = int(qs.get("limit", ["300"])[0])
                # BitMart rejects too large kline windows for some TF/ranges.
                limit = max(1, min(req_limit, 300))
                if not symbol:
                    self._json({"error": "symbol is required"}, code=400)
                    return
                candles = self.exchange.fetch_recent_candles(symbol=symbol, timeframe=timeframe, limit=limit)
                data = [
                    {
                        "ts_utc": c.ts_utc.isoformat(),
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                    }
                    for c in candles
                ]
                self._json({"candles": data})
                return

            self._json({"error": "not found"}, code=404)
        except Exception as exc:
            self._json({"error": str(exc)}, code=500)


def run_api_server() -> None:
    host = os.getenv("BOT_API_HOST", "0.0.0.0")
    port = int(os.getenv("BOT_API_PORT", "8787"))
    httpd = HTTPServer((host, port), DashboardAPIHandler)
    print(f"Dashboard API listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_api_server()
