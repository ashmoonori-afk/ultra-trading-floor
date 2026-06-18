from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dual_market_trader.charting import ChartSpec, MarketMinuteSeries
from dual_market_trader.live_models import (
    LiveOrderIntent,
    LivePaperExecutionResult,
    OrderSide,
    OrderType,
)
from dual_market_trader.models import Market  # noqa: TC001 - Pydantic needs Market at runtime.
from dual_market_trader.reporting import append_live_paper_execution_log

if TYPE_CHECKING:
    from dual_market_trader.models import Candle

DEFAULT_SCREENER_DECISION_LOG: Final = Path(".data/screener-decisions.jsonl")
SCREENER_NOTE: Final = "paper fill at screener-selected market price"
SCORE_VOLUME_CAP: Final = 3.0
SCORE_PRECISION: Final = 6
MIN_SERIES_CANDLES: Final = 2


class ScreenerMarketDataProvider(Protocol):
    def load_minute_candles(
        self, specs: tuple[ChartSpec, ...]
    ) -> tuple[MarketMinuteSeries, ...]: ...


class SymbolCandidateSpec(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str = Field(min_length=1)


class ScreenerRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbols: tuple[SymbolCandidateSpec, ...] = Field(min_length=1)
    max_positions: int = Field(ge=1, le=25)
    min_score: float = Field(ge=-100, le=100)
    lookback: int = Field(ge=1, le=120)


class ScreenedSymbol(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str
    latest_price: float = Field(gt=0)
    momentum_pct: float
    breakout_pct: float
    volume_ratio: float
    volatility_pct: float
    score: float
    selected: bool
    reason: str


class ScreenerDecision(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    recorded_at: str
    mode: Literal["screener_paper"] = "screener_paper"
    lookback: int
    max_positions: int
    min_score: float
    candidates: tuple[ScreenedSymbol, ...]
    selected_candidates: tuple[ScreenedSymbol, ...]


class ScreenerPaperConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    request: ScreenerRequest
    per_position_notional: float = Field(gt=0)
    decision_log_path: Path
    live_paper_log_path: Path
    max_cycles: int = Field(ge=1, le=10_000)
    interval_seconds: float = Field(ge=0, le=86_400)


@dataclass(frozen=True, slots=True)
class ScreenerPaperCycleResult:
    decision: ScreenerDecision
    fills: tuple[LivePaperExecutionResult, ...]


def screen_symbols(
    request: ScreenerRequest,
    market_data_provider: ScreenerMarketDataProvider,
) -> ScreenerDecision:
    series = market_data_provider.load_minute_candles(
        tuple(ChartSpec(market=item.market, symbol=item.symbol) for item in request.symbols),
    )
    ranked = tuple(
        sorted(
            (
                candidate
                for candidate in (
                    _screen_series(item, request.lookback)
                    for item in series
                    if len(item.candles) >= MIN_SERIES_CANDLES
                )
                if candidate is not None
            ),
            key=lambda item: item.score,
            reverse=True,
        ),
    )
    selected = tuple(
        item.model_copy(update={"selected": True})
        for item in ranked
        if item.score >= request.min_score
    )[: request.max_positions]
    selected_keys = {(item.market, _canonical_symbol(item.symbol)) for item in selected}
    candidates = tuple(
        item.model_copy(
            update={"selected": (item.market, _canonical_symbol(item.symbol)) in selected_keys},
        )
        for item in ranked
    )
    return ScreenerDecision(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lookback=request.lookback,
        max_positions=request.max_positions,
        min_score=request.min_score,
        candidates=candidates,
        selected_candidates=selected,
    )


def run_screener_paper_loop(
    config: ScreenerPaperConfig,
    market_data_provider: ScreenerMarketDataProvider,
    sleeper: Sleeper = sleep,
) -> tuple[ScreenerPaperCycleResult, ...]:
    results: list[ScreenerPaperCycleResult] = []
    open_symbols: set[tuple[Market, str]] = set()
    for cycle_index in range(config.max_cycles):
        decision = screen_symbols(config.request, market_data_provider)
        _ = append_screener_decision_log(decision, config.decision_log_path)
        fills = tuple(
            _append_new_candidate_fill(
                candidate,
                config.per_position_notional,
                config.live_paper_log_path,
                open_symbols,
            )
            for candidate in decision.selected_candidates
            if _candidate_key(candidate) not in open_symbols
        )
        results.append(ScreenerPaperCycleResult(decision=decision, fills=fills))
        if cycle_index + 1 < config.max_cycles and config.interval_seconds > 0:
            sleeper(config.interval_seconds)
    return tuple(results)


def append_screener_decision_log(decision: ScreenerDecision, path: Path) -> ScreenerDecision:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(decision.model_dump_json() + "\n")
    return decision


def read_screener_decision_log(path: Path) -> tuple[ScreenerDecision, ...]:
    if not path.exists():
        return ()
    return tuple(
        ScreenerDecision.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


class Sleeper(Protocol):
    def __call__(self, seconds: float, /) -> None: ...


def _screen_series(series: MarketMinuteSeries, lookback: int) -> ScreenedSymbol | None:
    candles = series.candles
    if len(candles) <= lookback:
        return None
    latest = candles[-1]
    baseline = candles[-1 - lookback]
    previous = candles[:-1]
    momentum_pct = _pct_change(latest.close, baseline.close)
    breakout_pct = _pct_change(latest.close, max(candle.high for candle in previous))
    volume_ratio = _volume_ratio(latest, previous)
    volatility_pct = _volatility_pct(candles[-lookback:])
    score = _score(momentum_pct, breakout_pct, volume_ratio, volatility_pct)
    return ScreenedSymbol(
        market=series.market,
        symbol=series.symbol,
        latest_price=latest.close,
        momentum_pct=round(momentum_pct, SCORE_PRECISION),
        breakout_pct=round(breakout_pct, SCORE_PRECISION),
        volume_ratio=round(volume_ratio, SCORE_PRECISION),
        volatility_pct=round(volatility_pct, SCORE_PRECISION),
        score=round(score, SCORE_PRECISION),
        selected=False,
        reason=_reason(momentum_pct, breakout_pct, volume_ratio),
    )


def _append_candidate_fill(
    candidate: ScreenedSymbol,
    per_position_notional: float,
    live_paper_log_path: Path,
) -> LivePaperExecutionResult:
    result = LivePaperExecutionResult(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        intent=LiveOrderIntent(
            market=candidate.market,
            symbol=candidate.symbol,
            side=OrderSide.BUY,
            quantity=round(per_position_notional / candidate.latest_price, 8),
            price=candidate.latest_price,
            order_type=OrderType.LIMIT,
        ),
        fill_price=candidate.latest_price,
        notional=round(per_position_notional, 8),
        note=SCREENER_NOTE,
    )
    return append_live_paper_execution_log(result, live_paper_log_path)


def _append_new_candidate_fill(
    candidate: ScreenedSymbol,
    per_position_notional: float,
    live_paper_log_path: Path,
    open_symbols: set[tuple[Market, str]],
) -> LivePaperExecutionResult:
    result = _append_candidate_fill(candidate, per_position_notional, live_paper_log_path)
    open_symbols.add(_candidate_key(candidate))
    return result


def _score(
    momentum_pct: float,
    breakout_pct: float,
    volume_ratio: float,
    volatility_pct: float,
) -> float:
    return (
        momentum_pct * 2.0
        + breakout_pct * 1.5
        + min(max(volume_ratio - 1.0, 0.0), SCORE_VOLUME_CAP) * 3.0
        - volatility_pct * 0.1
    )


def _reason(momentum_pct: float, breakout_pct: float, volume_ratio: float) -> str:
    return (
        f"momentum {momentum_pct:.2f}%, breakout {breakout_pct:.2f}%, "
        f"volume ratio {volume_ratio:.2f}"
    )


def _pct_change(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return (current / baseline - 1.0) * 100


def _volume_ratio(latest: Candle, previous: tuple[Candle, ...]) -> float:
    average_volume = sum(candle.volume for candle in previous) / len(previous)
    if average_volume <= 0:
        return 1.0
    return latest.volume / average_volume


def _volatility_pct(candles: tuple[Candle, ...]) -> float:
    high = max(candle.high for candle in candles)
    low = min(candle.low for candle in candles)
    latest_close = candles[-1].close
    if latest_close <= 0:
        return 0.0
    return (high - low) / latest_close * 100


def _canonical_symbol(symbol: str) -> str:
    return symbol.upper().removesuffix(".KS")


def _candidate_key(candidate: ScreenedSymbol) -> tuple[Market, str]:
    return (candidate.market, _canonical_symbol(candidate.symbol))
