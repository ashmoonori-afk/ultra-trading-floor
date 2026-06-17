from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, TypeVar, override

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from dual_market_trader.live import require_live_trading_enabled
from dual_market_trader.live_models import (
    BrokerName,
    LiveOrderIntent,
    LiveOrderResult,
    LiveOrderStatus,
    OrderSide,
    OrderType,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dual_market_trader.models import Market

DEFAULT_TOSSCTL_BINARY: Final = "tossctl"
DEFAULT_TIMEOUT_SECONDS: Final = 15.0


@dataclass(frozen=True, slots=True)
class CommandRequest:
    args: tuple[str, ...]
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class TossCommandRunner(Protocol):
    def run(self, request: CommandRequest) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class TossCtlConfig:
    env: Mapping[str, str]
    confirm_risk: bool
    binary: str = DEFAULT_TOSSCTL_BINARY
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


class TossBrokerError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BrokerCommandFailedError(TossBrokerError):
    request: CommandRequest
    stderr: str
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class BrokerCommandTimedOutError(TossBrokerError):
    request: CommandRequest

    @override
    def __str__(self) -> str:
        return f"{self.request.args[0]} timed out after {self.request.timeout_seconds:.1f}s"


@dataclass(frozen=True, slots=True)
class BrokerResponseError(TossBrokerError):
    raw_response: str

    @override
    def __str__(self) -> str:
        return "tossctl returned malformed JSON"


@dataclass(frozen=True, slots=True)
class BrokerAuthError(TossBrokerError):
    reason: str
    raw_response: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class BrokerPreviewError(TossBrokerError):
    raw_response: str

    @override
    def __str__(self) -> str:
        return "tossctl preview returned no confirm token"


class SubprocessCommandRunner:
    def run(self, request: CommandRequest) -> CommandResult:
        try:
            completed = subprocess.run(  # noqa: S603
                list(request.args),
                check=False,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
            )
        except FileNotFoundError as exc:
            detail = f"{request.args[0]} not found"
            raise BrokerCommandFailedError(
                request,
                "",
                detail,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise BrokerCommandTimedOutError(
                request,
            ) from exc
        return CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )


class _AuthStatusPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    valid: bool | None = None
    active: bool | None = None
    expired: bool | None = None
    authenticated: bool | None = None
    logged_in: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("logged_in", "loggedIn", "isAuthenticated"),
    )
    status: str | None = None
    state: str | None = None
    validation_error: str | None = None


class _PreviewPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    confirmation_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("confirm", "confirmToken", "token", "confirmation"),
    )


class _PlacePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    order_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("orderId", "id", "order_id"),
    )


PayloadT = TypeVar("PayloadT", bound=BaseModel)


class TossCtlBroker:
    def __init__(
        self,
        config: TossCtlConfig,
        runner: TossCommandRunner | None = None,
    ) -> None:
        self._config: TossCtlConfig = config
        self._runner: TossCommandRunner = (
            runner if runner is not None else SubprocessCommandRunner()
        )

    def place_order(self, intent: LiveOrderIntent) -> LiveOrderResult:
        require_live_trading_enabled(
            self._config.env,
            confirm_risk=self._config.confirm_risk,
        )
        self._require_authenticated()
        preview, preview_raw = self._preview(intent)
        if preview.confirmation_token is None:
            raise BrokerPreviewError(preview_raw)
        placed, placed_raw = self._place(intent, preview.confirmation_token)
        return LiveOrderResult(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            broker=BrokerName.TOSS,
            status=LiveOrderStatus.PLACED,
            intent=intent,
            order_id=placed.order_id,
            confirmation_token_present=True,
            broker_message=placed_raw,
        )

    def _require_authenticated(self) -> None:
        payload, raw = self._run_payload(("auth", "status"), _AuthStatusPayload)
        if _is_authenticated(payload):
            return
        reason = payload.validation_error or "tossctl session is not authenticated"
        raise BrokerAuthError(reason, raw)

    def _preview(self, intent: LiveOrderIntent) -> tuple[_PreviewPayload, str]:
        return self._run_payload(
            (
                "order",
                "preview",
                "--symbol",
                intent.symbol,
                "--side",
                _side_arg(intent.side),
                "--qty",
                _format_number(intent.quantity),
                "--price",
                _format_number(intent.price),
                "--market",
                _market_arg(intent.market),
                "--type",
                _order_type_arg(intent.order_type),
            ),
            _PreviewPayload,
        )

    def _place(self, intent: LiveOrderIntent, confirmation_token: str) -> tuple[_PlacePayload, str]:
        return self._run_payload(
            (
                "order",
                "place",
                "--symbol",
                intent.symbol,
                "--side",
                _side_arg(intent.side),
                "--qty",
                _format_number(intent.quantity),
                "--price",
                _format_number(intent.price),
                "--market",
                _market_arg(intent.market),
                "--type",
                _order_type_arg(intent.order_type),
                "--execute",
                "--dangerously-skip-permissions",
                "--confirm",
                confirmation_token,
            ),
            _PlacePayload,
        )

    def _run_payload(
        self,
        args: tuple[str, ...],
        payload_type: type[PayloadT],
    ) -> tuple[PayloadT, str]:
        request = CommandRequest(
            args=_with_output((self._config.binary, *args)),
            timeout_seconds=self._config.timeout_seconds,
        )
        result = self._runner.run(request)
        raw = result.stdout.strip()
        if result.returncode != 0:
            message = result.stderr.strip() or raw or "tossctl command failed"
            raise BrokerCommandFailedError(request, result.stderr, message)
        try:
            payload = payload_type.model_validate_json(raw)
        except ValidationError as exc:
            raise BrokerResponseError(raw) from exc
        return payload, raw


def _with_output(args: tuple[str, ...]) -> tuple[str, ...]:
    if "--output" in args:
        return args
    return (*args, "--output", "json")


def _is_authenticated(payload: _AuthStatusPayload) -> bool:
    if payload.valid is not None:
        return payload.valid
    if payload.active is True and payload.expired is not True:
        return True
    if payload.authenticated is True or payload.logged_in is True:
        return True
    status = payload.status or payload.state
    return status is not None and status.lower() == "authenticated"


def _market_arg(market: Market) -> str:
    return market.value


def _side_arg(side: OrderSide) -> str:
    return side.value


def _order_type_arg(order_type: OrderType) -> str:
    return order_type.value


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"
