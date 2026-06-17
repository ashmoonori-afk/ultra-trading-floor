from dual_market_trader.broker import run_paper_backtest
from dual_market_trader.models import (
    Fill,
    FillReport,
    IterationReport,
    MarketBacktest,
    MarketReport,
    PaperBacktestRequest,
    RunConfig,
    ValidationReport,
)
from dual_market_trader.sample_data import sample_candles, symbol_for_market
from dual_market_trader.strategies import generate_candidates


def run_improvement_loop(config: RunConfig) -> ValidationReport:
    iterations: list[IterationReport] = []
    selected: IterationReport | None = None
    for iteration, candidate in enumerate(generate_candidates(config.max_iterations), start=1):
        results = tuple(
            run_paper_backtest(
                PaperBacktestRequest(
                    market=market,
                    symbol=symbol_for_market(market),
                    candles=sample_candles(market),
                    candidate=candidate,
                    initial_cash=config.initial_cash,
                    fee_bps=config.fee_bps,
                    slippage_bps=config.slippage_bps,
                    risk=config.risk,
                ),
            )
            for market in config.markets
        )
        aggregate_return = _aggregate_return(results)
        target_met = aggregate_return >= config.target_daily_return_pct and all(
            result.trade_count > 0 for result in results
        )
        iteration_report = IterationReport(
            iteration=iteration,
            strategy=candidate.strategy,
            threshold_pct=candidate.threshold_pct,
            allocation_fraction=candidate.allocation_fraction,
            aggregate_daily_return_pct=round(aggregate_return, 4),
            target_met=target_met,
            markets=tuple(_market_report(result) for result in results),
        )
        iterations.append(iteration_report)
        if target_met:
            selected = iteration_report
            break
    return ValidationReport(
        target_daily_return_pct=config.target_daily_return_pct,
        target_met=selected is not None,
        iterations_run=len(iterations),
        selected_iteration=selected,
        iterations=tuple(iterations),
        caveat=(
            "Paper validation on deterministic bundled sample data; not a live-return guarantee."
        ),
    )


def _aggregate_return(results: tuple[MarketBacktest, ...]) -> float:
    if not results:
        return 0.0
    return sum(result.daily_return_pct for result in results) / len(results)


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
