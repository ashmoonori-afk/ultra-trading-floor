from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Final
from urllib.parse import quote

import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

from dual_market_trader.charting import ChartSpec, MarketDataSource, MarketMinuteSeries
from dual_market_trader.models import Candle, Market

if TYPE_CHECKING:
    from collections.abc import Sequence

YAHOO_BASE_URL: Final = "https://query1.finance.yahoo.com"
YAHOO_RANGE: Final = "1d"
YAHOO_INTERVAL: Final = "1m"
MAX_CANDLES: Final = 90
USER_AGENT: Final = "UltraTradingFloor/0.1 paper-market-data"

_LIMITS: Final = httpx2.Limits(
    max_connections=200,
    max_keepalive_connections=40,
    keepalive_expiry=30.0,
)
_TIMEOUT: Final = httpx2.Timeout(
    connect=5.0,
    read=30.0,
    write=10.0,
    pool=10.0,
)
_SOCKET_OPTIONS: Final = [
    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
]


class YahooQuote(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    open: tuple[float | None, ...]
    high: tuple[float | None, ...]
    low: tuple[float | None, ...]
    close: tuple[float | None, ...]
    volume: tuple[float | None, ...] = ()


class YahooIndicators(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    quote: tuple[YahooQuote, ...]


class YahooResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    timestamp: tuple[int, ...] = ()
    indicators: YahooIndicators


class YahooChart(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    result: tuple[YahooResult, ...] | None = None


class YahooChartResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    chart: YahooChart


@dataclass(frozen=True, slots=True)
class YahooFinanceMarketDataProvider:
    base_url: str = YAHOO_BASE_URL

    def load_minute_candles(self, specs: Sequence[ChartSpec]) -> tuple[MarketMinuteSeries, ...]:
        with _create_client(self.base_url) as client:
            series: list[MarketMinuteSeries] = []
            for spec in specs:
                loaded = self._load_one(client, spec)
                if loaded is not None:
                    series.append(loaded)
            return tuple(series)

    def _load_one(self, client: httpx2.Client, spec: ChartSpec) -> MarketMinuteSeries | None:
        yahoo_symbol = _yahoo_symbol(spec)
        try:
            response = client.get(
                f"/v8/finance/chart/{quote(yahoo_symbol, safe='')}",
                params={
                    "range": YAHOO_RANGE,
                    "interval": YAHOO_INTERVAL,
                    "includePrePost": "false",
                },
            )
            _ = response.raise_for_status()
            payload = YahooChartResponse.model_validate_json(response.text)
        except (httpx2.HTTPError, ValidationError):
            return None
        candles = _candles_from_payload(payload)
        if not candles:
            return None
        return MarketMinuteSeries(
            market=spec.market,
            symbol=yahoo_symbol,
            candles=candles[-MAX_CANDLES:],
            source=MarketDataSource.YAHOO,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )


def _create_client(base_url: str) -> httpx2.Client:
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=_LIMITS,
        socket_options=_SOCKET_OPTIONS,
    )
    return httpx2.Client(
        transport=transport,
        timeout=_TIMEOUT,
        base_url=base_url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _candles_from_payload(payload: YahooChartResponse) -> tuple[Candle, ...]:
    results = payload.chart.result
    if not results or not results[0].indicators.quote:
        return ()
    result = results[0]
    quote_data = result.indicators.quote[0]
    candles: list[Candle] = []
    for index, timestamp in enumerate(result.timestamp):
        candle = _candle_at(index, timestamp, quote_data)
        if candle is not None:
            candles.append(candle)
    return tuple(candles)


def _candle_at(index: int, timestamp: int, quote_data: YahooQuote) -> Candle | None:
    if index >= len(quote_data.close):
        return None
    open_price = _value_at(quote_data.open, index)
    high_price = _value_at(quote_data.high, index)
    low_price = _value_at(quote_data.low, index)
    close_price = _value_at(quote_data.close, index)
    if open_price is None or high_price is None or low_price is None or close_price is None:
        return None
    volume = _value_at(quote_data.volume, index) if quote_data.volume else 0.0
    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume if volume is not None else 0.0,
    )


def _value_at(values: tuple[float | None, ...], index: int) -> float | None:
    if index >= len(values):
        return None
    return values[index]


def _yahoo_symbol(spec: ChartSpec) -> str:
    symbol = spec.symbol.upper()
    if spec.market == Market.KR and not symbol.endswith(".KS"):
        return f"{symbol}.KS"
    return symbol
