from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum, unique
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from dual_market_trader.live_models import LivePaperExecutionResult, OrderSide

if TYPE_CHECKING:
    from collections.abc import Sequence

SIDE_EXIT_DIRECTIONS: Final = MappingProxyType(
    {
        OrderSide.BUY: (1.0, -1.0),
        OrderSide.SELL: (-1.0, 1.0),
    },
)
SIDE_PNL_DIRECTIONS: Final = MappingProxyType(
    {
        OrderSide.BUY: 1.0,
        OrderSide.SELL: -1.0,
    },
)


@unique
class TradeMarkerKind(StrEnum):
    ENTRY = "entry"
    TARGET = "target"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class TradeMarker:
    kind: TradeMarkerKind
    label: str
    timestamp: int
    price: float
    quantity: float


def build_trade_markers(
    entries: Sequence[LivePaperExecutionResult],
    target_pct: float,
    stop_loss_pct: float,
    fallback_timestamp: int,
) -> tuple[TradeMarker, ...]:
    markers: list[TradeMarker] = []
    for entry in entries[-1:]:
        timestamp = recorded_at_epoch(entry.recorded_at, fallback_timestamp)
        markers.extend(_markers_for_entry(entry, timestamp, target_pct, stop_loss_pct))
    return tuple(markers)


def compute_live_pnl(
    entries: Sequence[LivePaperExecutionResult],
    latest_price: float,
) -> tuple[float, float, float | None]:
    exposure = sum(entry.fill_price * entry.intent.quantity for entry in entries)
    if exposure <= 0:
        return 0.0, 0.0, None
    pnl = sum(
        (latest_price - entry.fill_price)
        * SIDE_PNL_DIRECTIONS[entry.intent.side]
        * entry.intent.quantity
        for entry in entries
    )
    return exposure, pnl, pnl / exposure * 100


def recorded_at_epoch(recorded_at: str, fallback: int) -> int:
    try:
        parsed = datetime.fromisoformat(recorded_at)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


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
