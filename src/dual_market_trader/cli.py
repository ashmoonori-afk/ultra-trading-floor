from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console

from dual_market_trader.config import load_run_config
from dual_market_trader.dashboard import serve_dashboard
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.live_cli import (
    DEFAULT_LIVE_EXECUTION_LOG,
    DEFAULT_LIVE_PAPER_EXECUTION_LOG,
    UnsupportedMarketError,
    parse_market,
    register_live_commands,
)
from dual_market_trader.models import Market
from dual_market_trader.reporting import append_performance_log, append_run_log, write_report

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
DEFAULT_REPORT_OUTPUT: Final = Path(".omo/evidence/run-once-report.json")
DEFAULT_CONFIG_PATH: Final = Path("examples/paper_target_5.json")
DEFAULT_PERFORMANCE_LOG: Final = Path(".data/performance-log.jsonl")
register_live_commands(app, console)


@app.command("run-once")
def run_once(
    config: Annotated[
        Path,
        typer.Option("--config", exists=True, dir_okay=False, readable=True),
    ] = DEFAULT_CONFIG_PATH,
    markets: Annotated[
        str | None,
        typer.Option("--markets", help="Comma-separated markets: KR,US"),
    ] = None,
    target_daily_return_pct: Annotated[
        float | None,
        typer.Option("--target-daily-return-pct", min=0.000001),
    ] = None,
    sample: Annotated[
        str,
        typer.Option("--sample", help="Only deterministic is supported in this paper prototype."),
    ] = "deterministic",
    evidence_dir: Annotated[
        Path | None,
        typer.Option("--evidence-dir", file_okay=False),
    ] = None,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = DEFAULT_REPORT_OUTPUT,
) -> None:
    if sample != "deterministic":
        console.print("only deterministic sample data is supported")
        raise typer.Exit(code=2)
    run_config = load_run_config(config).with_overrides(
        markets=_parse_markets(markets),
        target_daily_return_pct=target_daily_return_pct,
    )
    report_output = evidence_dir / "run-once-report.json" if evidence_dir is not None else output
    report = run_improvement_loop(run_config)
    write_report(report, report_output)
    append_run_log(report, Path(".data/paper-runs.jsonl"))
    performance_entry = append_performance_log(report, DEFAULT_PERFORMANCE_LOG)
    selected = report.selected_iteration
    optimal = report.optimal_strategy
    strategy = selected.strategy.value if selected is not None else "none"
    fallback_strategy = report.validation_summary.best_available_strategy
    console.print(
        {
            "mode": report.mode,
            "guaranteed": report.guaranteed,
            "live_order_enabled": report.live_order_enabled,
            "target_daily_return_pct": report.target_daily_return_pct,
            "target_met": report.target_met,
            "validation_status": report.validation_status.value,
            "fallback_used": report.validation_summary.fallback_used,
            "best_available_strategy": (
                fallback_strategy.value if fallback_strategy is not None else "none"
            ),
            "failed_criteria": report.validation_summary.failed_criteria,
            "strategy_pipeline": report.strategy_pipeline.stages,
            "ml_score": optimal.score if optimal is not None else None,
            "optimal_strategy": optimal.strategy.value if optimal is not None else "none",
            "iterations_run": report.iterations_run,
            "selected_strategy": strategy,
            "output": str(report_output),
            "performance_log": str(DEFAULT_PERFORMANCE_LOG),
            "performance_logged_at": performance_entry.recorded_at,
        },
    )


@app.command("dashboard")
def dashboard(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    log_path: Annotated[Path, typer.Option("--log", dir_okay=False)] = DEFAULT_PERFORMANCE_LOG,
    live_log_path: Annotated[
        Path,
        typer.Option("--live-log", dir_okay=False),
    ] = DEFAULT_LIVE_EXECUTION_LOG,
    live_paper_log_path: Annotated[
        Path,
        typer.Option("--live-paper-log", dir_okay=False),
    ] = DEFAULT_LIVE_PAPER_EXECUTION_LOG,
) -> None:
    console.print(f"serving paper dashboard at http://{host}:{port}")
    console.print(f"performance log: {log_path}")
    console.print(f"live execution log: {live_log_path}")
    console.print(f"live paper execution log: {live_paper_log_path}")
    serve_dashboard(
        host=host,
        port=port,
        log_path=log_path,
        live_log_path=live_log_path,
        live_paper_log_path=live_paper_log_path,
    )


def _parse_markets(raw: str | None) -> tuple[Market, ...] | None:
    if raw is None:
        return None
    parsed: list[Market] = []
    for item in raw.split(","):
        try:
            parsed.append(parse_market(item))
        except UnsupportedMarketError as exc:
            console.print(f"unsupported market: {item}")
            raise typer.Exit(code=2) from exc
    return tuple(parsed)
