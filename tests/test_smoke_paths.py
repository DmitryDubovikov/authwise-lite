"""Smoke-гейт итерации 0: все три терминала + retry-цикл, ассерты — (branch, retry_cycles)
из PathTrace (правило 6: не OTel, не логи). Всё в replay, $0.
"""

import asyncio

import pytest
from conftest import ROOT

from app.config import Settings
from app.workflow.fixtures import load_requests
from app.workflow.graph import PARunResult, run_pa_request

EXPECTED = {
    "PA-smoke-001": ("approve", 0),
    "PA-smoke-002": ("approve", 1),
    "PA-smoke-003": ("escalate", 0),
    "PA-smoke-004": ("request-info", 2),
}


@pytest.fixture(scope="module")
def results() -> dict[str, PARunResult]:
    """Один прогон всей фикстуры на модуль; значащие поля Settings — явными аргументами,
    чтобы env/.env не влияли на тест."""
    settings = Settings(
        llm_mode="replay",
        cassette_set="smoke",
        retry_limit=2,
        tier_classify="cheap",
        tier_policy_check="cheap",
        cassettes_dir=ROOT / "cassettes",
        tiers_path=ROOT / "llm-tiers.yaml",
    )
    requests = load_requests(ROOT / "fixtures" / "requests-smoke.jsonl")

    async def run_all() -> list[PARunResult]:
        return await asyncio.gather(*(run_pa_request(r, settings=settings) for r in requests))

    return dict(zip((r.id for r in requests), asyncio.run(run_all()), strict=True))


def test_smoke_paths_cover_all_terminals(results: dict[str, PARunResult]) -> None:
    assert set(results) == set(EXPECTED)
    for request_id, result in results.items():
        actual = (result.trace.branch, result.trace.retry_cycles)
        assert actual == EXPECTED[request_id], request_id


def test_retry_loop_revisits_policy_check(results: dict[str, PARunResult]) -> None:
    # nodes — информационное поле, но форма retry-цикла должна быть честной (витрина)
    trace = results["PA-smoke-004"].trace
    assert trace.nodes.count("policy-check") == trace.retry_cycles + 1
    assert trace.nodes.count("request-info") == trace.retry_cycles
