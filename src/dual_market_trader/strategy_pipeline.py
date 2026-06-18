from dataclasses import dataclass
from typing import Final

from dual_market_trader.models import (
    CandidateConfig,
    CandidateLineage,
    OptimalStrategyReport,
    PipelineCandidateReport,
    StrategyPipelineReport,
)

PIPELINE_STAGES: Final = (
    "validation",
    "modification",
    "evolution",
    "ml_scoring",
    "optimal_selection",
)
SCORING_MODEL: Final = "local_weighted_linear_score_v1"
OBJECTIVE: Final = "maximize return and stability while penalizing drawdown and turnover"
SELECTION_REASON: Final = (
    "highest local ML score among candidates satisfying validation constraints"
)
DEFAULT_PIPELINE_SEED: Final = 7
DEFAULT_GENERATIONS: Final = 2
DEFAULT_ELITE_COUNT: Final = 2
DEFAULT_MAX_CANDIDATES: Final = 12


@dataclass(frozen=True, slots=True)
class PipelineBacktestMetrics:
    aggregate_daily_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    scenario_stability_pct: float


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate: CandidateConfig
    metrics: PipelineBacktestMetrics
    passed_constraints: bool


@dataclass(frozen=True, slots=True)
class EvolvedCandidate:
    candidate: CandidateConfig
    lineage: CandidateLineage


def mutate_candidate(candidate: CandidateConfig, *, seed: int) -> CandidateConfig:
    threshold_shift = _choice((-0.4, -0.2, 0.2, 0.4), seed)
    allocation_shift = _choice((-0.08, -0.04, 0.04, 0.08), seed // 3)
    lookback_shift = _choice((-1, 0, 1), seed // 7)
    return CandidateConfig(
        strategy=candidate.strategy,
        threshold_pct=round(_clamp(candidate.threshold_pct + threshold_shift, 0.0, 5.0), 4),
        allocation_fraction=round(
            _clamp(candidate.allocation_fraction + allocation_shift, 0.1, 1.0),
            4,
        ),
        lookback=int(_clamp(candidate.lookback + lookback_shift, 1, 5)),
    )


def score_candidate(metrics: PipelineBacktestMetrics) -> float:
    turnover_penalty = max(metrics.trade_count - 4, 0) * 0.12
    raw_score = (
        metrics.aggregate_daily_return_pct
        - metrics.max_drawdown_pct * 0.7
        + metrics.scenario_stability_pct * 0.35
        - turnover_penalty
    )
    return round(raw_score, 6)


def build_strategy_pipeline(
    seeds: tuple[CandidateConfig, ...],
    *,
    seed: int = DEFAULT_PIPELINE_SEED,
    generations: int = DEFAULT_GENERATIONS,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    evaluations: tuple[CandidateEvaluation, ...] = (),
) -> StrategyPipelineReport:
    candidates = evolve_candidate_records(seeds, seed=seed, generations=generations)
    ranked = _rank_candidates(candidates[:max_candidates], evaluations)
    selected = _optimal_strategy(ranked)
    mutation_count = sum(1 for item in candidates if item.lineage.generation > 0)
    return StrategyPipelineReport(
        stages=PIPELINE_STAGES,
        seed=seed,
        generations=generations,
        elite_count=min(DEFAULT_ELITE_COUNT, len(seeds)),
        mutation_count=mutation_count,
        scoring_model=SCORING_MODEL,
        objective=OBJECTIVE,
        ranked_candidates=ranked,
        selected_candidate=selected,
    )


def evolve_candidates(
    seeds: tuple[CandidateConfig, ...],
    *,
    seed: int,
    generations: int,
) -> tuple[CandidateConfig, ...]:
    return tuple(
        item.candidate
        for item in evolve_candidate_records(seeds, seed=seed, generations=generations)
    )


def evolve_candidate_records(
    seeds: tuple[CandidateConfig, ...],
    *,
    seed: int,
    generations: int,
) -> tuple[EvolvedCandidate, ...]:
    records = tuple(
        EvolvedCandidate(
            candidate=candidate,
            lineage=CandidateLineage(
                candidate_id=_candidate_id(candidate),
                parent_id=None,
                generation=0,
                mutation_reason="seed candidate",
            ),
        )
        for candidate in tuple(dict.fromkeys(seeds))
    )
    population = _dedupe_records(records)
    for generation in range(1, generations + 1):
        elite = population[:DEFAULT_ELITE_COUNT]
        mutated = tuple(
            _mutated_record(
                item,
                generation=generation,
                seed=seed + generation * 101 + index,
            )
            for index, item in enumerate(population)
        )
        population = _dedupe_records((*elite, *mutated, *population))
    return population


def _rank_candidates(
    candidates: tuple[EvolvedCandidate, ...],
    evaluations: tuple[CandidateEvaluation, ...],
) -> tuple[PipelineCandidateReport, ...]:
    evaluation_by_candidate = {evaluation.candidate: evaluation for evaluation in evaluations}
    reports = tuple(
        _candidate_report(
            candidate,
            index,
            evaluation_by_candidate.get(candidate.candidate),
        )
        for index, candidate in enumerate(candidates, start=1)
    )
    ranked = sorted(
        reports,
        key=lambda item: (
            item.evaluation_complete,
            item.passed_constraints,
            item.score,
            item.aggregate_daily_return_pct,
            -item.max_drawdown_pct,
        ),
        reverse=True,
    )
    return tuple(report.model_copy(update={"rank": rank}) for rank, report in enumerate(ranked, 1))


def _candidate_report(
    candidate: EvolvedCandidate,
    index: int,
    evaluation: CandidateEvaluation | None,
) -> PipelineCandidateReport:
    metrics = (
        evaluation.metrics
        if evaluation is not None
        else PipelineBacktestMetrics(
            aggregate_daily_return_pct=0.0,
            max_drawdown_pct=0.0,
            trade_count=0,
            scenario_stability_pct=0.0,
        )
    )
    return PipelineCandidateReport(
        rank=index,
        candidate_id=_candidate_id(candidate.candidate),
        strategy=candidate.candidate.strategy,
        threshold_pct=candidate.candidate.threshold_pct,
        allocation_fraction=candidate.candidate.allocation_fraction,
        lookback=candidate.candidate.lookback,
        score=score_candidate(metrics) if evaluation is not None else 0.0,
        aggregate_daily_return_pct=metrics.aggregate_daily_return_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        trade_count=metrics.trade_count,
        scenario_stability_pct=metrics.scenario_stability_pct,
        passed_constraints=evaluation.passed_constraints if evaluation is not None else False,
        evaluation_complete=evaluation is not None,
        lineage=candidate.lineage,
    )


def _optimal_strategy(
    ranked: tuple[PipelineCandidateReport, ...],
) -> OptimalStrategyReport | None:
    for item in ranked:
        if item.evaluation_complete and item.passed_constraints:
            return OptimalStrategyReport(
                candidate_id=item.candidate_id,
                strategy=item.strategy,
                score=item.score,
                aggregate_daily_return_pct=item.aggregate_daily_return_pct,
                max_drawdown_pct=item.max_drawdown_pct,
                trade_count=item.trade_count,
                selected_by_objective=True,
                selection_reason=SELECTION_REASON,
            )
    return None


def _mutated_record(
    item: EvolvedCandidate,
    *,
    generation: int,
    seed: int,
) -> EvolvedCandidate:
    candidate = mutate_candidate(item.candidate, seed=seed)
    return EvolvedCandidate(
        candidate=candidate,
        lineage=CandidateLineage(
            candidate_id=_candidate_id(candidate),
            parent_id=_candidate_id(item.candidate),
            generation=generation,
            mutation_reason="deterministic bounded mutation",
        ),
    )


def _dedupe_records(records: tuple[EvolvedCandidate, ...]) -> tuple[EvolvedCandidate, ...]:
    by_candidate: dict[CandidateConfig, EvolvedCandidate] = {}
    for record in records:
        if record.candidate not in by_candidate:
            by_candidate[record.candidate] = record
    return tuple(by_candidate.values())


def _candidate_id(candidate: CandidateConfig) -> str:
    return (
        f"{candidate.strategy.value}:"
        f"{candidate.threshold_pct:.4f}:"
        f"{candidate.allocation_fraction:.4f}:"
        f"{candidate.lookback}"
    )


def _choice(values: tuple[float, ...], seed: int) -> float:
    return values[abs(seed) % len(values)]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(float(value), float(minimum)), float(maximum))
