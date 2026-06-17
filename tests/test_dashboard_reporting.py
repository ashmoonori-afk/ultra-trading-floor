from pathlib import Path

from dual_market_trader.config import load_run_config
from dual_market_trader.dashboard import render_dashboard
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.live_models import (
    BrokerName,
    LiveOrderIntent,
    LiveOrderResult,
    LiveOrderStatus,
    LivePaperExecutionResult,
    OrderSide,
    OrderType,
)
from dual_market_trader.models import Market
from dual_market_trader.reporting import (
    append_live_execution_log,
    append_live_paper_execution_log,
    append_performance_log,
    read_live_paper_execution_log,
    read_performance_log,
)


def test_performance_log_is_append_only_jsonl(tmp_path: Path) -> None:
    report = run_improvement_loop(load_run_config(Path("examples/paper_target_5.json")))
    log_path = tmp_path / "performance-log.jsonl"

    first = append_performance_log(report, log_path)
    second = append_performance_log(report, log_path)

    entries = read_performance_log(log_path)
    assert entries == (first, second)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2
    assert entries[-1].target_met is True
    assert entries[-1].aggregate_daily_return_pct is not None
    assert {market.market.value for market in entries[-1].markets} == {"kr", "us"}


def test_dashboard_renders_persistent_performance_log(tmp_path: Path) -> None:
    report = run_improvement_loop(load_run_config(Path("examples/paper_target_5.json")))
    log_path = tmp_path / "performance-log.jsonl"
    _ = append_performance_log(report, log_path)

    html = render_dashboard(log_path)

    assert "Dual Market Paper Trader" in html
    assert "Persistent Performance Log" in html
    assert "PAPER ONLY" in html
    assert "KR" in html
    assert "US" in html
    assert "7.82%" in html


def test_dashboard_renders_live_execution_log(tmp_path: Path) -> None:
    performance_log = tmp_path / "performance-log.jsonl"
    live_log = tmp_path / "live-executions.jsonl"
    _ = append_live_execution_log(
        LiveOrderResult(
            recorded_at="2026-06-17T00:00:00+00:00",
            broker=BrokerName.TOSS,
            status=LiveOrderStatus.PLACED,
            intent=LiveOrderIntent(
                market=Market.KR,
                symbol="005930",
                side=OrderSide.BUY,
                quantity=1,
                price=71000,
                order_type=OrderType.LIMIT,
            ),
            order_id="order-123",
            confirmation_token_present=True,
            broker_message="placed",
        ),
        live_log,
    )

    html = render_dashboard(performance_log, live_log)

    assert "Live Execution Log" in html
    assert "order-123" in html
    assert "005930" in html
    assert "TOSS" in html


def test_live_paper_log_is_append_only_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "live-paper-executions.jsonl"
    result = LivePaperExecutionResult(
        recorded_at="2026-06-17T00:00:00+00:00",
        intent=LiveOrderIntent(
            market=Market.US,
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=2,
            price=210.5,
            order_type=OrderType.LIMIT,
        ),
        fill_price=210.5,
        notional=421.0,
        note="paper fill only",
    )

    first = append_live_paper_execution_log(result, log_path)
    second = append_live_paper_execution_log(result, log_path)

    entries = read_live_paper_execution_log(log_path)
    assert entries == (first, second)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_dashboard_renders_live_paper_validation_log(tmp_path: Path) -> None:
    performance_log = tmp_path / "performance-log.jsonl"
    live_log = tmp_path / "live-executions.jsonl"
    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    _ = append_live_paper_execution_log(
        LivePaperExecutionResult(
            recorded_at="2026-06-17T00:00:00+00:00",
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

    html = render_dashboard(performance_log, live_log, live_paper_log)

    assert "Live Paper Validation Log" in html
    assert "paper fill only" in html
    assert "005930" in html


def test_dashboard_renders_empty_state(tmp_path: Path) -> None:
    html = render_dashboard(
        tmp_path / "missing-performance.jsonl",
        tmp_path / "missing-live.jsonl",
        tmp_path / "missing-live-paper.jsonl",
    )

    assert "No performance runs logged yet." in html
    assert "No market results logged yet." in html
    assert "No live executions logged yet." in html
    assert "No live paper validations logged yet." in html
