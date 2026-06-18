from pathlib import Path

from dual_market_trader.config import load_run_config
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.models import Market, ValidationStatus


def test_run_improvement_loop_meets_target_with_kr_and_us_sample_data() -> None:
    config = load_run_config(Path("examples/paper_target_5.json"))

    report = run_improvement_loop(config)

    assert report.mode == "paper"
    assert report.guaranteed is False
    assert report.live_order_enabled is False
    assert report.target_met is True
    assert report.selected_iteration is not None
    assert report.validation_status is ValidationStatus.PASSED
    assert report.validation_summary.fallback_used is False
    assert report.validation_summary.evaluated_candidates == 4
    assert report.validation_summary.passed_criteria == (
        "aggregate_return_at_or_above_target",
        "all_markets_traded",
        "all_markets_non_negative_return",
        "drawdown_within_limit",
        "out_of_sample_target",
        "repeatability",
        "strategy_selected_without_fallback",
    )
    markets = {market_report.market for market_report in report.selected_iteration.markets}
    assert markets == {Market.KR, Market.US}
    assert report.selected_iteration.aggregate_daily_return_pct >= 5.0


def test_run_improvement_loop_records_failed_iterations_before_target() -> None:
    config = load_run_config(Path("examples/paper_target_5.json"))

    report = run_improvement_loop(config)

    assert report.iterations_run > 1
    assert report.iterations[0].target_met is False
    assert report.iterations[-1].target_met is True


def test_run_improvement_loop_reports_strategy_pipeline_and_optimal_strategy() -> None:
    config = load_run_config(Path("examples/paper_target_5.json"))

    report = run_improvement_loop(config)

    assert report.strategy_pipeline.stages == (
        "validation",
        "modification",
        "evolution",
        "ml_scoring",
        "optimal_selection",
    )
    assert report.strategy_pipeline.seed == 7
    assert report.strategy_pipeline.generations == 2
    assert report.strategy_pipeline.ranked_candidates
    assert report.optimal_strategy is not None
    assert report.optimal_strategy.selected_by_objective is True
    assert report.optimal_strategy.selection_reason == (
        "highest local ML score among candidates satisfying validation constraints"
    )
    assert report.optimal_strategy.score == report.strategy_pipeline.ranked_candidates[0].score


def test_run_improvement_loop_reports_fallback_chain_when_target_is_not_validated() -> None:
    config = load_run_config(Path("examples/paper_target_5.json")).with_overrides(
        markets=(Market.KR, Market.US),
        target_daily_return_pct=20.0,
    )

    report = run_improvement_loop(config)

    assert report.target_met is False
    assert report.validation_status is ValidationStatus.FALLBACK
    assert report.selected_iteration is not None
    assert report.selected_iteration.strategy.value == "buy_hold"
    assert report.validation_summary.fallback_used is True
    assert report.validation_summary.best_available_strategy == "buy_hold"
    assert report.validation_summary.failed_criteria == (
        "aggregate_return_below_target",
        "validation_scenario_below_target",
    )
    assert len(report.fallback_chain) == report.iterations_run
    assert report.fallback_chain[-1].selected_as_fallback is True
