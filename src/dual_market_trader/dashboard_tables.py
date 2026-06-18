from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.live_models import LiveOrderResult, LivePaperExecutionResult
    from dual_market_trader.models import MarketPerformanceEntry, PerformanceLogEntry
    from dual_market_trader.screener import ScreenedSymbol, ScreenerDecision


def market_rows(latest: PerformanceLogEntry | None) -> str:
    if latest is None or not latest.markets:
        return '<tr><td colspan="5" class="empty">No market results logged yet.</td></tr>'
    return "\n".join(_market_row(market) for market in latest.markets)


def run_rows(entries: Sequence[PerformanceLogEntry]) -> str:
    if not entries:
        return '<tr><td colspan="10" class="empty">No performance runs logged yet.</td></tr>'
    return "\n".join(_run_row(entry) for entry in reversed(entries[-25:]))


def pipeline_rows(entries: Sequence[PerformanceLogEntry]) -> str:
    if not entries:
        return '<tr><td colspan="5" class="empty">No strategy pipeline runs logged yet.</td></tr>'
    return "\n".join(_pipeline_row(entry) for entry in reversed(entries[-25:]))


def live_paper_rows(entries: Sequence[LivePaperExecutionResult]) -> str:
    if not entries:
        return '<tr><td colspan="8" class="empty">No live paper validations logged yet.</td></tr>'
    return "\n".join(_live_paper_row(entry) for entry in reversed(entries[-25:]))


def live_rows(entries: Sequence[LiveOrderResult]) -> str:
    if not entries:
        return '<tr><td colspan="9" class="empty">No live executions logged yet.</td></tr>'
    return "\n".join(_live_row(entry) for entry in reversed(entries[-25:]))


def screener_rows(entries: Sequence[ScreenerDecision]) -> str:
    if not entries:
        return '<tr><td colspan="10" class="empty">No screener decisions logged yet.</td></tr>'
    return "\n".join(
        _screener_row(entry.recorded_at, candidate)
        for entry in reversed(entries[-10:])
        for candidate in entry.candidates[:10]
    )


def _market_row(market: MarketPerformanceEntry) -> str:
    return "".join(
        (
            "<tr>",
            f"<td>{escape(market.market.value.upper())}</td>",
            f"<td>{escape(market.symbol)}</td>",
            f"<td>{escape(format_pct(market.daily_return_pct))}</td>",
            f"<td>{escape(format_pct(market.max_drawdown_pct))}</td>",
            f"<td>{market.trade_count}</td>",
            "</tr>",
        ),
    )


def _run_row(entry: PerformanceLogEntry) -> str:
    status = "met" if entry.target_met else "open"
    markets = ", ".join(market.market.value.upper() for market in entry.markets)
    strategy = entry.selected_strategy.value if entry.selected_strategy is not None else "none"
    fallback = entry.fallback_strategy.value if entry.fallback_strategy is not None else "none"
    failed = ", ".join(entry.failed_criteria) if entry.failed_criteria else "none"
    return "".join(
        (
            "<tr>",
            f"<td>{escape(entry.recorded_at)}</td>",
            f"<td>{escape(format_pct(entry.target_daily_return_pct))}</td>",
            f'<td><span class="status {status}">{status}</span></td>',
            f"<td>{escape(entry.validation_status.value)}</td>",
            f"<td>{escape(format_pct(entry.aggregate_daily_return_pct))}</td>",
            f"<td>{escape(strategy)}</td>",
            f"<td>{escape(fallback)}</td>",
            f"<td>{escape(failed)}</td>",
            f"<td>{entry.iterations_run}</td>",
            f"<td>{escape(markets)}</td>",
            "</tr>",
        ),
    )


def _pipeline_row(entry: PerformanceLogEntry) -> str:
    strategy = entry.optimal_strategy.value if entry.optimal_strategy is not None else "none"
    score = format_number(entry.pipeline_score) if entry.pipeline_score is not None else "n/a"
    return "".join(
        (
            "<tr>",
            f"<td>{escape(entry.recorded_at)}</td>",
            "<td>validation -> modification -> evolution -> ml_scoring -> optimal_selection</td>",
            f"<td>{escape(score)}</td>",
            f"<td>{escape(strategy)}</td>",
            f"<td>{escape(entry.validation_status.value)}</td>",
            "</tr>",
        ),
    )


def _live_paper_row(entry: LivePaperExecutionResult) -> str:
    intent = entry.intent
    return "".join(
        (
            "<tr>",
            f"<td>{escape(entry.recorded_at)}</td>",
            f"<td>{escape(intent.market.value.upper())}</td>",
            f"<td>{escape(intent.symbol)}</td>",
            f"<td>{escape(intent.side.value)}</td>",
            f"<td>{escape(format_number(intent.quantity))}</td>",
            f"<td>{escape(format_number(entry.fill_price))}</td>",
            f"<td>{escape(format_number(entry.notional))}</td>",
            f"<td>{escape(entry.note)}</td>",
            "</tr>",
        ),
    )


def _live_row(entry: LiveOrderResult) -> str:
    order_id = entry.order_id if entry.order_id is not None else "n/a"
    intent = entry.intent
    return "".join(
        (
            "<tr>",
            f"<td>{escape(entry.recorded_at)}</td>",
            f"<td>{escape(entry.broker.value.upper())}</td>",
            f"<td>{escape(intent.market.value.upper())}</td>",
            f"<td>{escape(intent.symbol)}</td>",
            f"<td>{escape(intent.side.value)}</td>",
            f"<td>{escape(format_number(intent.quantity))}</td>",
            f"<td>{escape(format_number(intent.price))}</td>",
            f"<td>{escape(order_id)}</td>",
            f'<td><span class="status met">{escape(entry.status.value)}</span></td>',
            "</tr>",
        ),
    )


def _screener_row(recorded_at: str, candidate: ScreenedSymbol) -> str:
    status = "selected" if candidate.selected else "watch"
    return "".join(
        (
            "<tr>",
            f"<td>{escape(recorded_at)}</td>",
            f"<td>{escape(candidate.market.value.upper())}</td>",
            f"<td>{escape(candidate.symbol)}</td>",
            f"<td>{escape(format_number(candidate.score))}</td>",
            f"<td>{escape(format_number(candidate.latest_price))}</td>",
            f"<td>{escape(format_pct(candidate.momentum_pct))}</td>",
            f"<td>{escape(format_pct(candidate.breakout_pct))}</td>",
            f"<td>{escape(format_number(candidate.volume_ratio))}</td>",
            f'<td><span class="status {status}">{status}</span></td>',
            f"<td>{escape(candidate.reason)}</td>",
            "</tr>",
        ),
    )


def format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"
