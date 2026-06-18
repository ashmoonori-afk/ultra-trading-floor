from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dual_market_trader import screener_cli
from dual_market_trader.charting import ChartSpec, MarketDataSource, MarketMinuteSeries
from dual_market_trader.cli import app
from dual_market_trader.models import Candle, Market


@dataclass(frozen=True, slots=True)
class _FakeScreenerMarketDataProvider:
    def load_minute_candles(self, specs: tuple[ChartSpec, ...]) -> tuple[MarketMinuteSeries, ...]:
        requested = {(spec.market, spec.symbol.upper().removesuffix(".KS")) for spec in specs}
        series = (
            _series(Market.KR, "005930.KS", (100, 101, 102, 103), (10, 10, 12, 14)),
            _series(Market.KR, "000660.KS", (100, 105, 108, 112), (10, 13, 18, 25)),
            _series(Market.US, "AAPL", (200, 201, 203, 207), (20, 21, 22, 25)),
        )
        return tuple(
            item
            for item in series
            if (item.market, item.symbol.upper().removesuffix(".KS")) in requested
        )


def test_scan_trade_paper_cli_surface_selects_and_logs_multiple_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        screener_cli,
        "YahooFinanceMarketDataProvider",
        _FakeScreenerMarketDataProvider,
    )

    result = runner.invoke(
        app,
        [
            "scan-trade-paper",
            "--markets",
            "KR,US",
            "--kr-symbols",
            "005930,000660",
            "--us-symbols",
            "AAPL",
            "--max-positions",
            "2",
            "--per-position-notional",
            "1000",
            "--lookback",
            "3",
            "--max-cycles",
            "1",
            "--interval-seconds",
            "0",
            "--evidence-dir",
            str(tmp_path),
        ],
        env={
            "DMT_LIVE_TRADING_ENABLED": "",
            "DMT_BROKER_API_KEY": "",
            "DMT_BROKER_API_SECRET": "",
            "TOSS_ALLOW_LIVE_ORDERS": "",
        },
    )

    decision_log = tmp_path / "screener-decisions.jsonl"
    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    assert result.exit_code == 0
    assert "screener_paper" in result.stdout
    assert "000660.KS" in result.stdout
    assert "AAPL" in result.stdout
    assert decision_log.exists()
    assert live_paper_log.exists()
    assert len(live_paper_log.read_text(encoding="utf-8").splitlines()) == 2


def _series(
    market: Market,
    symbol: str,
    closes: tuple[float, ...],
    volumes: tuple[float, ...],
) -> MarketMinuteSeries:
    return MarketMinuteSeries(
        market=market,
        symbol=symbol,
        candles=tuple(
            Candle(
                timestamp=1_800_000_000 + index * 60,
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                volume=volumes[index],
            )
            for index, close in enumerate(closes)
        ),
        source=MarketDataSource.YAHOO,
        fetched_at="2026-06-18T00:00:00+00:00",
    )
