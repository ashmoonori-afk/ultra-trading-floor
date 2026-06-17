from collections.abc import Mapping
from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class LiveTradingDisabledError(Exception):
    missing: tuple[str, ...]

    @override
    def __str__(self) -> str:
        missing = ", ".join(self.missing)
        return (
            "live trading is disabled until credentials and explicit opt-in exist: "
            f"missing {missing}"
        )


def require_live_trading_enabled(
    env: Mapping[str, str],
    *,
    confirm_risk: bool,
) -> None:
    missing: list[str] = []
    if env.get("DMT_LIVE_TRADING_ENABLED") != "true":
        missing.append("DMT_LIVE_TRADING_ENABLED=true")
    if not env.get("DMT_BROKER_API_KEY"):
        missing.append("DMT_BROKER_API_KEY")
    if not env.get("DMT_BROKER_API_SECRET"):
        missing.append("DMT_BROKER_API_SECRET")
    if env.get("TOSS_ALLOW_LIVE_ORDERS") != "true":
        missing.append("TOSS_ALLOW_LIVE_ORDERS=true")
    if not confirm_risk:
        missing.append("--confirm-risk")
    if missing:
        raise LiveTradingDisabledError(tuple(missing))
