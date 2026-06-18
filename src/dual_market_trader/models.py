from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


@unique
class Market(StrEnum):
    KR = "kr"
    US = "us"


@unique
class StrategyKind(StrEnum):
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    BUY_HOLD = "buy_hold"


@unique
class ValidationStatus(StrEnum):
    PASSED = "pass"
    FALLBACK = "fallback"
    FAIL = "fail"
    LEGACY = "legacy"


PipelineStage = Literal[
    "validation",
    "modification",
    "evolution",
    "ml_scoring",
    "optimal_selection",
]


class CandidateLineage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    candidate_id: str
    parent_id: str | None
    generation: int = Field(ge=0)
    mutation_reason: str


class PipelineCandidateReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    candidate_id: str
    strategy: StrategyKind
    threshold_pct: float
    allocation_fraction: float
    lookback: int
    score: float
    aggregate_daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    scenario_stability_pct: float
    passed_constraints: bool
    evaluation_complete: bool
    lineage: CandidateLineage


class OptimalStrategyReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    candidate_id: str
    strategy: StrategyKind
    score: float
    aggregate_daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    selected_by_objective: Literal[True]
    selection_reason: str


class StrategyPipelineReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    stages: tuple[PipelineStage, ...]
    seed: int
    generations: int = Field(ge=0)
    elite_count: int = Field(ge=1)
    mutation_count: int = Field(ge=0)
    scoring_model: str
    objective: str
    ranked_candidates: tuple[PipelineCandidateReport, ...]
    selected_candidate: OptimalStrategyReport | None


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    strategy: StrategyKind
    threshold_pct: float
    allocation_fraction: float
    lookback: int


@dataclass(frozen=True, slots=True)
class Fill:
    market: Market
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    timestamp: int


@dataclass(frozen=True, slots=True)
class MarketBacktest:
    market: Market
    symbol: str
    initial_equity: float
    final_equity: float
    daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    fills: tuple[Fill, ...]


@dataclass(frozen=True, slots=True)
class PaperBacktestRequest:
    market: Market
    symbol: str
    candles: tuple[Candle, ...]
    candidate: CandidateConfig
    initial_cash: float
    fee_bps: float
    slippage_bps: float
    risk: RiskConfig


@dataclass(frozen=True, slots=True)
class FillContext:
    market: Market
    symbol: str
    candle: Candle
    cost_rate: float


class RiskConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    max_position_fraction: float = Field(gt=0, le=1)
    max_daily_loss_pct: float = Field(gt=0, le=100)
    max_trades_per_market: int = Field(ge=1, le=100)


class RunConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    mode: Literal["paper"]
    target_daily_return_pct: float = Field(gt=0, le=20)
    max_iterations: int = Field(ge=1, le=100)
    markets: tuple[Market, ...]
    initial_cash: float = Field(gt=0)
    fee_bps: float = Field(ge=0, le=100)
    slippage_bps: float = Field(ge=0, le=100)
    risk: RiskConfig

    def with_overrides(
        self,
        *,
        markets: tuple[Market, ...] | None,
        target_daily_return_pct: float | None,
    ) -> RunConfig:
        return self.model_copy(
            update={
                "markets": markets if markets is not None else self.markets,
                "target_daily_return_pct": (
                    target_daily_return_pct
                    if target_daily_return_pct is not None
                    else self.target_daily_return_pct
                ),
            },
        )


class FillReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    timestamp: int


class MarketReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str
    daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    fills: tuple[FillReport, ...]


class IterationReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    iteration: int
    strategy: StrategyKind
    threshold_pct: float
    allocation_fraction: float
    aggregate_daily_return_pct: float
    target_met: bool
    markets: tuple[MarketReport, ...]


class FallbackCandidateReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    iteration: int
    strategy: StrategyKind
    aggregate_daily_return_pct: float
    failed_criteria: tuple[str, ...]
    selected_as_fallback: bool = False


class ValidationSummary(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    validation_status: ValidationStatus
    fallback_used: bool
    evaluated_candidates: int
    passed_criteria: tuple[str, ...]
    failed_criteria: tuple[str, ...]
    best_available_strategy: StrategyKind | None
    validation_scenarios: tuple[str, ...] = ()
    repeatability_runs: int = Field(ge=0, default=0)


class ValidationReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    mode: Literal["paper"] = "paper"
    guaranteed: Literal[False] = False
    live_order_enabled: Literal[False] = False
    target_daily_return_pct: float
    target_met: bool
    iterations_run: int
    selected_iteration: IterationReport | None
    iterations: tuple[IterationReport, ...]
    validation_status: ValidationStatus
    validation_summary: ValidationSummary
    fallback_chain: tuple[FallbackCandidateReport, ...]
    strategy_pipeline: StrategyPipelineReport
    optimal_strategy: OptimalStrategyReport | None
    caveat: str


class MarketPerformanceEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str
    daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int


class PerformanceLogEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    recorded_at: str
    mode: Literal["paper"] = "paper"
    guaranteed: Literal[False] = False
    live_order_enabled: Literal[False] = False
    target_daily_return_pct: float
    target_met: bool
    iterations_run: int
    selected_strategy: StrategyKind | None
    aggregate_daily_return_pct: float | None
    validation_status: ValidationStatus = ValidationStatus.LEGACY
    fallback_used: bool = False
    fallback_strategy: StrategyKind | None = None
    failed_criteria: tuple[str, ...] = ()
    pipeline_score: float | None = None
    optimal_strategy: StrategyKind | None = None
    markets: tuple[MarketPerformanceEntry, ...]
    caveat: str
