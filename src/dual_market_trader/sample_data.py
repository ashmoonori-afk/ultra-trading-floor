from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from dual_market_trader.models import Candle, Market


@dataclass(frozen=True, slots=True)
class SampleScenario:
    name: str
    markets: tuple[Market, ...]


SYMBOLS_BY_MARKET: Final[Mapping[Market, str]] = MappingProxyType(
    {Market.KR: "005930.KS", Market.US: "AAPL"},
)
CLOSES_BY_SCENARIO: Final[Mapping[str, Mapping[Market, tuple[float, ...]]]] = MappingProxyType(
    {
        "training": MappingProxyType(
            {
                Market.KR: (100.0, 101.8, 104.5, 107.2, 110.8, 113.4),
                Market.US: (100.0, 102.4, 105.7, 109.6, 113.0, 116.2),
            },
        ),
        "validation": MappingProxyType(
            {
                Market.KR: (100.0, 101.7, 103.6, 105.4, 107.6, 109.2),
                Market.US: (100.0, 101.9, 104.0, 106.2, 108.4, 110.8),
            },
        ),
        "stress": MappingProxyType(
            {
                Market.KR: (100.0, 99.8, 100.1, 99.7, 100.0, 99.9),
                Market.US: (100.0, 100.2, 99.9, 100.1, 99.8, 100.0),
            },
        ),
    },
)
PRIMARY_VALIDATION_SCENARIOS: Final = ("training", "validation")


def symbol_for_market(market: Market) -> str:
    return SYMBOLS_BY_MARKET[market]


def validation_scenarios() -> tuple[SampleScenario, ...]:
    markets = tuple(SYMBOLS_BY_MARKET)
    return tuple(SampleScenario(name=name, markets=markets) for name in CLOSES_BY_SCENARIO)


def primary_validation_scenarios() -> tuple[str, ...]:
    return PRIMARY_VALIDATION_SCENARIOS


def sample_candles(market: Market, scenario: str = "training") -> tuple[Candle, ...]:
    closes = CLOSES_BY_SCENARIO[scenario][market]
    candles: list[Candle] = []
    for index, close in enumerate(closes):
        prior = closes[index - 1] if index > 0 else close
        high = max(prior, close) * 1.004
        low = min(prior, close) * 0.996
        candles.append(
            Candle(
                timestamp=1_787_000_000 + index * 60,
                open=prior,
                high=round(high, 4),
                low=round(low, 4),
                close=close,
                volume=10_000 + index * 1_000,
            ),
        )
    return tuple(candles)
