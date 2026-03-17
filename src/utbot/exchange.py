from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import time

from .models import Candle, Direction, Position


class ExchangeAdapter(ABC):
    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        raise NotImplementedError

    @abstractmethod
    def place_market_order(self, symbol: str, side: Direction, size: float) -> str:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, symbol: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_symbol_meta(self, symbol: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        raise NotImplementedError


class InMemoryBitmartPerpAdapter(ExchangeAdapter):
    """Dry-run adapter that follows ExchangeAdapter contract for tests and local runs."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}
        self._order_counter = 0
        self.orders: list[dict] = []

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def place_market_order(self, symbol: str, side: Direction, size: float) -> str:
        self._order_counter += 1
        order_id = f"ord_{self._order_counter}"
        self._positions[symbol] = Position(side=side, size=size)
        self.orders.append({"id": order_id, "symbol": symbol, "action": "OPEN", "side": side.value, "size": size})
        return order_id

    def close_position(self, symbol: str) -> str | None:
        position = self._positions.get(symbol)
        if position is None:
            return None
        self._order_counter += 1
        order_id = f"ord_{self._order_counter}"
        self.orders.append({"id": order_id, "symbol": symbol, "action": "CLOSE", "side": position.side.value, "size": position.size})
        self._positions.pop(symbol, None)
        return order_id

    def get_symbol_meta(self, symbol: str) -> dict:
        return {"symbol": symbol, "status": "Trading", "type": "USDT_PERP"}

    def fetch_recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        _ = symbol, timeframe, limit
        return []


class BitmartAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class BitmartCredentials:
    api_key: str
    api_secret: str
    api_memo: str


class BitmartPerpRestAdapter(ExchangeAdapter):
    """
    BitMart Futures V2 adapter.

    Uses KEYED endpoints for reads and SIGNED endpoints for trading.
    """

    def __init__(
        self,
        credentials: BitmartCredentials,
        base_url: str = "https://api-cloud-v2.bitmart.com",
        account: str = "futures",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.account = account
        self.timeout_seconds = timeout_seconds

    def get_symbol_meta(self, symbol: str) -> dict:
        response = self._request("GET", "/contract/public/details", params={"symbol": symbol})
        data = response.get("data", {})
        rows = data.get("symbols", []) if isinstance(data, dict) else []
        for row in rows:
            if row.get("symbol") == symbol:
                return row
        raise BitmartAPIError(f"Symbol not found on BitMart futures: {symbol}")

    def get_position(self, symbol: str) -> Position | None:
        response = self._request(
            "GET",
            "/contract/private/position-v2",
            params={"symbol": symbol, "account": self.account},
            keyed=True,
        )
        rows = response.get("data", [])
        if not rows:
            return None
        row = rows[0]

        amount_raw = row.get("current_amount")
        if amount_raw in (None, "", "0", "0.0"):
            return None

        amount = abs(float(amount_raw))
        if amount == 0:
            return None

        position_type = str(row.get("position_type", ""))
        if position_type == "1":
            side = Direction.LONG
        elif position_type == "2":
            side = Direction.SHORT
        else:
            side_value = str(row.get("position_side", "")).lower()
            if side_value == "long":
                side = Direction.LONG
            elif side_value == "short":
                side = Direction.SHORT
            else:
                return None

        return Position(side=side, size=amount)

    def fetch_recent_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        if limit < 1:
            return []
        step = _bitmart_step_from_timeframe(timeframe)
        end_time = int(time())
        start_time = int((datetime.now(tz=timezone.utc) - timedelta(minutes=step * limit)).timestamp())
        response = self._request(
            "GET",
            "/contract/public/kline",
            params={
                "symbol": symbol,
                "step": step,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        rows = response.get("data", [])
        candles: list[Candle] = []
        for row in rows:
            ts = datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc)
            candles.append(
                Candle(
                    ts_utc=ts,
                    open=float(row["open_price"]),
                    high=float(row["high_price"]),
                    low=float(row["low_price"]),
                    close=float(row["close_price"]),
                )
            )
        candles.sort(key=lambda c: c.ts_utc)
        return candles[-limit:]

    def place_market_order(self, symbol: str, side: Direction, size: float) -> str:
        contracts = _contracts_from_size(size)
        side_code = 1 if side == Direction.LONG else 4
        body = {
            "symbol": symbol,
            "side": side_code,
            "type": "market",
            "mode": 1,
            "size": contracts,
        }
        response = self._request("POST", "/contract/private/submit-order", body=body, signed=True)
        data = response.get("data", {})
        return str(data.get("order_id", ""))

    def close_position(self, symbol: str) -> str | None:
        current = self.get_position(symbol)
        if current is None:
            return None

        side_code = 3 if current.side == Direction.LONG else 2
        body = {
            "symbol": symbol,
            "side": side_code,
            "type": "market",
            "mode": 1,
            "size": _contracts_from_size(current.size),
        }
        response = self._request("POST", "/contract/private/submit-order", body=body, signed=True)
        data = response.get("data", {})
        return str(data.get("order_id", ""))

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
        keyed: bool = False,
        signed: bool = False,
    ) -> dict:
        method = method.upper()
        params = params or {}
        body = body or {}

        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        payload_for_sign = ""
        raw_body = b""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "utbot-bitmart/0.1",
            "Accept": "application/json",
        }

        if method in {"GET", "DELETE"}:
            payload_for_sign = query_string
        else:
            body_str = json.dumps(body, separators=(",", ":"))
            payload_for_sign = body_str
            raw_body = body_str.encode("utf-8")

        if keyed or signed:
            headers["X-BM-KEY"] = self.credentials.api_key

        if signed:
            timestamp_ms = str(int(time() * 1000))
            sign_plain = f"{timestamp_ms}#{self.credentials.api_memo}#{payload_for_sign}"
            signature = hmac.new(
                self.credentials.api_secret.encode("utf-8"),
                sign_plain.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-BM-TIMESTAMP"] = timestamp_ms
            headers["X-BM-SIGN"] = signature

        req = urllib.request.Request(url=url, data=raw_body if raw_body else None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                response_raw = resp.read().decode("utf-8")
                parsed = json.loads(response_raw)
        except Exception as exc:  # pragma: no cover
            raise BitmartAPIError(f"BitMart request failed: {method} {path}: {exc}") from exc

        code = parsed.get("code")
        if code != 1000:
            raise BitmartAPIError(f"BitMart API error code={code}, message={parsed.get('message')}, path={path}")
        return parsed


def _contracts_from_size(size: float) -> int:
    contracts = int(round(size))
    if contracts < 1:
        raise ValueError("size must round to at least 1 contract")
    return contracts


def _bitmart_step_from_timeframe(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    mapping = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "1d": 1440,
    }
    if tf not in mapping:
        raise ValueError(f"Unsupported timeframe for BitMart kline: {timeframe}")
    return mapping[tf]
