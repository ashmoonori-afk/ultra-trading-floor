from dataclasses import dataclass
from typing import Protocol

from dual_market_trader.live_models import LiveOrderIntent
from dual_market_trader.models import Market


class LatestMarketPriceProvider(Protocol):
    def latest_price(self, market: Market, symbol: str) -> float | None: ...


@dataclass(frozen=True, slots=True)
class YahooLivePaperPriceProvider:
    market_data_provider: LatestMarketPriceProvider

    def latest_price(self, intent: LiveOrderIntent) -> float | None:
        return self.market_data_provider.latest_price(intent.market, intent.symbol)
