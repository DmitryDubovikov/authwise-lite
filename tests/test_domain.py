"""Чистые domain-функции: decide, render_path, парсинг структурированных выходов."""

import pytest

from app.domain.decide import decide
from app.domain.path import PathTrace, render_path
from app.domain.schemas import PolicyCheckResult, json_object, parse_policy_check


def _policy(status: str) -> PolicyCheckResult:
    return PolicyCheckResult(status=status)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "retry_cycles", "expected"),
    [
        ("sufficient", 0, "approve"),
        ("sufficient", 2, "approve"),
        ("out_of_policy", 0, "escalate"),
        ("out_of_policy", 2, "escalate"),
        ("missing_info", 0, "retry"),
        ("missing_info", 1, "retry"),
        ("missing_info", 2, "request-info"),  # потолок N=2 исчерпан → терминал
    ],
)
def test_decide(status: str, retry_cycles: int, expected: str) -> None:
    assert (
        decide(_policy(status), retry_cycles=retry_cycles, retry_limit=2, budget_remaining_usd=1.0)
        == expected
    )


def test_decide_zero_limit_never_retries() -> None:
    decision = decide(
        _policy("missing_info"), retry_cycles=0, retry_limit=0, budget_remaining_usd=1.0
    )
    assert decision == "request-info"


@pytest.mark.parametrize("remaining", [0.0, -0.001])
def test_decide_exhausted_budget_escalates_instead_of_retry(remaining: float) -> None:
    # контракт №2: исчерпание бюджета — маршрут escalate, а не исключение
    decision = decide(
        _policy("missing_info"), retry_cycles=0, retry_limit=2, budget_remaining_usd=remaining
    )
    assert decision == "escalate"


@pytest.mark.parametrize("status", ["sufficient", "out_of_policy"])
def test_decide_budget_gates_only_retry(status: str) -> None:
    # исчерпанный бюджет не трогает решения, где нового LLM-цикла не будет
    with_budget = decide(_policy(status), retry_cycles=0, retry_limit=2, budget_remaining_usd=1.0)
    without = decide(_policy(status), retry_cycles=0, retry_limit=2, budget_remaining_usd=0.0)
    assert with_budget == without


def test_decide_exhausted_limit_beats_budget() -> None:
    # исчерпаны и потолок N, и бюджет → терминал остаётся request-info (LLM-цикла всё равно нет)
    decision = decide(
        _policy("missing_info"), retry_cycles=2, retry_limit=2, budget_remaining_usd=0.0
    )
    assert decision == "request-info"


def test_render_path_without_retries() -> None:
    trace = PathTrace(branch="approve", retry_cycles=0, nodes=())
    assert render_path(trace) == "classify → policy-check → approve"


def test_render_path_with_retries() -> None:
    trace = PathTrace(branch="approve", retry_cycles=2, nodes=())
    assert render_path(trace) == "classify → policy-check → request-info ↻2 → approve"


def test_render_path_terminal_request_info_not_duplicated() -> None:
    trace = PathTrace(branch="request-info", retry_cycles=2, nodes=())
    assert render_path(trace) == "classify → policy-check → request-info ↻2"


def test_json_object_tolerates_fences() -> None:
    raw = 'Sure! ```json\n{"status": "sufficient", "missing": [], "rationale": "ok"}\n```'
    assert parse_policy_check(raw).status == "sufficient"


def test_json_object_rejects_prose() -> None:
    with pytest.raises(ValueError):
        json_object("no json here")
