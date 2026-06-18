import pytest

from dual_market_trader.models import Market
from dual_market_trader.sample_data import sample_candles, validation_scenarios


def test_validation_scenarios_are_deterministic_for_kr_and_us() -> None:
    first = validation_scenarios()
    second = validation_scenarios()

    assert tuple(scenario.name for scenario in first) == ("training", "validation", "stress")
    assert first == second
    assert sample_candles(Market.KR) == sample_candles(Market.KR, scenario="training")
    assert len(sample_candles(Market.KR, scenario="validation")) == 6
    assert len(sample_candles(Market.US, scenario="validation")) == 6


def test_unknown_validation_scenario_is_rejected() -> None:
    with pytest.raises(KeyError) as exc_info:
        _ = sample_candles(Market.KR, scenario="unknown")

    assert exc_info.value.args == ("unknown",)
