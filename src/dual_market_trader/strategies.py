from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from dual_market_trader.models import CandidateConfig, Candle, StrategyKind

StrategyRule = Callable[[CandidateConfig, tuple[Candle, ...], int], bool]


def generate_candidates(max_iterations: int) -> tuple[CandidateConfig, ...]:
    seeds = (
        CandidateConfig(
            StrategyKind.MOMENTUM, threshold_pct=2.0, allocation_fraction=0.45, lookback=1
        ),
        CandidateConfig(
            StrategyKind.MOMENTUM, threshold_pct=1.2, allocation_fraction=0.65, lookback=1
        ),
        CandidateConfig(
            StrategyKind.BREAKOUT, threshold_pct=0.8, allocation_fraction=0.80, lookback=2
        ),
        CandidateConfig(
            StrategyKind.BREAKOUT, threshold_pct=0.2, allocation_fraction=0.95, lookback=1
        ),
        CandidateConfig(
            StrategyKind.BUY_HOLD, threshold_pct=0.0, allocation_fraction=1.0, lookback=1
        ),
    )
    return seeds[:max_iterations]


def should_enter(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    return ENTER_RULES[candidate.strategy](candidate, candles, index)


def should_exit(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    return EXIT_RULES[candidate.strategy](candidate, candles, index)


def _enter_momentum(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    if index < 1:
        return False
    prior = candles[index - 1].close
    return candles[index].close >= prior * (1 + candidate.threshold_pct / 100)


def _enter_breakout(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    if index < candidate.lookback:
        return False
    prior_window = candles[index - candidate.lookback : index]
    high = max(candle.close for candle in prior_window)
    return candles[index].close >= high * (1 + candidate.threshold_pct / 100)


def _enter_buy_hold(
    _candidate: CandidateConfig,
    _candles: tuple[Candle, ...],
    index: int,
) -> bool:
    return index == 0


def _exit_momentum(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    if index < 1:
        return False
    prior = candles[index - 1].close
    return candles[index].close < prior * (1 - candidate.threshold_pct / 200)


def _exit_breakout(candidate: CandidateConfig, candles: tuple[Candle, ...], index: int) -> bool:
    if index < candidate.lookback:
        return False
    prior_window = candles[index - candidate.lookback : index]
    low = min(candle.close for candle in prior_window)
    return candles[index].close <= low


def _exit_buy_hold(
    _candidate: CandidateConfig,
    _candles: tuple[Candle, ...],
    _index: int,
) -> bool:
    return False


ENTER_RULES: Final[Mapping[StrategyKind, StrategyRule]] = MappingProxyType(
    {
        StrategyKind.MOMENTUM: _enter_momentum,
        StrategyKind.BREAKOUT: _enter_breakout,
        StrategyKind.BUY_HOLD: _enter_buy_hold,
    },
)
EXIT_RULES: Final[Mapping[StrategyKind, StrategyRule]] = MappingProxyType(
    {
        StrategyKind.MOMENTUM: _exit_momentum,
        StrategyKind.BREAKOUT: _exit_breakout,
        StrategyKind.BUY_HOLD: _exit_buy_hold,
    },
)
