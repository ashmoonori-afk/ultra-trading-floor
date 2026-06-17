from dual_market_trader.models import (
    Fill,
    FillContext,
    MarketBacktest,
    PaperBacktestRequest,
)
from dual_market_trader.strategies import should_enter, should_exit


def run_paper_backtest(request: PaperBacktestRequest) -> MarketBacktest:
    cash = request.initial_cash
    quantity = 0.0
    fills: list[Fill] = []
    peak_equity = request.initial_cash
    max_drawdown_pct = 0.0
    stopped = False
    cost_rate = (request.fee_bps + request.slippage_bps) / 10_000

    for index, candle in enumerate(request.candles):
        equity = cash + quantity * candle.close
        peak_equity = max(peak_equity, equity)
        max_drawdown_pct = max(max_drawdown_pct, _drawdown_pct(peak_equity, equity))
        if equity <= request.initial_cash * (1 - request.risk.max_daily_loss_pct / 100):
            stopped = True
        if stopped:
            continue
        context = FillContext(request.market, request.symbol, candle, cost_rate)
        if quantity > 0 and should_exit(request.candidate, request.candles, index):
            cash, quantity = _sell_all(context, cash, quantity, fills)
        if (
            quantity == 0
            and len(fills) < request.risk.max_trades_per_market
            and should_enter(request.candidate, request.candles, index)
        ):
            cash, quantity = _buy_position(
                context,
                cash,
                min(request.candidate.allocation_fraction, request.risk.max_position_fraction),
                fills,
            )

    if quantity > 0:
        final_context = FillContext(
            request.market,
            request.symbol,
            request.candles[-1],
            cost_rate,
        )
        cash, quantity = _sell_all(final_context, cash, quantity, fills)

    final_equity = cash + quantity * request.candles[-1].close
    daily_return_pct = ((final_equity - request.initial_cash) / request.initial_cash) * 100
    return MarketBacktest(
        market=request.market,
        symbol=request.symbol,
        initial_equity=round(request.initial_cash, 4),
        final_equity=round(final_equity, 4),
        daily_return_pct=round(daily_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        trade_count=len(fills),
        fills=tuple(fills),
    )


def _drawdown_pct(peak_equity: float, equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return ((peak_equity - equity) / peak_equity) * 100


def _buy_position(
    context: FillContext,
    cash: float,
    allocation_fraction: float,
    fills: list[Fill],
) -> tuple[float, float]:
    budget = cash * allocation_fraction
    fill_price = context.candle.close * (1 + context.cost_rate)
    quantity = budget / fill_price
    fee = budget * context.cost_rate
    fills.append(
        Fill(
            context.market,
            context.symbol,
            "buy",
            round(quantity, 8),
            round(fill_price, 4),
            round(fee, 4),
            context.candle.timestamp,
        ),
    )
    return cash - budget, quantity


def _sell_all(
    context: FillContext,
    cash: float,
    quantity: float,
    fills: list[Fill],
) -> tuple[float, float]:
    fill_price = context.candle.close * (1 - context.cost_rate)
    notional = quantity * fill_price
    fee = notional * context.cost_rate
    fills.append(
        Fill(
            context.market,
            context.symbol,
            "sell",
            round(quantity, 8),
            round(fill_price, 4),
            round(fee, 4),
            context.candle.timestamp,
        ),
    )
    return cash + notional - fee, 0.0
