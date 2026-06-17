from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dual_market_trader.live_models import (
    LiveOrderIntent,
    LiveOrderResult,
    LivePaperExecutionResult,
)
from dual_market_trader.reporting import append_live_execution_log, append_live_paper_execution_log


class LiveBroker(Protocol):
    def place_order(self, intent: LiveOrderIntent) -> LiveOrderResult: ...


class Sleeper(Protocol):
    def __call__(self, seconds: float, /) -> None: ...


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
) -> tuple[LivePaperExecutionResult, ...]:
    results: list[LivePaperExecutionResult] = []
    for cycle_index in range(config.max_cycles):
        result = LivePaperExecutionResult(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            intent=config.intent,
            fill_price=config.intent.price,
            notional=round(config.intent.quantity * config.intent.price, 8),
            note="paper fill only",
        )
        _ = append_live_paper_execution_log(result, config.log_path)
        results.append(result)
        if cycle_index + 1 < config.max_cycles and config.interval_seconds > 0:
            sleeper(config.interval_seconds)
    return tuple(results)
