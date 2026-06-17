import os
from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console

from dual_market_trader.config import load_run_config
from dual_market_trader.dashboard import serve_dashboard
from dual_market_trader.execution import LiveExecutionConfig, run_live_execution_loop
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.live import LiveTradingDisabledError, require_live_trading_enabled
from dual_market_trader.live_models import LiveOrderIntent, OrderSide, OrderType
from dual_market_trader.models import Market
from dual_market_trader.reporting import append_performance_log, append_run_log, write_report
from dual_market_trader.toss import TossBrokerError, TossCtlBroker, TossCtlConfig

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
DEFAULT_REPORT_OUTPUT: Final = Path(".omo/evidence/run-once-report.json")
DEFAULT_CONFIG_PATH: Final = Path("examples/paper_target_5.json")
DEFAULT_PERFORMANCE_LOG: Final = Path(".data/performance-log.jsonl")
DEFAULT_LIVE_EXECUTION_LOG: Final = Path(".data/live-executions.jsonl")


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
    strategy = selected.strategy.value if selected is not None else "none"
    console.print(
        {
            "mode": report.mode,
            "guaranteed": report.guaranteed,
            "live_order_enabled": report.live_order_enabled,
            "target_daily_return_pct": report.target_daily_return_pct,
            "target_met": report.target_met,
            "iterations_run": report.iterations_run,
            "selected_strategy": strategy,
            "output": str(report_output),
            "performance_log": str(DEFAULT_PERFORMANCE_LOG),
            "performance_logged_at": performance_entry.recorded_at,
        },
    )


@app.command("trade-live")
def trade_live(
    symbol: Annotated[str, typer.Option("--symbol")],
    quantity: Annotated[float, typer.Option("--quantity", min=0.000001)],
    price: Annotated[float | None, typer.Option("--price", min=0.000001)] = None,
    market: Annotated[str, typer.Option("--market")] = "KR",
    side: Annotated[str, typer.Option("--side")] = "buy",
    evidence_dir: Annotated[
        Path | None,
        typer.Option("--evidence-dir", file_okay=False),
    ] = None,
    confirm_risk: Annotated[bool, typer.Option("--confirm-risk")] = False,
) -> None:
    _execute_live_order_command(
        market=market,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        evidence_dir=evidence_dir,
        confirm_risk=confirm_risk,
        max_cycles=1,
        interval_seconds=0,
    )


@app.command("run-live")
def run_live(
    symbol: Annotated[str, typer.Option("--symbol")],
    quantity: Annotated[float, typer.Option("--quantity", min=0.000001)],
    price: Annotated[float | None, typer.Option("--price", min=0.000001)] = None,
    market: Annotated[str, typer.Option("--market")] = "KR",
    side: Annotated[str, typer.Option("--side")] = "buy",
    max_cycles: Annotated[int, typer.Option("--max-cycles", min=1, max=10_000)] = 1,
    interval_seconds: Annotated[float, typer.Option("--interval-seconds", min=0)] = 30,
    evidence_dir: Annotated[
        Path | None,
        typer.Option("--evidence-dir", file_okay=False),
    ] = None,
    confirm_risk: Annotated[bool, typer.Option("--confirm-risk")] = False,
) -> None:
    _execute_live_order_command(
        market=market,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        evidence_dir=evidence_dir,
        confirm_risk=confirm_risk,
        max_cycles=max_cycles,
        interval_seconds=interval_seconds,
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
) -> None:
    console.print(f"serving paper dashboard at http://{host}:{port}")
    console.print(f"performance log: {log_path}")
    console.print(f"live execution log: {live_log_path}")
    serve_dashboard(host=host, port=port, log_path=log_path, live_log_path=live_log_path)


def _parse_markets(raw: str | None) -> tuple[Market, ...] | None:
    if raw is None:
        return None
    parsed: list[Market] = []
    for item in raw.split(","):
        try:
            parsed.append(_parse_market(item))
        except UnsupportedMarketError as exc:
            console.print(f"unsupported market: {item}")
            raise typer.Exit(code=2) from exc
    return tuple(parsed)


def _execute_live_order_command(
    *,
    market: str,
    symbol: str,
    side: str,
    quantity: float,
    price: float | None,
    evidence_dir: Path | None,
    confirm_risk: bool,
    max_cycles: int,
    interval_seconds: float,
) -> None:
    try:
        require_live_trading_enabled(os.environ, confirm_risk=confirm_risk)
    except LiveTradingDisabledError as exc:
        console.print(str(exc))
        raise typer.Exit(code=2) from exc
    if price is None:
        console.print("live Toss limit orders require --price")
        raise typer.Exit(code=2)
    intent = LiveOrderIntent(
        market=_parse_market_or_exit(market),
        symbol=symbol,
        side=_parse_side_or_exit(side),
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
    )
    live_log_path = (
        evidence_dir / "live-executions.jsonl"
        if evidence_dir is not None
        else DEFAULT_LIVE_EXECUTION_LOG
    )
    broker = TossCtlBroker(
        TossCtlConfig(
            env=os.environ,
            confirm_risk=confirm_risk,
            binary=os.environ.get("TOSS_CLI_BIN", "tossctl"),
        ),
    )
    try:
        results = run_live_execution_loop(
            LiveExecutionConfig(
                intent=intent,
                log_path=live_log_path,
                max_cycles=max_cycles,
                interval_seconds=interval_seconds,
            ),
            broker,
        )
    except TossBrokerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=2) from exc
    latest = results[-1]
    console.print(
        {
            "mode": "live",
            "broker": "toss",
            "orders_placed": len(results),
            "latest_order_id": latest.order_id,
            "live_execution_log": str(live_log_path),
        },
    )


class UnsupportedMarketError(Exception):
    pass


class UnsupportedSideError(Exception):
    pass


def _parse_market_or_exit(raw: str) -> Market:
    try:
        return _parse_market(raw)
    except UnsupportedMarketError as exc:
        console.print(f"unsupported market: {raw}")
        raise typer.Exit(code=2) from exc


def _parse_market(raw: str) -> Market:
    markets = {"kr": Market.KR, "us": Market.US}
    try:
        return markets[raw.strip().lower()]
    except KeyError as exc:
        raise UnsupportedMarketError from exc


def _parse_side_or_exit(raw: str) -> OrderSide:
    try:
        return _parse_side(raw)
    except UnsupportedSideError as exc:
        console.print(f"unsupported side: {raw}")
        raise typer.Exit(code=2) from exc


def _parse_side(raw: str) -> OrderSide:
    sides = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
    try:
        return sides[raw.strip().lower()]
    except KeyError as exc:
        raise UnsupportedSideError from exc
