from pathlib import Path

from dual_market_trader.config import load_run_config
from dual_market_trader.improvement import run_improvement_loop
from dual_market_trader.models import Market


def test_run_improvement_loop_meets_target_with_kr_and_us_sample_data() -> None:
    config = load_run_config(Path("examples/paper_target_5.json"))

    report = run_improvement_loop(config)

    assert report.mode == "paper"
    assert report.guaranteed is False
    assert report.live_order_enabled is False
    assert report.target_met is True
    assert report.selected_iteration is not None
    markets = {market_report.market for market_report in report.selected_iteration.markets}
    assert markets == {Market.KR, Market.US}
    assert report.selected_iteration.aggregate_daily_return_pct >= 5.0


def test_run_improvement_loop_records_failed_iterations_before_target() -> None:
    config = load_run_config(Path("examples/paper_target_5.json"))

    report = run_improvement_loop(config)

    assert report.iterations_run > 1
    assert report.iterations[0].target_met is False
    assert report.iterations[-1].target_met is True
