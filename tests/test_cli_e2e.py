from pathlib import Path

import pytest
from typer.testing import CliRunner

from dual_market_trader import live_paper_cli
from dual_market_trader.cli import app
from dual_market_trader.models import Market


class _FakeMarketDataProvider:
    def latest_price(self, market: Market, symbol: str) -> float | None:
        _ = (market, symbol)
        return 354500


def test_run_once_cli_surface_accepts_target_options(tmp_path: Path) -> None:
    runner = CliRunner()
    performance_log = Path(".data/performance-log.jsonl")

    result = runner.invoke(
        app,
        [
            "run-once",
            "--markets",
            "KR,US",
            "--target-daily-return-pct",
            "5.0",
            "--sample",
            "deterministic",
            "--evidence-dir",
            str(tmp_path),
        ],
    )

    report_path = tmp_path / "run-once-report.json"
    assert result.exit_code == 0
    assert "target_met" in result.stdout
    assert "validation_status" in result.stdout
    assert "fallback_used" in result.stdout
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert '"live_order_enabled": false' in report_text
    assert '"guaranteed": false' in report_text
    assert '"validation_status": "pass"' in report_text
    assert '"market": "kr"' in report_text
    assert '"market": "us"' in report_text
    assert performance_log.exists()
    last_log_line = performance_log.read_text(encoding="utf-8").splitlines()[-1]
    assert '"target_met":true' in last_log_line
    assert '"validation_status":"pass"' in last_log_line
    assert '"aggregate_daily_return_pct"' in last_log_line


def test_run_once_cli_surface_reports_fallback_when_target_is_not_validated(
    tmp_path: Path,
) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-once",
            "--markets",
            "KR,US",
            "--target-daily-return-pct",
            "20.0",
            "--sample",
            "deterministic",
            "--evidence-dir",
            str(tmp_path),
        ],
    )

    report_path = tmp_path / "run-once-report.json"
    assert result.exit_code == 0
    assert "'target_met': False" in result.stdout
    assert "'validation_status': 'fallback'" in result.stdout
    assert "'fallback_used': True" in result.stdout
    assert "'best_available_strategy': 'buy_hold'" in result.stdout
    report_text = report_path.read_text(encoding="utf-8")
    assert '"validation_status": "fallback"' in report_text
    assert '"selected_as_fallback": true' in report_text


def test_run_paper_loop_cli_surface_appends_performance_log(tmp_path: Path) -> None:
    runner = CliRunner()
    performance_log = tmp_path / "performance-log.jsonl"

    result = runner.invoke(
        app,
        [
            "run-paper-loop",
            "--markets",
            "KR,US",
            "--target-daily-return-pct",
            "5.0",
            "--sample",
            "deterministic",
            "--max-cycles",
            "2",
            "--interval-seconds",
            "0",
            "--evidence-dir",
            str(tmp_path),
            "--performance-log",
            str(performance_log),
        ],
    )

    assert result.exit_code == 0
    assert "paper_loop" in result.stdout
    assert "performance_log" in result.stdout
    assert performance_log.exists()
    assert len(performance_log.read_text(encoding="utf-8").splitlines()) == 2


def test_trade_live_cli_surface_refuses_without_credentials(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "trade-live",
            "--market",
            "KR",
            "--symbol",
            "005930.KS",
            "--side",
            "buy",
            "--quantity",
            "1",
            "--evidence-dir",
            str(tmp_path),
        ],
        env={
            "DMT_LIVE_TRADING_ENABLED": "",
            "DMT_BROKER_API_KEY": "",
            "DMT_BROKER_API_SECRET": "",
        },
    )

    assert result.exit_code == 2
    assert "live trading is disabled" in result.stdout
    assert not any(tmp_path.iterdir())


def test_run_live_cli_surface_refuses_without_credentials(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-live",
            "--market",
            "KR",
            "--symbol",
            "005930",
            "--side",
            "buy",
            "--quantity",
            "1",
            "--price",
            "71000",
            "--max-cycles",
            "1",
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

    assert result.exit_code == 2
    assert "live trading is disabled" in result.stdout
    assert not any(tmp_path.iterdir())


def test_run_live_paper_cli_surface_logs_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(live_paper_cli, "YahooFinanceMarketDataProvider", _FakeMarketDataProvider)

    result = runner.invoke(
        app,
        [
            "run-live-paper",
            "--market",
            "KR",
            "--symbol",
            "005930",
            "--side",
            "buy",
            "--quantity",
            "1",
            "--price",
            "71000",
            "--max-cycles",
            "2",
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

    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    assert result.exit_code == 0
    assert "live_paper" in result.stdout
    assert "'latest_fill_price': 354500.0" in result.stdout
    assert live_paper_log.exists()
    entries = live_paper_log.read_text(encoding="utf-8").splitlines()
    assert len(entries) == 2
    assert '"price":71000.0' in entries[-1]
    assert '"fill_price":354500.0' in entries[-1]
    assert '"notional":354500.0' in entries[-1]


def test_dashboard_cli_surface_exposes_log_option() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["dashboard", "--help"])

    assert result.exit_code == 0
    assert "--log" in result.stdout
    assert "--live-log" in result.stdout
    assert "--live-paper-log" in result.stdout
    assert "--refresh-seconds" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout
