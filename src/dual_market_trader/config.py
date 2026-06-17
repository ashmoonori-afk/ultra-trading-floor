from pathlib import Path

from dual_market_trader.models import RunConfig


def load_run_config(path: Path) -> RunConfig:
    return RunConfig.model_validate_json(path.read_text(encoding="utf-8"))
