from datetime import UTC, datetime
from pathlib import Path

from dual_market_trader.live_models import LiveOrderResult, LivePaperExecutionResult
from dual_market_trader.models import (
    MarketPerformanceEntry,
    PerformanceLogEntry,
    ValidationReport,
)


def write_report(report: ValidationReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def append_run_log(report: ValidationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(report.model_dump_json() + "\n")


def append_performance_log(report: ValidationReport, path: Path) -> PerformanceLogEntry:
    entry = build_performance_log_entry(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(entry.model_dump_json() + "\n")
    return entry


def append_live_execution_log(result: LiveOrderResult, path: Path) -> LiveOrderResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(result.model_dump_json() + "\n")
    return result


def append_live_paper_execution_log(
    result: LivePaperExecutionResult,
    path: Path,
) -> LivePaperExecutionResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(result.model_dump_json() + "\n")
    return result


def read_performance_log(path: Path) -> tuple[PerformanceLogEntry, ...]:
    if not path.exists():
        return ()
    return tuple(
        PerformanceLogEntry.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def read_live_execution_log(path: Path) -> tuple[LiveOrderResult, ...]:
    if not path.exists():
        return ()
    return tuple(
        LiveOrderResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def read_live_paper_execution_log(path: Path) -> tuple[LivePaperExecutionResult, ...]:
    if not path.exists():
        return ()
    return tuple(
        LivePaperExecutionResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def build_performance_log_entry(report: ValidationReport) -> PerformanceLogEntry:
    selected = report.selected_iteration
    optimal = report.optimal_strategy
    fallback_strategy = (
        report.validation_summary.best_available_strategy
        if report.validation_summary.fallback_used
        else None
    )
    return PerformanceLogEntry(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        target_daily_return_pct=report.target_daily_return_pct,
        target_met=report.target_met,
        iterations_run=report.iterations_run,
        selected_strategy=selected.strategy if selected is not None else None,
        aggregate_daily_return_pct=(
            selected.aggregate_daily_return_pct if selected is not None else None
        ),
        validation_status=report.validation_status,
        fallback_used=report.validation_summary.fallback_used,
        fallback_strategy=fallback_strategy,
        failed_criteria=report.validation_summary.failed_criteria,
        pipeline_score=optimal.score if optimal is not None else None,
        optimal_strategy=optimal.strategy if optimal is not None else None,
        markets=(
            tuple(
                MarketPerformanceEntry(
                    market=market.market,
                    symbol=market.symbol,
                    daily_return_pct=market.daily_return_pct,
                    max_drawdown_pct=market.max_drawdown_pct,
                    trade_count=market.trade_count,
                )
                for market in selected.markets
            )
            if selected is not None
            else ()
        ),
        caveat=report.caveat,
    )
