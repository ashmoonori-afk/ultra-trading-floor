from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Final

from dual_market_trader.dashboard_tables import (
    format_pct,
    live_paper_rows,
    live_rows,
    market_rows,
    pipeline_rows,
    run_rows,
)
from dual_market_trader.reporting import (
    read_live_execution_log,
    read_live_paper_execution_log,
    read_performance_log,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.live_models import LiveOrderResult, LivePaperExecutionResult
    from dual_market_trader.models import PerformanceLogEntry

DEFAULT_LIVE_LOG_PATH = Path(".data/live-executions.jsonl")
DEFAULT_LIVE_PAPER_LOG_PATH = Path(".data/live-paper-executions.jsonl")
DEFAULT_REFRESH_SECONDS: Final = 5


@dataclass(frozen=True, slots=True)
class DashboardServerConfig:
    host: str
    port: int
    log_path: Path
    live_log_path: Path
    live_paper_log_path: Path
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS


def render_dashboard(
    log_path: Path,
    live_log_path: Path = DEFAULT_LIVE_LOG_PATH,
    live_paper_log_path: Path = DEFAULT_LIVE_PAPER_LOG_PATH,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
) -> str:
    entries = read_performance_log(log_path)
    live_entries = read_live_execution_log(live_log_path)
    live_paper_entries = read_live_paper_execution_log(live_paper_log_path)
    latest = entries[-1] if entries else None
    return "\n".join(
        (
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f'  <meta http-equiv="refresh" content="{refresh_seconds}">',
            "  <title>Dual Market Paper Trader</title>",
            f"  <style>{_stylesheet()}</style>",
            "</head>",
            "<body>",
            _dashboard_body(
                entries,
                latest,
                live_entries,
                live_paper_entries,
                refresh_seconds,
            ),
            "</body>",
            "</html>",
        ),
    )


def serve_dashboard(config: DashboardServerConfig) -> None:
    server = ThreadingHTTPServer(
        (config.host, config.port),
        _handler_for(
            config.log_path,
            config.live_log_path,
            config.live_paper_log_path,
            config.refresh_seconds,
        ),
    )
    server.serve_forever()


def _handler_for(
    log_path: Path,
    live_log_path: Path,
    live_paper_log_path: Path,
    refresh_seconds: int,
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(HTTPStatus.NOT_FOUND.value)
                return
            payload = render_dashboard(
                log_path,
                live_log_path,
                live_paper_log_path,
                refresh_seconds,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

    return DashboardHandler


def _dashboard_body(
    entries: Sequence[PerformanceLogEntry],
    latest: PerformanceLogEntry | None,
    live_entries: Sequence[LiveOrderResult],
    live_paper_entries: Sequence[LivePaperExecutionResult],
    refresh_seconds: int,
) -> str:
    return "\n".join(
        (
            "  <main>",
            "    <header>",
            "      <div>",
            "        <h1>Dual Market Paper Trader</h1>",
            '        <div class="subhead">KR and US live-clock paper trading dashboard</div>',
            "      </div>",
            '      <div class="header-actions">',
            '        <div class="mode">PAPER ONLY</div>',
            f'        <div class="refresh">Auto-refresh {refresh_seconds}s</div>',
            "      </div>",
            "    </header>",
            _metrics(entries, latest, live_entries, live_paper_entries),
            _section(
                "Latest Market Results",
                ("Market", "Symbol", "Daily return", "Max drawdown", "Trades"),
                market_rows(latest),
            ),
            _section(
                "Paper Trading Performance",
                (
                    "Recorded",
                    "Target",
                    "Status",
                    "Validation",
                    "Return",
                    "Strategy",
                    "Fallback",
                    "Failed Criteria",
                    "Iterations",
                    "Markets",
                ),
                run_rows(entries),
            ),
            _section(
                "Strategy Pipeline",
                ("Recorded", "Stages", "ML Score", "Optimal Strategy", "Validation"),
                pipeline_rows(entries),
            ),
            _section(
                "Real-Time Paper Orders",
                ("Recorded", "Market", "Symbol", "Side", "Qty", "Fill", "Notional", "Note"),
                live_paper_rows(live_paper_entries),
            ),
            _section(
                "Live Execution Log",
                (
                    "Recorded",
                    "Broker",
                    "Market",
                    "Symbol",
                    "Side",
                    "Qty",
                    "Price",
                    "Order",
                    "Status",
                ),
                live_rows(live_entries),
            ),
            "  </main>",
        ),
    )


def _section(title: str, headers: tuple[str, ...], rows: str) -> str:
    return "\n".join(
        (
            "    <section>",
            f"      <h2>{escape(title)}</h2>",
            '      <div class="table-wrap">',
            "        <table>",
            "          <thead>",
            f"            <tr>{_header_cells(headers)}</tr>",
            "          </thead>",
            "          <tbody>",
            f"            {rows}",
            "          </tbody>",
            "        </table>",
            "      </div>",
            "    </section>",
        ),
    )


def _header_cells(headers: tuple[str, ...]) -> str:
    return "".join(f"<th>{escape(header)}</th>" for header in headers)


def _metrics(
    entries: Sequence[PerformanceLogEntry],
    latest: PerformanceLogEntry | None,
    live_entries: Sequence[LiveOrderResult],
    live_paper_entries: Sequence[LivePaperExecutionResult],
) -> str:
    status = "Met" if latest is not None and latest.target_met else "Open"
    status_tone = "good" if latest is not None and latest.target_met else "watch"
    validation = latest.validation_status.value if latest is not None else "none"
    validation_tone = "good" if validation == "pass" else "watch"
    return "\n".join(
        (
            '<div class="metrics">',
            _metric("Latest return", format_pct(_latest_return(latest)), "good"),
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


def _stylesheet() -> str:
    return files("dual_market_trader").joinpath("dashboard.css").read_text(encoding="utf-8")


def _latest_return(entry: PerformanceLogEntry | None) -> float | None:
    return entry.aggregate_daily_return_pct if entry is not None else None


def _short_recorded_at(entry: PerformanceLogEntry | None) -> str:
    if entry is None:
        return "No runs"
    return entry.recorded_at[:16].replace("T", " ")
