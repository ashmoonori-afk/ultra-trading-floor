from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import ClassVar, Final, Protocol, override

from pydantic import BaseModel, ConfigDict, Field

from dual_market_trader.live_models import (
    LiveOrderIntent,
    LiveOrderResult,
    LivePaperExecutionResult,
)
from dual_market_trader.models import Market
from dual_market_trader.reporting import append_live_execution_log, append_live_paper_execution_log

THOUSANDS_PRICE_THRESHOLD: Final = 1_000


class LiveBroker(Protocol):
    def place_order(self, intent: LiveOrderIntent) -> LiveOrderResult: ...


class Sleeper(Protocol):
    def __call__(self, seconds: float, /) -> None: ...


class LivePaperPriceProvider(Protocol):
    def latest_price(self, intent: LiveOrderIntent) -> float | None: ...


@dataclass(frozen=True, slots=True)
class LivePaperPriceUnavailableError(Exception):
    market: Market
    symbol: str

    @override
    def __str__(self) -> str:
        return f"live paper market price unavailable for {self.market.value.upper()} {self.symbol}"


class LiveExecutionConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    intent: LiveOrderIntent
    log_path: Path
    max_cycles: int = Field(ge=1, le=10_000)
    interval_seconds: float = Field(ge=0, le=86_400)


class LivePaperExecutionConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    intent: LiveOrderIntent
    log_path: Path
    max_cycles: int = Field(ge=1, le=10_000)
    interval_seconds: float = Field(ge=0, le=86_400)


def run_live_execution_loop(
    config: LiveExecutionConfig,
    broker: LiveBroker,
    sleeper: Sleeper = sleep,
) -> tuple[LiveOrderResult, ...]:
    results: list[LiveOrderResult] = []
    for cycle_index in range(config.max_cycles):
        result = broker.place_order(config.intent)
        _ = append_live_execution_log(result, config.log_path)
        results.append(result)
        if cycle_index + 1 < config.max_cycles and config.interval_seconds > 0:
            sleeper(config.interval_seconds)
    return tuple(results)


def run_live_paper_execution_loop(
    config: LivePaperExecutionConfig,
    sleeper: Sleeper = sleep,
    price_provider: LivePaperPriceProvider | None = None,
) -> tuple[LivePaperExecutionResult, ...]:
    results: list[LivePaperExecutionResult] = []
    for cycle_index in range(config.max_cycles):
        fill_price, note = _resolve_live_paper_fill(config.intent, price_provider)
        result = LivePaperExecutionResult(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            intent=config.intent,
            fill_price=fill_price,
            notional=round(config.intent.quantity * fill_price, 8),
            note=note,
        )
        _ = append_live_paper_execution_log(result, config.log_path)
        results.append(result)
        if cycle_index + 1 < config.max_cycles and config.interval_seconds > 0:
            sleeper(config.interval_seconds)
    return tuple(results)


def _resolve_live_paper_fill(
    intent: LiveOrderIntent,
    price_provider: LivePaperPriceProvider | None,
) -> tuple[float, str]:
    if price_provider is None:
        return intent.price, "paper fill only"
    latest_price = price_provider.latest_price(intent)
    if latest_price is None:
        raise LivePaperPriceUnavailableError(market=intent.market, symbol=intent.symbol)
    return latest_price, _market_fill_note(intent.price, latest_price)


def _market_fill_note(requested_price: float, fill_price: float) -> str:
    if abs(requested_price - fill_price) <= max(fill_price * 0.0001, 0.01):
        return "paper fill at latest market price"
    return f"paper fill at latest market price; requested price {_format_price(requested_price)}"


def _format_price(value: float) -> str:
    if value >= THOUSANDS_PRICE_THRESHOLD:
        return f"{value:,.0f}"
    return f"{value:,.4g}"
