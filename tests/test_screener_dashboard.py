from pathlib import Path

from dual_market_trader.dashboard import render_dashboard
from dual_market_trader.models import Market
from dual_market_trader.screener import (
    ScreenedSymbol,
    ScreenerDecision,
    append_screener_decision_log,
)


def test_dashboard_renders_screener_decision_log(tmp_path: Path) -> None:
    screener_log = tmp_path / "screener-decisions.jsonl"
    _ = append_screener_decision_log(
        ScreenerDecision(
            recorded_at="2026-06-18T00:00:00+00:00",
            lookback=3,
            max_positions=2,
            min_score=0,
            candidates=(
                _screened_symbol("000660.KS", 21.5, selected=True),
                _screened_symbol("005930.KS", 3.1, selected=False),
            ),
            selected_candidates=(_screened_symbol("000660.KS", 21.5, selected=True),),
        ),
        screener_log,
    )

    html = render_dashboard(
        tmp_path / "missing-performance.jsonl",
        tmp_path / "missing-live.jsonl",
        tmp_path / "missing-live-paper.jsonl",
        screener_decision_log_path=screener_log,
    )

    assert "Symbol Screener" in html
    assert "000660.KS" in html
    assert "selected" in html
    assert "momentum 5.00%" in html


def _screened_symbol(symbol: str, score: float, *, selected: bool) -> ScreenedSymbol:
    return ScreenedSymbol(
        market=Market.KR,
        symbol=symbol,
        latest_price=112,
        momentum_pct=5,
        breakout_pct=1,
        volume_ratio=1.5,
        volatility_pct=2,
        score=score,
        selected=selected,
        reason="momentum 5.00%, breakout 1.00%, volume ratio 1.50",
    )
