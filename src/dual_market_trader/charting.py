from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol

from dual_market_trader.chart_trades import (
    TradeMarker,
    build_trade_markers,
    compute_live_pnl,
    recorded_at_epoch,
)
from dual_market_trader.models import Candle, Market, PerformanceLogEntry
from dual_market_trader.sample_data import symbol_for_market

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.live_models import LivePaperExecutionResult

CHART_MINUTES: Final = 60
DEFAULT_TARGET_PCT: Final = 5.0
DEFAULT_STOP_LOSS_PCT: Final = 2.0
DEFAULT_END_TIMESTAMP: Final = 1_787_003_540
COMPACT_PRICE_THRESHOLD: Final = 1_000.0
DEFAULT_REFERENCE_PRICES: Final = MappingProxyType(
    {
        Market.KR: 71_000.0,
        Market.US: 116.2,
    },
)


@unique
class MarketDataSource(StrEnum):
    YAHOO = "yahoo"
    GENERATED = "generated"


@dataclass(frozen=True, slots=True)
class ChartSpec:
    market: Market
    symbol: str


@dataclass(frozen=True, slots=True)
class MarketMinuteSeries:
    market: Market
    symbol: str
    candles: tuple[Candle, ...]
    source: MarketDataSource
    fetched_at: str


class MarketDataProvider(Protocol):
    def load_minute_candles(self, specs: Sequence[ChartSpec]) -> tuple[MarketMinuteSeries, ...]: ...


@dataclass(frozen=True, slots=True)
class MarketMinuteChart:
    market: Market
    symbol: str
    candles: tuple[Candle, ...]
    markers: tuple[TradeMarker, ...]
    target_daily_return_pct: float
    stop_loss_pct: float
    data_source: MarketDataSource
    data_notice: str
    latest_price: float
    live_exposure: float
    live_pnl: float
    live_return_pct: float | None


def build_market_minute_charts(
    performance_entries: Sequence[PerformanceLogEntry],
    live_paper_entries: Sequence[LivePaperExecutionResult],
    market_data_provider: MarketDataProvider | None = None,
) -> tuple[MarketMinuteChart, ...]:
    latest = performance_entries[-1] if performance_entries else None
    target_pct = latest.target_daily_return_pct if latest is not None else DEFAULT_TARGET_PCT
    specs = _chart_specs(latest, live_paper_entries)
    series = (
        market_data_provider.load_minute_candles(specs) if market_data_provider is not None else ()
    )
    return tuple(
        _build_chart(
            spec,
            live_paper_entries,
            target_pct,
            DEFAULT_STOP_LOSS_PCT,
            _matching_series(spec, series),
        )
        for spec in specs
    )


def _build_chart(
    spec: ChartSpec,
    live_paper_entries: Sequence[LivePaperExecutionResult],
    target_pct: float,
    stop_loss_pct: float,
    series: MarketMinuteSeries | None,
) -> MarketMinuteChart:
    entries = _matching_entries(spec, live_paper_entries)
    if series is not None and series.candles:
        candles = series.candles
        latest_price = candles[-1].close
        live_exposure, live_pnl, live_return_pct = compute_live_pnl(entries, latest_price)
        return MarketMinuteChart(
            market=spec.market,
            symbol=spec.symbol,
            candles=candles,
            markers=build_trade_markers(
                entries,
                target_pct,
                stop_loss_pct,
                candles[-1].timestamp,
            ),
            target_daily_return_pct=target_pct,
            stop_loss_pct=stop_loss_pct,
            data_source=series.source,
            data_notice=f"{series.source.value} real 1m fetched {series.fetched_at}",
            latest_price=latest_price,
            live_exposure=live_exposure,
            live_pnl=live_pnl,
            live_return_pct=live_return_pct,
        )
    end_timestamp = _chart_end_timestamp(entries)
    reference_price = _reference_price(spec.market, entries)
    generated = _minute_candles(reference_price, end_timestamp)
    live_exposure, live_pnl, live_return_pct = compute_live_pnl(entries, generated[-1].close)
    return MarketMinuteChart(
        market=spec.market,
        symbol=spec.symbol,
        candles=generated,
        markers=build_trade_markers(entries, target_pct, stop_loss_pct, end_timestamp),
        target_daily_return_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
        data_source=MarketDataSource.GENERATED,
        data_notice="generated fallback; live market data unavailable",
        latest_price=generated[-1].close,
        live_exposure=live_exposure,
        live_pnl=live_pnl,
        live_return_pct=live_return_pct,
    )


def _chart_specs(
    latest: PerformanceLogEntry | None,
    live_paper_entries: Sequence[LivePaperExecutionResult],
) -> tuple[ChartSpec, ...]:
    specs: list[ChartSpec] = []
    seen: set[tuple[Market, str]] = set()
    if latest is not None:
        for market_entry in latest.markets:
            _append_spec(specs, seen, market_entry.market, market_entry.symbol)
    for entry in live_paper_entries[-25:]:
        _append_spec(specs, seen, entry.intent.market, entry.intent.symbol)
    for market in tuple(Market):
        _append_spec(specs, seen, market, symbol_for_market(market))
    return tuple(specs)


def _append_spec(
    specs: list[ChartSpec],
    seen: set[tuple[Market, str]],
    market: Market,
    symbol: str,
) -> None:
    key = (market, _canonical_symbol(symbol))
    if key in seen:
        return
    seen.add(key)
    specs.append(ChartSpec(market=market, symbol=symbol))


def _matching_entries(
    spec: ChartSpec,
    entries: Sequence[LivePaperExecutionResult],
) -> tuple[LivePaperExecutionResult, ...]:
    return tuple(
        entry
        for entry in entries[-50:]
        if entry.intent.market == spec.market
        and _canonical_symbol(entry.intent.symbol) == _canonical_symbol(spec.symbol)
    )


def _matching_series(
    spec: ChartSpec,
    series: Sequence[MarketMinuteSeries],
) -> MarketMinuteSeries | None:
    for item in series:
        if item.market == spec.market and _canonical_symbol(item.symbol) == _canonical_symbol(
            spec.symbol
        ):
            return item
    return None


def _chart_end_timestamp(entries: Sequence[LivePaperExecutionResult]) -> int:
    if not entries:
        return DEFAULT_END_TIMESTAMP
    return max(recorded_at_epoch(entry.recorded_at, DEFAULT_END_TIMESTAMP) for entry in entries)


def _reference_price(
    market: Market,
    entries: Sequence[LivePaperExecutionResult],
) -> float:
    if entries:
        return entries[-1].fill_price
    return DEFAULT_REFERENCE_PRICES[market]


def _minute_candles(reference_price: float, end_timestamp: int) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    precision = 4 if reference_price < COMPACT_PRICE_THRESHOLD else 2
    previous_close = _minute_close(reference_price, 0)
    for index in range(CHART_MINUTES):
        timestamp = end_timestamp - (CHART_MINUTES - 1 - index) * 60
        close = _minute_close(reference_price, index)
        high = round(max(previous_close, close) * (1.0015 + (index % 3) * 0.0001), precision)
        low = round(min(previous_close, close) * (0.9985 - (index % 2) * 0.0001), precision)
        candles.append(
            Candle(
                timestamp=timestamp,
                open=round(previous_close, precision),
                high=high,
                low=low,
                close=round(close, precision),
                volume=10_000 + index * 175,
            ),
        )
        previous_close = close
    return tuple(candles)


def _minute_close(reference_price: float, index: int) -> float:
    trend = (index - (CHART_MINUTES - 1)) * 0.00018
    wave = ((index % 9) - 4) * 0.00055
    return max(0.01, reference_price * (1 + trend + wave))


def _canonical_symbol(symbol: str) -> str:
    return symbol.upper().removesuffix(".KS")
