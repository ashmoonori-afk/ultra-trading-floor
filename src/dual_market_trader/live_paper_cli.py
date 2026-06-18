from dataclasses import dataclass
from pathlib import Path
from typing import Final

import typer
from rich.console import Console

from dual_market_trader.execution import (
    LivePaperExecutionConfig,
    LivePaperPriceUnavailableError,
    run_live_paper_execution_loop,
)
from dual_market_trader.live_models import LiveOrderIntent, OrderSide, OrderType
from dual_market_trader.live_prices import YahooLivePaperPriceProvider
from dual_market_trader.market_data import YahooFinanceMarketDataProvider
from dual_market_trader.models import Market

DEFAULT_LIVE_PAPER_EXECUTION_LOG: Final = Path(".data/live-paper-executions.jsonl")


@dataclass(frozen=True, slots=True)
class LivePaperCommand:
    market: Market
    symbol: str
    side: OrderSide
    quantity: float
    price: float | None
    max_cycles: int
    interval_seconds: float
    evidence_dir: Path | None


def execute_live_paper_command(
    console: Console,
    command: LivePaperCommand,
) -> None:
    market_data_provider = YahooFinanceMarketDataProvider()
    price_provider = YahooLivePaperPriceProvider(market_data_provider=market_data_provider)
    intent = LiveOrderIntent(
        market=command.market,
        symbol=command.symbol,
        side=command.side,
        quantity=command.quantity,
        price=_intent_price_or_exit(
            console,
            market_data_provider,
            command.market,
            command.symbol,
            command.price,
        ),
        order_type=OrderType.LIMIT,
    )
    live_paper_log_path = (
        command.evidence_dir / "live-paper-executions.jsonl"
        if command.evidence_dir is not None
        else DEFAULT_LIVE_PAPER_EXECUTION_LOG
    )
    try:
        results = run_live_paper_execution_loop(
            LivePaperExecutionConfig(
                intent=intent,
                log_path=live_paper_log_path,
                max_cycles=command.max_cycles,
                interval_seconds=command.interval_seconds,
            ),
            price_provider=price_provider,
        )
    except LivePaperPriceUnavailableError as exc:
        console.print(str(exc))
        raise typer.Exit(code=2) from exc
    latest = results[-1]
    console.print(
        {
            "mode": "live_paper",
            "paper_fills": len(results),
            "latest_symbol": latest.intent.symbol,
            "requested_price": latest.intent.price,
            "latest_fill_price": latest.fill_price,
            "latest_notional": latest.notional,
            "live_paper_execution_log": str(live_paper_log_path),
        },
    )


def _intent_price_or_exit(
    console: Console,
    market_data_provider: YahooFinanceMarketDataProvider,
    market: Market,
    symbol: str,
    price: float | None,
) -> float:
    if price is not None:
        return price
    latest_price = market_data_provider.latest_price(market, symbol)
    if latest_price is None:
        console.print(f"live paper market price unavailable for {market.value.upper()} {symbol}")
        raise typer.Exit(code=2)
    return latest_price
