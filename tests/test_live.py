from dataclasses import dataclass
from pathlib import Path

from dual_market_trader.execution import (
    LiveExecutionConfig,
    LivePaperExecutionConfig,
    run_live_execution_loop,
    run_live_paper_execution_loop,
)
from dual_market_trader.live import LiveTradingDisabledError, require_live_trading_enabled
from dual_market_trader.live_models import (
    BrokerName,
    LiveOrderIntent,
    LiveOrderResult,
    LiveOrderStatus,
    OrderSide,
    OrderType,
)
from dual_market_trader.models import Market
from dual_market_trader.reporting import read_live_execution_log, read_live_paper_execution_log
from dual_market_trader.toss import CommandRequest, CommandResult, TossCtlBroker, TossCtlConfig


def test_live_trading_requires_credentials_and_explicit_opt_in() -> None:
    try:
        require_live_trading_enabled({}, confirm_risk=False)
    except LiveTradingDisabledError as exc:
        message = str(exc)
    else:
        message = ""

    assert "DMT_LIVE_TRADING_ENABLED=true" in message
    assert "DMT_BROKER_API_KEY" in message
    assert "DMT_BROKER_API_SECRET" in message
    assert "TOSS_ALLOW_LIVE_ORDERS=true" in message
    assert "--confirm-risk" in message


@dataclass(frozen=True, slots=True)
class _CapturingRunner:
    calls: list[tuple[str, ...]]

    def run(self, request: CommandRequest) -> CommandResult:
        self.calls.append(request.args)
        if len(request.args) < 3:
            msg = f"unexpected command: {request.args}"
            raise AssertionError(msg)
        key = (request.args[1], request.args[2])
        responses = {
            ("auth", "status"): CommandResult(stdout='{"valid": true}', stderr="", returncode=0),
            ("order", "preview"): CommandResult(
                stdout='{"confirm": "token-123"}',
                stderr="",
                returncode=0,
            ),
            ("order", "place"): CommandResult(
                stdout='{"orderId": "order-123"}',
                stderr="",
                returncode=0,
            ),
        }
        try:
            return responses[key]
        except KeyError as exc:
            msg = f"unexpected command: {key}"
            raise AssertionError(msg) from exc


def test_tossctl_broker_places_after_auth_and_preview() -> None:
    runner = _CapturingRunner(calls=[])
    broker = TossCtlBroker(
        TossCtlConfig(
            binary="tossctl",
            env={
                "DMT_LIVE_TRADING_ENABLED": "true",
                "DMT_BROKER_API_KEY": "key",
                "DMT_BROKER_API_SECRET": "secret",
                "TOSS_ALLOW_LIVE_ORDERS": "true",
            },
            confirm_risk=True,
        ),
        runner,
    )
    intent = LiveOrderIntent(
        market=Market.KR,
        symbol="005930",
        side=OrderSide.BUY,
        quantity=1,
        price=71000,
        order_type=OrderType.LIMIT,
    )

    result = broker.place_order(intent)

    assert result.status is LiveOrderStatus.PLACED
    assert result.order_id == "order-123"
    assert runner.calls == [
        ("tossctl", "auth", "status", "--output", "json"),
        (
            "tossctl",
            "order",
            "preview",
            "--symbol",
            "005930",
            "--side",
            "buy",
            "--qty",
            "1",
            "--price",
            "71000",
            "--market",
            "kr",
            "--type",
            "limit",
            "--output",
            "json",
        ),
        (
            "tossctl",
            "order",
            "place",
            "--symbol",
            "005930",
            "--side",
            "buy",
            "--qty",
            "1",
            "--price",
            "71000",
            "--market",
            "kr",
            "--type",
            "limit",
            "--execute",
            "--dangerously-skip-permissions",
            "--confirm",
            "token-123",
            "--output",
            "json",
        ),
    ]


@dataclass(frozen=True, slots=True)
class _PlacedBroker:
    result: LiveOrderResult

    def place_order(self, intent: LiveOrderIntent) -> LiveOrderResult:
        assert intent == self.result.intent
        return self.result


def test_live_execution_loop_persists_append_only_order_log(tmp_path: Path) -> None:
    intent = LiveOrderIntent(
        market=Market.US,
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=2,
        price=210.5,
        order_type=OrderType.LIMIT,
    )
    result = LiveOrderResult(
        recorded_at="2026-06-17T00:00:00+00:00",
        broker=BrokerName.TOSS,
        status=LiveOrderStatus.PLACED,
        intent=intent,
        order_id="us-order-1",
        confirmation_token_present=True,
        broker_message="placed",
    )
    log_path = tmp_path / "live-executions.jsonl"

    results = run_live_execution_loop(
        LiveExecutionConfig(intent=intent, log_path=log_path, max_cycles=2, interval_seconds=0),
        _PlacedBroker(result),
    )

    entries = read_live_execution_log(log_path)
    assert results == (result, result)
    assert entries == (result, result)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_live_paper_execution_loop_persists_without_broker_credentials(tmp_path: Path) -> None:
    intent = LiveOrderIntent(
        market=Market.KR,
        symbol="005930",
        side=OrderSide.BUY,
        quantity=3,
        price=71000,
        order_type=OrderType.LIMIT,
    )
    log_path = tmp_path / "live-paper-executions.jsonl"

    results = run_live_paper_execution_loop(
        LivePaperExecutionConfig(
            intent=intent,
            log_path=log_path,
            max_cycles=2,
            interval_seconds=0,
        ),
    )

    entries = read_live_paper_execution_log(log_path)
    assert len(results) == 2
    assert entries == results
    assert entries[-1].notional == 213000
    assert entries[-1].note == "paper fill only"
