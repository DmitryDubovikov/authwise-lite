"""Runtime budget controls (iter 4): исчерпание бюджета рана — МАРШРУТ (escalate), не
исключение; видно на уровне траектории. Всё в replay, $0; ассерты — PathTrace (правило 6).

Демо-калибровка: полный ран базовой пачки стоит ~$0.00005–0.00015 (cheap-тир, usage из кассет);
бюджет 0.00008 пропускает первый retry (spent ≈ $0.00006 на decide №1), но обрывает второй.
"""

import asyncio

from conftest import ROOT, replay_settings

from app.config import Settings
from app.domain.schemas import PARequest
from app.workflow.fixtures import load_requests
from app.workflow.graph import run_pa_request
from app.workflow.metrics import aggregate_batch
from app.workflow.runner import run_batch

RETRY_HEAVY = "PA-base-019"  # golden: request-info ↻2 — двум retry есть что обрывать


def _request(request_id: str) -> PARequest:
    requests = load_requests(ROOT / "fixtures" / "requests-base.jsonl")
    return next(r for r in requests if r.id == request_id)


def _base_settings(budget_usd: float) -> Settings:
    return replay_settings("base").model_copy(update={"run_budget_usd": budget_usd})


def test_default_budget_keeps_golden_path() -> None:
    # дефолтный бюджет калиброван с запасом → путь не меняется, флаг не поднят
    result = asyncio.run(run_pa_request(_request(RETRY_HEAVY), settings=replay_settings("base")))
    assert (result.trace.branch, result.trace.retry_cycles) == ("request-info", 2)
    assert not result.budget_escalated


def test_squeezed_budget_turns_retry_loop_into_escalate() -> None:
    result = asyncio.run(run_pa_request(_request(RETRY_HEAVY), settings=_base_settings(0.00008)))
    # первый retry прошёл (остаток ещё был), второй оборван бюджетом → escalate
    assert (result.trace.branch, result.trace.retry_cycles) == ("escalate", 1)
    assert result.budget_escalated


def test_budget_escalation_reaches_runrecord_and_metrics() -> None:
    requests = [_request(RETRY_HEAVY), _request("PA-base-001")]  # ↻2 + прямой approve
    records = asyncio.run(run_batch(requests, settings=_base_settings(0.00008)))
    by_id = {r.request_id: r for r in records}
    assert by_id[RETRY_HEAVY].budget_escalated
    assert not by_id["PA-base-001"].budget_escalated  # approve бюджетом не задет

    batch = aggregate_batch(records, settings=_base_settings(0.00008))
    assert batch.runs == 2
    assert batch.budget_escalations == 1
