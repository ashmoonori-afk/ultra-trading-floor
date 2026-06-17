from enum import StrEnum, unique
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dual_market_trader.models import Market


@unique
class BrokerName(StrEnum):
    TOSS = "toss"


@unique
class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@unique
class OrderType(StrEnum):
    LIMIT = "limit"


@unique
class LiveOrderStatus(StrEnum):
    PLACED = "placed"


class LiveOrderIntent(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    market: Market
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    order_type: OrderType = OrderType.LIMIT


class LiveOrderResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    recorded_at: str
    broker: BrokerName
    status: LiveOrderStatus
    intent: LiveOrderIntent
    order_id: str | None
    confirmation_token_present: bool
    broker_message: str
