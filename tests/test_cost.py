"""cost_usd — единственная функция стоимости (контракт №5): usage × цены тира, чистая математика."""

import pytest

from app.domain.cost import cost_usd


def test_cost_is_usage_times_tier_prices() -> None:
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}
    assert cost_usd(usage, input_per_1m=0.10, output_per_1m=0.40) == pytest.approx(0.30)


def test_no_usage_means_no_cost() -> None:
    assert cost_usd(None, input_per_1m=0.10, output_per_1m=0.40) is None


def test_missing_token_counts_default_to_zero() -> None:
    assert cost_usd({}, input_per_1m=0.10, output_per_1m=0.40) == 0.0
