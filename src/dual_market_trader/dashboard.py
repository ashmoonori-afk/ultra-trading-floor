from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Final

from dual_market_trader.charting import build_market_minute_charts
from dual_market_trader.dashboard_charts import render_market_charts
from dual_market_trader.dashboard_metrics import render_metrics
from dual_market_trader.dashboard_tables import (
    live_paper_rows,
    live_rows,
    market_rows,
    pipeline_rows,
    run_rows,
)
from dual_market_trader.market_data import YahooFinanceMarketDataProvider
from dual_market_trader.reporting import (
    read_live_execution_log,
    read_live_paper_execution_log,
    read_performance_log,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.charting import MarketDataProvider, MarketMinuteChart
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


@dataclass(frozen=True, slots=True)
class DashboardViewState:
    entries: Sequence[PerformanceLogEntry]
    latest: PerformanceLogEntry | None
    live_entries: Sequence[LiveOrderResult]
    live_paper_entries: Sequence[LivePaperExecutionResult]
    charts: Sequence[MarketMinuteChart]
    refresh_seconds: int


def render_dashboard(
    log_path: Path,
    live_log_path: Path = DEFAULT_LIVE_LOG_PATH,
    live_paper_log_path: Path = DEFAULT_LIVE_PAPER_LOG_PATH,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
    market_data_provider: MarketDataProvider | None = None,
) -> str:
    entries = read_performance_log(log_path)
    live_entries = read_live_execution_log(live_log_path)
    live_paper_entries = read_live_paper_execution_log(live_paper_log_path)
    latest = entries[-1] if entries else None
    charts = build_market_minute_charts(entries, live_paper_entries, market_data_provider)
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
                DashboardViewState(
                    entries=entries,
                    latest=latest,
                    live_entries=live_entries,
                    live_paper_entries=live_paper_entries,
                    charts=charts,
                    refresh_seconds=refresh_seconds,
                ),
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
    market_data_provider = YahooFinanceMarketDataProvider()

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
                market_data_provider,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

    return DashboardHandler


def _dashboard_body(state: DashboardViewState) -> str:
    return "\n".join(
        (
            '  <main class="terminal-screen">',
            "    <header>",
            "      <div>",
            "        <h1>Dual Market Paper Trader</h1>",
            '        <div class="subhead">KR and US live-clock paper trading terminal</div>',
            "      </div>",
            '      <div class="header-actions">',
            '        <div class="mode">PAPER ONLY</div>',
            f'        <div class="refresh">Auto-refresh {state.refresh_seconds}s</div>',
            "      </div>",
            "    </header>",
            render_metrics(
                state.entries,
                state.latest,
                state.live_entries,
                state.live_paper_entries,
                state.charts,
            ),
            render_market_charts(state.charts),
            _section(
                "Latest Market Results",
                ("Market", "Symbol", "Daily return", "Max drawdown", "Trades"),
                market_rows(state.latest),
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
                run_rows(state.entries),
            ),
            _section(
                "Strategy Pipeline",
                ("Recorded", "Stages", "ML Score", "Optimal Strategy", "Validation"),
                pipeline_rows(state.entries),
            ),
            _section(
                "Real-Time Paper Orders",
                ("Recorded", "Market", "Symbol", "Side", "Qty", "Fill", "Notional", "Note"),
                live_paper_rows(state.live_paper_entries),
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
                live_rows(state.live_entries),
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


def _stylesheet() -> str:
    return files("dual_market_trader").joinpath("dashboard.css").read_text(encoding="utf-8")
