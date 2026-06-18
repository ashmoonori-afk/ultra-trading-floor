from dataclasses import dataclass
from pathlib import Path

from dual_market_trader.charting import ChartSpec, MarketDataSource, MarketMinuteSeries
from dual_market_trader.models import Candle, Market
from dual_market_trader.reporting import read_live_paper_execution_log
from dual_market_trader.screener import (
    ScreenerPaperConfig,
    ScreenerRequest,
    SymbolCandidateSpec,
    read_screener_decision_log,
    run_screener_paper_loop,
    screen_symbols,
)


@dataclass(frozen=True, slots=True)
class _FakeMinuteProvider:
    series: tuple[MarketMinuteSeries, ...]

    def load_minute_candles(self, specs: tuple[ChartSpec, ...]) -> tuple[MarketMinuteSeries, ...]:
        requested = {(spec.market, spec.symbol.upper().removesuffix(".KS")) for spec in specs}
        return tuple(
            item
            for item in self.series
            if (item.market, item.symbol.upper().removesuffix(".KS")) in requested
        )


def test_screen_symbols_ranks_multiple_kr_and_us_candidates() -> None:
    request = ScreenerRequest(
        symbols=(
            SymbolCandidateSpec(market=Market.KR, symbol="005930"),
            SymbolCandidateSpec(market=Market.KR, symbol="000660"),
            SymbolCandidateSpec(market=Market.US, symbol="AAPL"),
        ),
        max_positions=2,
        min_score=0,
        lookback=3,
    )
    provider = _FakeMinuteProvider(
        series=(
            _series(Market.KR, "005930.KS", (100, 101, 101.5, 102), (10, 10, 10, 11)),
            _series(Market.KR, "000660.KS", (100, 105, 108, 112), (10, 12, 16, 22)),
            _series(Market.US, "AAPL", (200, 201, 203, 207), (20, 21, 21, 24)),
        ),
    )

    decision = screen_symbols(request, provider)

    assert tuple(item.symbol for item in decision.selected_candidates) == ("000660.KS", "AAPL")
    assert decision.candidates[0].score > decision.candidates[-1].score
    assert decision.selected_candidates[0].latest_price == 112


def test_screener_paper_loop_logs_selected_multi_symbol_fills(tmp_path: Path) -> None:
    decision_log = tmp_path / "screener-decisions.jsonl"
    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    config = ScreenerPaperConfig(
        request=ScreenerRequest(
            symbols=(
                SymbolCandidateSpec(market=Market.KR, symbol="005930"),
                SymbolCandidateSpec(market=Market.KR, symbol="000660"),
                SymbolCandidateSpec(market=Market.US, symbol="AAPL"),
            ),
            max_positions=2,
            min_score=0,
            lookback=3,
        ),
        per_position_notional=1000,
        decision_log_path=decision_log,
        live_paper_log_path=live_paper_log,
        max_cycles=1,
        interval_seconds=0,
    )
    provider = _FakeMinuteProvider(
        series=(
            _series(Market.KR, "005930.KS", (100, 101, 101.5, 102), (10, 10, 10, 11)),
            _series(Market.KR, "000660.KS", (100, 105, 108, 112), (10, 12, 16, 22)),
            _series(Market.US, "AAPL", (200, 201, 203, 207), (20, 21, 21, 24)),
        ),
    )

    results = run_screener_paper_loop(config, provider)

    decisions = read_screener_decision_log(decision_log)
    fills = read_live_paper_execution_log(live_paper_log)
    assert len(results) == 1
    assert len(decisions) == 1
    assert tuple(item.symbol for item in decisions[0].selected_candidates) == ("000660.KS", "AAPL")
    assert tuple(fill.intent.symbol for fill in fills) == ("000660.KS", "AAPL")
    assert fills[0].fill_price == 112
    assert fills[0].note == "paper fill at screener-selected market price"


def test_screener_paper_loop_skips_same_symbol_reentry(tmp_path: Path) -> None:
    decision_log = tmp_path / "screener-decisions.jsonl"
    live_paper_log = tmp_path / "live-paper-executions.jsonl"
    config = ScreenerPaperConfig(
        request=ScreenerRequest(
            symbols=(SymbolCandidateSpec(market=Market.US, symbol="AAPL"),),
            max_positions=1,
            min_score=-100,
            lookback=2,
        ),
        per_position_notional=1000,
        decision_log_path=decision_log,
        live_paper_log_path=live_paper_log,
        max_cycles=2,
        interval_seconds=0,
    )
    provider = _FakeMinuteProvider(
        series=(_series(Market.US, "AAPL", (100, 101, 102, 103), (10, 10, 12, 14)),),
    )

    results = run_screener_paper_loop(config, provider)

    decisions = read_screener_decision_log(decision_log)
    fills = read_live_paper_execution_log(live_paper_log)
    assert len(results) == 2
    assert len(decisions) == 2
    assert len(results[0].fills) == 1
    assert results[1].fills == ()
    assert len(fills) == 1


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
