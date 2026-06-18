from dataclasses import dataclass

from dual_market_trader.models import (
    FallbackCandidateReport,
    IterationReport,
    RunConfig,
    ValidationStatus,
    ValidationSummary,
)

MIN_REPEATABILITY_RUNS = 2


@dataclass(frozen=True, slots=True)
class ScenarioReturn:
    name: str
    aggregate_daily_return_pct: float


@dataclass(frozen=True, slots=True)
class CandidateScenarioEvidence:
    iteration: int
    scenario_returns: tuple[ScenarioReturn, ...]


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    iteration: IterationReport
    passed_criteria: tuple[str, ...]
    failed_criteria: tuple[str, ...]
    scenario_returns: tuple[ScenarioReturn, ...]


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    selected_iteration: IterationReport | None
    target_met: bool
    status: ValidationStatus
    summary: ValidationSummary
    fallback_chain: tuple[FallbackCandidateReport, ...]
    iterations: tuple[IterationReport, ...]


def build_validation_decision(
    iterations: tuple[IterationReport, ...],
    config: RunConfig,
    scenario_evidence: tuple[CandidateScenarioEvidence, ...] = (),
) -> ValidationDecision:
    validations = tuple(
        _validate_candidate(iteration, config, _scenario_returns(iteration, scenario_evidence))
        for iteration in iterations
    )
    updated_iterations = tuple(
        validation.iteration.model_copy(update={"target_met": not validation.failed_criteria})
        for validation in validations
    )
    updated_validations = tuple(
        CandidateValidation(
            iteration=iteration,
            passed_criteria=validation.passed_criteria,
            failed_criteria=validation.failed_criteria,
            scenario_returns=validation.scenario_returns,
        )
        for iteration, validation in zip(updated_iterations, validations, strict=True)
    )
    passing = tuple(
        validation for validation in updated_validations if not validation.failed_criteria
    )
    if passing:
        return _pass_decision(passing[0], updated_iterations)
    if updated_validations:
        return _fallback_decision(updated_validations, updated_iterations)
    return _fail_decision()


def _validate_candidate(
    iteration: IterationReport,
    config: RunConfig,
    scenario_returns: tuple[ScenarioReturn, ...],
) -> CandidateValidation:
    passed: list[str] = []
    failed: list[str] = []
    if iteration.aggregate_daily_return_pct >= config.target_daily_return_pct:
        passed.append("aggregate_return_at_or_above_target")
    else:
        failed.append("aggregate_return_below_target")
    if all(market.trade_count > 0 for market in iteration.markets):
        passed.append("all_markets_traded")
    else:
        failed.append("market_without_trade")
    if all(market.daily_return_pct >= 0 for market in iteration.markets):
        passed.append("all_markets_non_negative_return")
    else:
        failed.append("negative_market_return")
    if all(
        market.max_drawdown_pct <= config.risk.max_daily_loss_pct for market in iteration.markets
    ):
        passed.append("drawdown_within_limit")
    else:
        failed.append("drawdown_above_limit")
    if all(
        item.aggregate_daily_return_pct >= config.target_daily_return_pct
        for item in scenario_returns
    ):
        passed.append("out_of_sample_target")
    else:
        failed.append("validation_scenario_below_target")
    if len(scenario_returns) >= MIN_REPEATABILITY_RUNS:
        passed.append("repeatability")
    else:
        failed.append("insufficient_repeatability_runs")
    return CandidateValidation(iteration, tuple(passed), tuple(failed), scenario_returns)


def _pass_decision(
    validation: CandidateValidation,
    iterations: tuple[IterationReport, ...],
) -> ValidationDecision:
    passed_criteria = (*validation.passed_criteria, "strategy_selected_without_fallback")
    summary = ValidationSummary(
        validation_status=ValidationStatus.PASSED,
        fallback_used=False,
        evaluated_candidates=len(iterations),
        passed_criteria=passed_criteria,
        failed_criteria=(),
        best_available_strategy=validation.iteration.strategy,
        validation_scenarios=tuple(item.name for item in validation.scenario_returns),
        repeatability_runs=len(validation.scenario_returns),
    )
    return ValidationDecision(
        selected_iteration=validation.iteration,
        target_met=True,
        status=ValidationStatus.PASSED,
        summary=summary,
        fallback_chain=(),
        iterations=iterations,
    )


def _fallback_decision(
    validations: tuple[CandidateValidation, ...],
    iterations: tuple[IterationReport, ...],
) -> ValidationDecision:
    best = max(
        validations,
        key=lambda item: (
            item.iteration.aggregate_daily_return_pct,
            len(item.passed_criteria),
            -item.iteration.iteration,
        ),
    )
    summary = ValidationSummary(
        validation_status=ValidationStatus.FALLBACK,
        fallback_used=True,
        evaluated_candidates=len(validations),
        passed_criteria=best.passed_criteria,
        failed_criteria=best.failed_criteria,
        best_available_strategy=best.iteration.strategy,
        validation_scenarios=tuple(item.name for item in best.scenario_returns),
        repeatability_runs=len(best.scenario_returns),
    )
    chain = tuple(
        _fallback_candidate(
            item.iteration,
            item.failed_criteria,
            selected=item.iteration.iteration == best.iteration.iteration,
        )
        for item in validations
    )
    return ValidationDecision(
        selected_iteration=best.iteration,
        target_met=False,
        status=ValidationStatus.FALLBACK,
        summary=summary,
        fallback_chain=chain,
        iterations=iterations,
    )


def _fail_decision() -> ValidationDecision:
    summary = ValidationSummary(
        validation_status=ValidationStatus.FAIL,
        fallback_used=False,
        evaluated_candidates=0,
        passed_criteria=(),
        failed_criteria=("no_candidates_evaluated",),
        best_available_strategy=None,
        validation_scenarios=(),
        repeatability_runs=0,
    )
    return ValidationDecision(
        selected_iteration=None,
        target_met=False,
        status=ValidationStatus.FAIL,
        summary=summary,
        fallback_chain=(),
        iterations=(),
    )


def _fallback_candidate(
    iteration: IterationReport,
    failed_criteria: tuple[str, ...],
    *,
    selected: bool,
) -> FallbackCandidateReport:
    return FallbackCandidateReport(
        iteration=iteration.iteration,
        strategy=iteration.strategy,
        aggregate_daily_return_pct=iteration.aggregate_daily_return_pct,
        failed_criteria=failed_criteria,
        selected_as_fallback=selected,
    )


def _scenario_returns(
    iteration: IterationReport,
    evidence: tuple[CandidateScenarioEvidence, ...],
) -> tuple[ScenarioReturn, ...]:
    for item in evidence:
        if item.iteration == iteration.iteration:
            return item.scenario_returns
    return (ScenarioReturn("training", iteration.aggregate_daily_return_pct),)
