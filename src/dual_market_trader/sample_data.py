from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from dual_market_trader.models import Candle, Market

SYMBOLS_BY_MARKET: Final[Mapping[Market, str]] = MappingProxyType(
    {Market.KR: "005930.KS", Market.US: "AAPL"},
)
CLOSES_BY_MARKET: Final[Mapping[Market, tuple[float, ...]]] = MappingProxyType(
    {
        Market.KR: (100.0, 101.8, 104.5, 107.2, 110.8, 113.4),
        Market.US: (100.0, 102.4, 105.7, 109.6, 113.0, 116.2),
    },
)


def symbol_for_market(market: Market) -> str:
    return SYMBOLS_BY_MARKET[market]


def sample_candles(market: Market) -> tuple[Candle, ...]:
    closes = CLOSES_BY_MARKET[market]
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
