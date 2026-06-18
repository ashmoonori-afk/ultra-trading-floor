from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console

from dual_market_trader.live_cli import UnsupportedMarketError, parse_market
from dual_market_trader.live_paper_cli import DEFAULT_LIVE_PAPER_EXECUTION_LOG
from dual_market_trader.market_data import YahooFinanceMarketDataProvider
from dual_market_trader.models import Market
from dual_market_trader.screener import (
    DEFAULT_SCREENER_DECISION_LOG,
    ScreenerPaperConfig,
    ScreenerRequest,
    SymbolCandidateSpec,
    run_screener_paper_loop,
)

DEFAULT_KR_SYMBOLS: Final = ("005930", "000660", "035420", "051910", "068270", "005380")
DEFAULT_US_SYMBOLS: Final = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META")
DEFAULT_SCREENER_LOOKBACK: Final = 20


def register_screener_commands(app: typer.Typer, console: Console) -> None:
    @app.command("scan-trade-paper")
    def scan_trade_paper(
        markets: Annotated[str, typer.Option("--markets")] = "KR,US",
        kr_symbols: Annotated[str | None, typer.Option("--kr-symbols")] = None,
        us_symbols: Annotated[str | None, typer.Option("--us-symbols")] = None,
        max_positions: Annotated[int, typer.Option("--max-positions", min=1, max=25)] = 4,
        per_position_notional: Annotated[
            float,
            typer.Option("--per-position-notional", min=0.000001),
        ] = 1_000_000,
        min_score: Annotated[float, typer.Option("--min-score", min=-100, max=100)] = 0,
        lookback: Annotated[int, typer.Option("--lookback", min=1, max=120)] = (
            DEFAULT_SCREENER_LOOKBACK
        ),
        max_cycles: Annotated[int, typer.Option("--max-cycles", min=1, max=10_000)] = 1,
        interval_seconds: Annotated[float, typer.Option("--interval-seconds", min=0)] = 30,
        evidence_dir: Annotated[
            Path | None,
            typer.Option("--evidence-dir", file_okay=False),
        ] = None,
    ) -> None:
        selected_markets = _parse_markets_or_exit(console, markets)
        symbol_specs = _symbol_specs(selected_markets, kr_symbols, us_symbols)
        decision_log_path = (
            evidence_dir / "screener-decisions.jsonl"
            if evidence_dir is not None
            else DEFAULT_SCREENER_DECISION_LOG
        )
        live_paper_log_path = (
            evidence_dir / "live-paper-executions.jsonl"
            if evidence_dir is not None
            else DEFAULT_LIVE_PAPER_EXECUTION_LOG
        )
        results = run_screener_paper_loop(
            ScreenerPaperConfig(
                request=ScreenerRequest(
                    symbols=symbol_specs,
                    max_positions=max_positions,
                    min_score=min_score,
                    lookback=lookback,
                ),
                per_position_notional=per_position_notional,
                decision_log_path=decision_log_path,
                live_paper_log_path=live_paper_log_path,
                max_cycles=max_cycles,
                interval_seconds=interval_seconds,
            ),
            YahooFinanceMarketDataProvider(),
        )
        latest = results[-1]
        total_fills = sum(len(result.fills) for result in results)
        console.print(
            {
                "mode": "screener_paper",
                "cycles": len(results),
                "candidates": len(latest.decision.candidates),
                "selected": tuple(item.symbol for item in latest.decision.selected_candidates),
                "fills": total_fills,
                "latest_cycle_fills": len(latest.fills),
                "decision_log": str(decision_log_path),
                "live_paper_execution_log": str(live_paper_log_path),
            },
        )

    _ = scan_trade_paper


def _parse_markets_or_exit(console: Console, raw: str) -> tuple[Market, ...]:
    parsed: list[Market] = []
    for item in raw.split(","):
        try:
            parsed.append(parse_market(item))
        except UnsupportedMarketError as exc:
            console.print(f"unsupported market: {item}")
            raise typer.Exit(code=2) from exc
    return tuple(parsed)


def _symbol_specs(
    markets: tuple[Market, ...],
    kr_symbols: str | None,
    us_symbols: str | None,
) -> tuple[SymbolCandidateSpec, ...]:
    specs: list[SymbolCandidateSpec] = []
    for market in markets:
        specs.extend(
            SymbolCandidateSpec(market=market, symbol=symbol)
            for symbol in _symbols_for_market(market, kr_symbols, us_symbols)
        )
    return tuple(specs)


def _symbols_for_market(
    market: Market,
    kr_symbols: str | None,
    us_symbols: str | None,
) -> tuple[str, ...]:
    raw_symbols = {
        Market.KR: kr_symbols,
        Market.US: us_symbols,
    }
    default_symbols = {
        Market.KR: DEFAULT_KR_SYMBOLS,
        Market.US: DEFAULT_US_SYMBOLS,
    }
    return _split_symbols(raw_symbols[market], default_symbols[market])


def _split_symbols(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    parsed = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not parsed:
        return default
    return parsed
