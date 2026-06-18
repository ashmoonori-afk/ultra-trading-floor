from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from dual_market_trader.dashboard_tables import format_pct

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.charting import MarketMinuteChart
    from dual_market_trader.live_models import LiveOrderResult, LivePaperExecutionResult
    from dual_market_trader.models import PerformanceLogEntry


def render_metrics(
    entries: Sequence[PerformanceLogEntry],
    latest: PerformanceLogEntry | None,
    live_entries: Sequence[LiveOrderResult],
    live_paper_entries: Sequence[LivePaperExecutionResult],
    charts: Sequence[MarketMinuteChart],
) -> str:
    status = "Met" if latest is not None and latest.target_met else "Open"
    status_tone = "good" if latest is not None and latest.target_met else "watch"
    validation = latest.validation_status.value if latest is not None else "none"
    validation_tone = "good" if validation == "pass" else "watch"
    live_pnl = _live_paper_return(charts)
    return "\n".join(
        (
            '<div class="metrics">',
            _metric("Live paper PnL", format_pct(live_pnl), _return_tone(live_pnl)),
            _metric("Sample validation", format_pct(_latest_return(latest)), "good"),
            _metric("Target status", status, status_tone),
            _metric("Validation", validation, validation_tone),
            _metric("Logged runs", str(len(entries)), "blue"),
            _metric("Live paper fills", str(len(live_paper_entries)), "blue"),
            _metric("Live orders", str(len(live_entries)), "blue"),
            _metric("Last run", _short_recorded_at(latest), "neutral"),
            "</div>",
        ),
    )


def _metric(label: str, value: str, tone: str) -> str:
    return "".join(
        (
            f'<div class="metric {escape(tone)}">',
            f'<div class="label">{escape(label)}</div>',
            f'<div class="value">{escape(value)}</div>',
            "</div>",
        ),
    )


def _latest_return(entry: PerformanceLogEntry | None) -> float | None:
    return entry.aggregate_daily_return_pct if entry is not None else None


def _live_paper_return(charts: Sequence[MarketMinuteChart]) -> float | None:
    exposure = sum(chart.live_exposure for chart in charts)
    if exposure <= 0:
        return None
    pnl = sum(chart.live_pnl for chart in charts)
    return pnl / exposure * 100


def _return_tone(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value >= 0:
        return "good"
    return "watch"


def _short_recorded_at(entry: PerformanceLogEntry | None) -> str:
    if entry is None:
        return "No runs"
    return entry.recorded_at[:16].replace("T", " ")
