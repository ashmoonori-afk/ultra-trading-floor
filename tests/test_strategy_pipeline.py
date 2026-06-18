from dual_market_trader.models import CandidateConfig, StrategyKind
from dual_market_trader.strategy_pipeline import (
    CandidateEvaluation,
    PipelineBacktestMetrics,
    build_strategy_pipeline,
    evolve_candidates,
    mutate_candidate,
    score_candidate,
)


def test_strategy_pipeline_is_reproducible_for_same_seed() -> None:
    seeds = (
        CandidateConfig(
            StrategyKind.MOMENTUM, threshold_pct=1.0, allocation_fraction=0.5, lookback=1
        ),
        CandidateConfig(
            StrategyKind.BREAKOUT, threshold_pct=0.4, allocation_fraction=0.8, lookback=2
        ),
    )

    candidates = evolve_candidates(seeds, seed=7, generations=2)[:6]
    evaluations = tuple(
        _passing_evaluation(candidate, index) for index, candidate in enumerate(candidates)
    )

    first = build_strategy_pipeline(
        seeds,
        seed=7,
        generations=2,
        max_candidates=6,
        evaluations=evaluations,
    )
    second = build_strategy_pipeline(
        seeds,
        seed=7,
        generations=2,
        max_candidates=6,
        evaluations=evaluations,
    )

    assert first == second
    assert first.stages == (
        "validation",
        "modification",
        "evolution",
        "ml_scoring",
        "optimal_selection",
    )
    assert first.selected_candidate is not None
    assert first.selected_candidate.strategy is StrategyKind.BREAKOUT


def test_mutate_candidate_stays_inside_strategy_bounds() -> None:
    candidate = CandidateConfig(
        StrategyKind.MOMENTUM,
        threshold_pct=0.05,
        allocation_fraction=0.98,
        lookback=1,
    )

    mutated = tuple(mutate_candidate(candidate, seed=seed) for seed in range(12))

    assert all(0.0 <= item.threshold_pct <= 5.0 for item in mutated)
    assert all(0.1 <= item.allocation_fraction <= 1.0 for item in mutated)
    assert all(1 <= item.lookback <= 5 for item in mutated)


def test_ml_score_penalizes_worse_drawdown_when_return_and_trades_match() -> None:
    better = score_candidate(
        PipelineBacktestMetrics(
            aggregate_daily_return_pct=6.0,
            max_drawdown_pct=1.0,
            trade_count=4,
            scenario_stability_pct=0.8,
        ),
    )
    worse = score_candidate(
        PipelineBacktestMetrics(
            aggregate_daily_return_pct=6.0,
            max_drawdown_pct=6.0,
            trade_count=4,
            scenario_stability_pct=0.8,
        ),
    )

    assert better > worse


def test_pipeline_does_not_select_strategy_without_complete_evidence() -> None:
    seeds = (
        CandidateConfig(
            StrategyKind.MOMENTUM, threshold_pct=1.0, allocation_fraction=0.5, lookback=1
        ),
    )

    report = build_strategy_pipeline(seeds, seed=7, generations=1, max_candidates=4)

    assert report.selected_candidate is None
    assert report.ranked_candidates
    assert all(not candidate.evaluation_complete for candidate in report.ranked_candidates)
    assert all(not candidate.passed_constraints for candidate in report.ranked_candidates)


def test_pipeline_lineage_records_mutation_parent_and_generation() -> None:
    seeds = (
        CandidateConfig(
            StrategyKind.MOMENTUM, threshold_pct=1.0, allocation_fraction=0.5, lookback=1
        ),
    )
    candidates = evolve_candidates(seeds, seed=7, generations=1)[:4]
    evaluations = tuple(
        _passing_evaluation(candidate, index) for index, candidate in enumerate(candidates)
    )

    report = build_strategy_pipeline(
        seeds,
        seed=7,
        generations=1,
        max_candidates=4,
        evaluations=evaluations,
    )

    mutated = [
        candidate for candidate in report.ranked_candidates if candidate.lineage.generation > 0
    ]
    assert mutated
    assert all(candidate.lineage.parent_id is not None for candidate in mutated)
    assert all(
        candidate.lineage.mutation_reason == "deterministic bounded mutation"
        for candidate in mutated
    )


def _passing_evaluation(
    candidate: CandidateConfig,
    index: int,
) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate=candidate,
        metrics=PipelineBacktestMetrics(
            aggregate_daily_return_pct=6.0 + index,
            max_drawdown_pct=0.5,
            trade_count=2,
            scenario_stability_pct=0.8,
        ),
        passed_constraints=True,
    )
