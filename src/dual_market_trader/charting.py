from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum, unique
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from dual_market_trader.live_models import LivePaperExecutionResult, OrderSide
from dual_market_trader.models import Candle, Market, PerformanceLogEntry
from dual_market_trader.sample_data import symbol_for_market

if TYPE_CHECKING:
    from collections.abc import Sequence

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
SIDE_EXIT_DIRECTIONS: Final = MappingProxyType(
    {
        OrderSide.BUY: (1.0, -1.0),
        OrderSide.SELL: (-1.0, 1.0),
    },
)


@unique
class TradeMarkerKind(StrEnum):
    ENTRY = "entry"
    TARGET = "target"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ChartSpec:
    market: Market
    symbol: str


@dataclass(frozen=True, slots=True)
class TradeMarker:
    kind: TradeMarkerKind
    label: str
    timestamp: int
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class MarketMinuteChart:
    market: Market
    symbol: str
    candles: tuple[Candle, ...]
    markers: tuple[TradeMarker, ...]
    target_daily_return_pct: float
    stop_loss_pct: float


def build_market_minute_charts(
    performance_entries: Sequence[PerformanceLogEntry],
    live_paper_entries: Sequence[LivePaperExecutionResult],
) -> tuple[MarketMinuteChart, ...]:
    latest = performance_entries[-1] if performance_entries else None
    target_pct = latest.target_daily_return_pct if latest is not None else DEFAULT_TARGET_PCT
    specs = _chart_specs(latest, live_paper_entries)
    return tuple(
        _build_chart(spec, live_paper_entries, target_pct, DEFAULT_STOP_LOSS_PCT) for spec in specs
    )


def _build_chart(
    spec: ChartSpec,
    live_paper_entries: Sequence[LivePaperExecutionResult],
    target_pct: float,
    stop_loss_pct: float,
) -> MarketMinuteChart:
    entries = _matching_entries(spec, live_paper_entries)
    end_timestamp = _chart_end_timestamp(entries)
    reference_price = _reference_price(spec.market, entries)
    return MarketMinuteChart(
        market=spec.market,
        symbol=spec.symbol,
        candles=_minute_candles(reference_price, end_timestamp),
        markers=_trade_markers(entries, target_pct, stop_loss_pct, end_timestamp),
        target_daily_return_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
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


def _chart_end_timestamp(entries: Sequence[LivePaperExecutionResult]) -> int:
    if not entries:
        return DEFAULT_END_TIMESTAMP
    return max(_recorded_at_epoch(entry.recorded_at, DEFAULT_END_TIMESTAMP) for entry in entries)


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


def _trade_markers(
    entries: Sequence[LivePaperExecutionResult],
    target_pct: float,
    stop_loss_pct: float,
    fallback_timestamp: int,
) -> tuple[TradeMarker, ...]:
    markers: list[TradeMarker] = []
    for entry in entries[-1:]:
        timestamp = _recorded_at_epoch(entry.recorded_at, fallback_timestamp)
        markers.extend(_markers_for_entry(entry, timestamp, target_pct, stop_loss_pct))
    return tuple(markers)


def _markers_for_entry(
    entry: LivePaperExecutionResult,
    timestamp: int,
    target_pct: float,
    stop_loss_pct: float,
) -> tuple[TradeMarker, TradeMarker, TradeMarker]:
    target_price, stop_price = _exit_prices(entry, target_pct, stop_loss_pct)
    return (
        TradeMarker(
            kind=TradeMarkerKind.ENTRY,
            label="Entry",
            timestamp=timestamp,
            price=entry.fill_price,
            quantity=entry.intent.quantity,
        ),
        TradeMarker(
            kind=TradeMarkerKind.TARGET,
            label="Target Exit",
            timestamp=timestamp,
            price=target_price,
            quantity=entry.intent.quantity,
        ),
        TradeMarker(
            kind=TradeMarkerKind.STOP,
            label="Stop Loss",
            timestamp=timestamp,
            price=stop_price,
            quantity=entry.intent.quantity,
        ),
    )


def _exit_prices(
    entry: LivePaperExecutionResult,
    target_pct: float,
    stop_loss_pct: float,
) -> tuple[float, float]:
    target_direction, stop_direction = SIDE_EXIT_DIRECTIONS[entry.intent.side]
    return (
        entry.fill_price * (1 + target_direction * target_pct / 100),
        entry.fill_price * (1 + stop_direction * stop_loss_pct / 100),
    )


def _recorded_at_epoch(recorded_at: str, fallback: int) -> int:
    try:
        parsed = datetime.fromisoformat(recorded_at)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _canonical_symbol(symbol: str) -> str:
    return symbol.upper().removesuffix(".KS")
