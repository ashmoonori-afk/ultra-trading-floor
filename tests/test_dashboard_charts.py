from collections.abc import Sequence
from pathlib import Path

from dual_market_trader.charting import ChartSpec, MarketDataSource, MarketMinuteSeries
from dual_market_trader.config import load_run_config
from dual_market_trader.dashboard import render_dashboard
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.live_models import (
    LiveOrderIntent,
    LivePaperExecutionResult,
    OrderSide,
    OrderType,
)
from dual_market_trader.models import Candle, Market
from dual_market_trader.reporting import (
    append_live_paper_execution_log,
    append_performance_log,
)


class FakeMarketDataProvider:
    def load_minute_candles(
        self,
        specs: Sequence[ChartSpec],
    ) -> tuple[MarketMinuteSeries, ...]:
        _ = specs
        return (
            MarketMinuteSeries(
                market=Market.KR,
                symbol="005930.KS",
                candles=(
                    Candle(
                        timestamp=1_787_000_000,
                        open=71000,
                        high=72100,
                        low=70900,
                        close=71100,
                        volume=1000,
                    ),
                    Candle(
                        timestamp=1_787_000_060,
                        open=71100,
                        high=72200,
                        low=71000,
                        close=72000,
                        volume=1100,
                    ),
                ),
                source=MarketDataSource.YAHOO,
                fetched_at="2026-06-18T03:00:00+00:00",
            ),
        )


def test_dashboard_renders_market_minute_charts_with_paper_trade_markers(
    tmp_path: Path,
) -> None:
    report = run_improvement_loop(load_run_config(Path("examples/paper_target_5.json")))
    performance_log = tmp_path / "performance-log.jsonl"
    live_log = tmp_path / "live-executions.jsonl"
    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    _ = append_performance_log(report, performance_log)
    _ = append_live_paper_execution_log(
        LivePaperExecutionResult(
            recorded_at="2026-06-18T01:50:00+00:00",
            intent=LiveOrderIntent(
                market=Market.KR,
                symbol="005930",
                side=OrderSide.BUY,
                quantity=1,
                price=71000,
                order_type=OrderType.LIMIT,
            ),
            fill_price=71000,
            notional=71000,
            note="paper fill only",
        ),
        live_paper_log,
    )

    html = render_dashboard(
        performance_log,
        live_log,
        live_paper_log,
        market_data_provider=FakeMarketDataProvider(),
    )

    assert "Market Minute Charts" in html
    assert 'data-chart-market="kr"' in html
    assert "005930" in html
    assert "YAHOO REAL 1M" in html
    assert "Live paper PnL" in html
    assert "1.41%" in html
    assert 'data-marker-kind="entry"' in html
    assert 'data-marker-kind="target"' in html
    assert 'data-marker-kind="stop"' in html
    assert "Entry" in html
    assert "Target Exit" in html
    assert "Stop Loss" in html


def test_dashboard_uses_terminal_theme_tokens(tmp_path: Path) -> None:
    html = render_dashboard(
        tmp_path / "missing-performance.jsonl",
        tmp_path / "missing-live.jsonl",
        tmp_path / "missing-live-paper.jsonl",
    )

    assert 'class="terminal-screen"' in html
    assert "color-scheme: dark" in html
    assert "--terminal-orange" in html
