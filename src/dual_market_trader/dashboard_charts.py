from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING, Final

from dual_market_trader.chart_trades import TradeMarkerKind
from dual_market_trader.charting import MarketDataSource
from dual_market_trader.dashboard_tables import format_pct

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dual_market_trader.chart_trades import TradeMarker
    from dual_market_trader.charting import MarketMinuteChart
    from dual_market_trader.models import Candle

SVG_WIDTH: Final = 760
SVG_HEIGHT: Final = 260
PLOT_LEFT: Final = 44
PLOT_RIGHT: Final = 724
PLOT_TOP: Final = 18
PLOT_BOTTOM: Final = 218
COMPACT_PRICE_THRESHOLD: Final = 1_000.0
EDGE_LABEL_THRESHOLD: Final = 128.0


@dataclass(frozen=True, slots=True)
class ChartScale:
    min_timestamp: int
    max_timestamp: int
    min_price: float
    max_price: float


def render_market_charts(charts: Sequence[MarketMinuteChart]) -> str:
    return "\n".join(
        (
            '    <section class="market-charts">',
            '      <div class="section-bar">',
            "        <h2>Market Minute Charts</h2>",
            "        <span>1m candles with paper entry, target exit, and stop loss markers</span>",
            "      </div>",
            '      <div class="chart-grid">',
            "\n".join(_chart_card(chart) for chart in charts),
            "      </div>",
            "    </section>",
        ),
    )


def _chart_card(chart: MarketMinuteChart) -> str:
    market = chart.market.value
    symbol = escape(chart.symbol)
    return "\n".join(
        (
            (
                f'        <article class="chart-panel" data-chart-market="{market}" '
                f'data-chart-symbol="{symbol}">'
            ),
            '          <div class="chart-head">',
            f"            <div><strong>{escape(market.upper())}</strong> {symbol}</div>",
            f'            <span class="interval">{escape(_source_label(chart))}</span>',
            "          </div>",
            _chart_status(chart),
            _chart_svg(chart),
            _legend(chart),
            "        </article>",
        ),
    )


def _chart_status(chart: MarketMinuteChart) -> str:
    return "\n".join(
        (
            '          <div class="chart-status">',
            f"            <span>{escape(chart.data_notice)}</span>",
            f"            <strong>Live PnL {escape(format_pct(chart.live_return_pct))}</strong>",
            "          </div>",
        ),
    )


def _source_label(chart: MarketMinuteChart) -> str:
    if chart.data_source is MarketDataSource.YAHOO:
        return "YAHOO REAL 1M"
    return "FALLBACK 1M"


def _chart_svg(chart: MarketMinuteChart) -> str:
    scale = _chart_scale(chart)
    parts = [
        (
            f'          <svg class="minute-chart" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
            'role="img" aria-label="minute candle chart">'
        ),
        '            <rect class="chart-bg" x="0" y="0" width="760" height="260" />',
        _grid_lines(scale),
        "\n".join(_candle_svg(candle, scale) for candle in chart.candles),
        "\n".join(_marker_svg(marker, scale) for marker in chart.markers),
        "          </svg>",
    ]
    return "\n".join(parts)


def _chart_scale(chart: MarketMinuteChart) -> ChartScale:
    prices = tuple(
        price
        for candle in chart.candles
        for price in (candle.high, candle.low, candle.open, candle.close)
    ) + tuple(marker.price for marker in chart.markers)
    min_price = min(prices)
    max_price = max(prices)
    padding = max((max_price - min_price) * 0.08, max_price * 0.002)
    return ChartScale(
        min_timestamp=chart.candles[0].timestamp,
        max_timestamp=chart.candles[-1].timestamp,
        min_price=min_price - padding,
        max_price=max_price + padding,
    )


def _grid_lines(scale: ChartScale) -> str:
    rows: list[str] = []
    for index in range(5):
        y = PLOT_TOP + (PLOT_BOTTOM - PLOT_TOP) * index / 4
        price = scale.max_price - (scale.max_price - scale.min_price) * index / 4
        rows.append(
            (
                f'            <line class="grid-line" x1="{PLOT_LEFT}" y1="{y:.2f}" '
                f'x2="{PLOT_RIGHT}" y2="{y:.2f}" />'
            ),
        )
        rows.append(
            (
                f'            <text class="axis-label" x="8" y="{y + 4:.2f}">'
                f"{escape(_format_price(price))}</text>"
            ),
        )
    return "\n".join(rows)


def _candle_svg(candle: Candle, scale: ChartScale) -> str:
    x = _x(candle.timestamp, scale)
    open_y = _y(candle.open, scale)
    close_y = _y(candle.close, scale)
    high_y = _y(candle.high, scale)
    low_y = _y(candle.low, scale)
    top = min(open_y, close_y)
    height = max(abs(open_y - close_y), 1.6)
    tone = "up" if candle.close >= candle.open else "down"
    return "\n".join(
        (
            (
                f'            <line class="wick {tone}" x1="{x:.2f}" y1="{high_y:.2f}" '
                f'x2="{x:.2f}" y2="{low_y:.2f}" />'
            ),
            (
                f'            <rect class="candle {tone}" x="{x - 3:.2f}" y="{top:.2f}" '
                f'width="6" height="{height:.2f}" />'
            ),
        ),
    )


def _marker_svg(marker: TradeMarker, scale: ChartScale) -> str:
    x = _x(marker.timestamp, scale)
    y = _y(marker.price, scale)
    label = escape(f"{marker.label} {_format_price(marker.price)}")
    klass = marker.kind.value
    label_x, anchor = _marker_label_position(x)
    label_y = _marker_label_y(marker.kind, y)
    match marker.kind:
        case TradeMarkerKind.ENTRY:
            return "\n".join(
                (
                    f'            <g class="trade-marker {klass}" data-marker-kind="{klass}">',
                    (
                        f'              <line x1="{x:.2f}" y1="{PLOT_TOP}" '
                        f'x2="{x:.2f}" y2="{PLOT_BOTTOM}" />'
                    ),
                    f'              <circle cx="{x:.2f}" cy="{y:.2f}" r="4.8" />',
                    (
                        f'              <text x="{label_x:.2f}" y="{label_y:.2f}" '
                        f'text-anchor="{anchor}">{label}</text>'
                    ),
                    "            </g>",
                ),
            )
        case TradeMarkerKind.TARGET | TradeMarkerKind.STOP:
            return "\n".join(
                (
                    f'            <g class="trade-marker {klass}" data-marker-kind="{klass}">',
                    (
                        f'              <line x1="{x:.2f}" y1="{y:.2f}" '
                        f'x2="{PLOT_RIGHT}" y2="{y:.2f}" />'
                    ),
                    (
                        f'              <text x="{label_x:.2f}" y="{label_y:.2f}" '
                        f'text-anchor="{anchor}">{label}</text>'
                    ),
                    "            </g>",
                ),
            )


def _legend(chart: MarketMinuteChart) -> str:
    return "\n".join(
        (
            '          <div class="chart-legend">',
            '            <span><b class="entry-dot"></b>Entry</span>',
            (
                '            <span><b class="target-dot"></b>'
                f"Target Exit +{chart.target_daily_return_pct:.2f}%</span>"
            ),
            (
                '            <span><b class="stop-dot"></b>'
                f"Stop Loss -{chart.stop_loss_pct:.2f}%</span>"
            ),
            "          </div>",
        ),
    )


def _x(timestamp: int, scale: ChartScale) -> float:
    width = PLOT_RIGHT - PLOT_LEFT
    if scale.max_timestamp == scale.min_timestamp:
        return PLOT_LEFT + width
    ratio = (timestamp - scale.min_timestamp) / (scale.max_timestamp - scale.min_timestamp)
    bounded = min(max(ratio, 0), 1)
    return PLOT_LEFT + width * bounded


def _y(price: float, scale: ChartScale) -> float:
    height = PLOT_BOTTOM - PLOT_TOP
    ratio = (price - scale.min_price) / (scale.max_price - scale.min_price)
    bounded = min(max(ratio, 0), 1)
    return PLOT_BOTTOM - height * bounded


def _marker_label_position(x: float) -> tuple[float, str]:
    if x > PLOT_RIGHT - EDGE_LABEL_THRESHOLD:
        return x - 8, "end"
    return x + 8, "start"


def _marker_label_y(kind: TradeMarkerKind, y: float) -> float:
    match kind:
        case TradeMarkerKind.ENTRY:
            return min(max(PLOT_TOP + 12, y - 18), PLOT_BOTTOM - 34)
        case TradeMarkerKind.TARGET:
            return min(max(PLOT_TOP + 26, y - 6), PLOT_BOTTOM - 18)
        case TradeMarkerKind.STOP:
            return min(max(PLOT_TOP + 40, y + 14), PLOT_BOTTOM + 12)


def _format_price(value: float) -> str:
    if value >= COMPACT_PRICE_THRESHOLD:
        return f"{value:,.0f}"
    return f"{value:,.2f}"
