import os
from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console

from dual_market_trader.execution import (
    LiveExecutionConfig,
    run_live_execution_loop,
)
from dual_market_trader.live import LiveTradingDisabledError, require_live_trading_enabled
from dual_market_trader.live_models import LiveOrderIntent, OrderSide, OrderType
from dual_market_trader.live_paper_cli import (
    LivePaperCommand,
    execute_live_paper_command,
)
from dual_market_trader.models import Market
from dual_market_trader.toss import TossBrokerError, TossCtlBroker, TossCtlConfig

DEFAULT_LIVE_EXECUTION_LOG: Final = Path(".data/live-executions.jsonl")


def register_live_commands(app: typer.Typer, console: Console) -> None:
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
            console=console,
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
            console=console,
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

    @app.command("run-live-paper")
    def run_live_paper(
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
    ) -> None:
        market_value = _parse_market_or_exit(console, market)
        side_value = _parse_side_or_exit(console, side)
        command = LivePaperCommand(
            market=market_value,
            symbol=symbol,
            side=side_value,
            quantity=quantity,
            price=price,
            max_cycles=max_cycles,
            interval_seconds=interval_seconds,
            evidence_dir=evidence_dir,
        )
        execute_live_paper_command(console, command)

    _ = (trade_live, run_live, run_live_paper)


def _execute_live_order_command(
    *,
    console: Console,
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
        market=_parse_market_or_exit(console, market),
        symbol=symbol,
        side=_parse_side_or_exit(console, side),
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


def _parse_market_or_exit(console: Console, raw: str) -> Market:
    try:
        return parse_market(raw)
    except UnsupportedMarketError as exc:
        console.print(f"unsupported market: {raw}")
        raise typer.Exit(code=2) from exc


def parse_market(raw: str) -> Market:
    markets = {"kr": Market.KR, "us": Market.US}
    try:
        return markets[raw.strip().lower()]
    except KeyError as exc:
        raise UnsupportedMarketError from exc


def _parse_side_or_exit(console: Console, raw: str) -> OrderSide:
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
