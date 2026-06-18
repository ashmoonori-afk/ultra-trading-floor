from dual_market_trader.broker import run_paper_backtest
from dual_market_trader.models import (
    CandidateConfig,
    Fill,
    FillReport,
    IterationReport,
    MarketBacktest,
    MarketReport,
    PaperBacktestRequest,
    RunConfig,
    StrategyPipelineReport,
    ValidationReport,
)
from dual_market_trader.sample_data import (
    primary_validation_scenarios,
    sample_candles,
    symbol_for_market,
)
from dual_market_trader.strategies import generate_candidates
from dual_market_trader.strategy_pipeline import (
    DEFAULT_GENERATIONS,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_PIPELINE_SEED,
    CandidateEvaluation,
    PipelineBacktestMetrics,
    build_strategy_pipeline,
    evolve_candidates,
)
from dual_market_trader.validation import (
    CandidateScenarioEvidence,
    ScenarioReturn,
    build_validation_decision,
)


def run_improvement_loop(config: RunConfig) -> ValidationReport:
    iterations: list[IterationReport] = []
    scenario_evidence: list[CandidateScenarioEvidence] = []
    seed_candidates = generate_candidates(config.max_iterations)
    for iteration, candidate in enumerate(seed_candidates, start=1):
        results = _run_scenario(config, candidate, "training")
        scenario_evidence.append(
            CandidateScenarioEvidence(
                iteration=iteration,
                scenario_returns=tuple(
                    ScenarioReturn(
                        name=scenario,
                        aggregate_daily_return_pct=round(
                            _aggregate_return(_run_scenario(config, candidate, scenario)),
                            4,
                        ),
                    )
                    for scenario in primary_validation_scenarios()
                ),
            ),
        )
        aggregate_return = _aggregate_return(results)
        iteration_report = IterationReport(
            iteration=iteration,
            strategy=candidate.strategy,
            threshold_pct=candidate.threshold_pct,
            allocation_fraction=candidate.allocation_fraction,
            aggregate_daily_return_pct=round(aggregate_return, 4),
            target_met=False,
            markets=tuple(_market_report(result) for result in results),
        )
        decision = build_validation_decision(
            (*iterations, iteration_report),
            config,
            tuple(scenario_evidence),
        )
        iterations = list(decision.iterations)
        if decision.target_met:
            break
    decision = build_validation_decision(tuple(iterations), config, tuple(scenario_evidence))
    pipeline = _build_pipeline_report(config, seed_candidates)
    return ValidationReport(
        target_daily_return_pct=config.target_daily_return_pct,
        target_met=decision.target_met,
        iterations_run=len(iterations),
        selected_iteration=decision.selected_iteration,
        iterations=decision.iterations,
        validation_status=decision.status,
        validation_summary=decision.summary,
        fallback_chain=decision.fallback_chain,
        strategy_pipeline=pipeline,
        optimal_strategy=pipeline.selected_candidate,
        caveat=(
            "Paper validation on deterministic bundled sample data; "
            "fallback is best available, not a live-return guarantee."
        ),
    )


def _aggregate_return(results: tuple[MarketBacktest, ...]) -> float:
    if not results:
        return 0.0
    return sum(result.daily_return_pct for result in results) / len(results)


def _run_scenario(
    config: RunConfig,
    candidate: CandidateConfig,
    scenario: str,
) -> tuple[MarketBacktest, ...]:
    return tuple(
        run_paper_backtest(
            PaperBacktestRequest(
                market=market,
                symbol=symbol_for_market(market),
                candles=sample_candles(market, scenario=scenario),
                candidate=candidate,
                initial_cash=config.initial_cash,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
                risk=config.risk,
            ),
        )
        for market in config.markets
    )


def _build_pipeline_report(
    config: RunConfig,
    seeds: tuple[CandidateConfig, ...],
) -> StrategyPipelineReport:
    pipeline_candidates = evolve_candidates(
        seeds,
        seed=DEFAULT_PIPELINE_SEED,
        generations=DEFAULT_GENERATIONS,
    )[:DEFAULT_MAX_CANDIDATES]
    evaluations = tuple(
        _candidate_evaluation(config, candidate) for candidate in pipeline_candidates
    )
    return build_strategy_pipeline(
        seeds,
        seed=DEFAULT_PIPELINE_SEED,
        generations=DEFAULT_GENERATIONS,
        max_candidates=DEFAULT_MAX_CANDIDATES,
        evaluations=evaluations,
    )


def _candidate_evaluation(
    config: RunConfig,
    candidate: CandidateConfig,
) -> CandidateEvaluation:
    training = _run_scenario(config, candidate, "training")
    scenario_returns = tuple(
        _aggregate_return(_run_scenario(config, candidate, scenario))
        for scenario in primary_validation_scenarios()
    )
    max_drawdown = max((market.max_drawdown_pct for market in training), default=0.0)
    trade_count = sum(market.trade_count for market in training)
    stability = _scenario_stability(scenario_returns)
    metrics = PipelineBacktestMetrics(
        aggregate_daily_return_pct=round(_aggregate_return(training), 4),
        max_drawdown_pct=round(max_drawdown, 4),
        trade_count=trade_count,
        scenario_stability_pct=stability,
    )
    return CandidateEvaluation(
        candidate=candidate,
        metrics=metrics,
        passed_constraints=_passes_pipeline_constraints(config, training, scenario_returns),
    )


def _scenario_stability(scenario_returns: tuple[float, ...]) -> float:
    if not scenario_returns:
        return 0.0
    spread = max(scenario_returns) - min(scenario_returns)
    return round(max(0.0, 1.0 - spread / 10), 4)


def _passes_pipeline_constraints(
    config: RunConfig,
    training: tuple[MarketBacktest, ...],
    scenario_returns: tuple[float, ...],
) -> bool:
    return (
        _aggregate_return(training) >= config.target_daily_return_pct
        and all(market.trade_count > 0 for market in training)
        and all(market.daily_return_pct >= 0 for market in training)
        and all(market.max_drawdown_pct <= config.risk.max_daily_loss_pct for market in training)
        and all(item >= config.target_daily_return_pct for item in scenario_returns)
    )


def _market_report(result: MarketBacktest) -> MarketReport:
    return MarketReport(
        market=result.market,
        symbol=result.symbol,
        daily_return_pct=result.daily_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        trade_count=result.trade_count,
        fills=tuple(_fill_report(fill) for fill in result.fills),
    )


def _fill_report(fill: Fill) -> FillReport:
    return FillReport(
        market=fill.market,
        symbol=fill.symbol,
        side=fill.side,
        quantity=fill.quantity,
        price=fill.price,
        fee=fill.fee,
        timestamp=fill.timestamp,
    )
