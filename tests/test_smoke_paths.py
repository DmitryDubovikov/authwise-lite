"""Smoke-гейт итерации 0: все три терминала + retry-цикл, ассерты — (branch, retry_cycles)
из PathTrace (правило 6: не OTel, не логи). Всё в replay, $0.
"""

import asyncio

import pytest
from conftest import ROOT, replay_settings

from app.workflow.fixtures import load_requests
from app.workflow.runner import RunRecord, run_batch

EXPECTED = {
    "PA-smoke-001": ("approve", 0),
    "PA-smoke-002": ("approve", 1),
    "PA-smoke-003": ("escalate", 0),
    "PA-smoke-004": ("request-info", 2),
}


@pytest.fixture(scope="module")
def results() -> dict[str, RunRecord]:
    """Один прогон всей фикстуры на модуль через общий раннер (контракт №3); офлайн-Settings
    из conftest, чтобы env/.env не влияли на тест."""
    requests = load_requests(ROOT / "fixtures" / "requests-smoke.jsonl")
    records = asyncio.run(run_batch(requests, settings=replay_settings("smoke")))
    return {r.request_id: r for r in records}


def test_smoke_paths_cover_all_terminals(results: dict[str, RunRecord]) -> None:
    assert set(results) == set(EXPECTED)
    for request_id, result in results.items():
        actual = (result.trace.branch, result.trace.retry_cycles)
        assert actual == EXPECTED[request_id], request_id


def test_retry_loop_revisits_policy_check(results: dict[str, RunRecord]) -> None:
    # nodes — информационное поле, но форма retry-цикла должна быть честной (витрина)
    trace = results["PA-smoke-004"].trace
    assert trace.nodes.count("policy-check") == trace.retry_cycles + 1
    assert trace.nodes.count("request-info") == trace.retry_cycles
