"""Гейт iter 2 — path-assertion gate / trajectory regression testing (красная нить).
Базовая пачка в replay → каждый путь ∈ golden allowed_paths (зелёный: этот тест и есть
CI-блокер регрессии маршрута). Сломанный набор base-broken-policy → гейт КРАСНЕЕТ из-за смены
маршрута, а не cassette-miss (ловушка ROADMAP Заметки №2). Всё offline/replay, $0.

SUBSET/REGRESSED зеркалят authored-набор scripts/author_broken_cassettes.py (scripts не
устанавливается как пакет → не импортируем; расхождение всплывёт cassette-miss'ом или
несходимостью множеств ниже).
"""

import asyncio
from pathlib import Path

import pytest
from conftest import ROOT, replay_settings

from app.domain.gate import GateReport, build_gate_report
from app.workflow.fixtures import load_requests
from app.workflow.golden import load_golden
from app.workflow.runner import RunRecord, read_records, run_batch, write_records

CONTROLS = {"PA-base-001", "PA-base-003"}  # golden approve ↻0 — на сломанном наборе остаются им
REGRESSED = {"PA-base-015", "PA-base-019", "PA-base-021"}  # ветка/retry ушли с golden
SUBSET = CONTROLS | REGRESSED


def _run(cassette_set: str, ids: set[str] | None = None) -> tuple[GateReport, list[RunRecord]]:
    requests = load_requests(ROOT / "fixtures" / "requests-base.jsonl")
    golden = load_golden(ROOT / "fixtures" / "golden-base.jsonl")
    if ids is not None:
        requests = [r for r in requests if r.id in ids]
        golden = [g for g in golden if g.request_id in ids]
    records = asyncio.run(run_batch(requests, settings=replay_settings(cassette_set)))
    report = build_gate_report({r.request_id: r.trace for r in records}, golden)
    return report, records


@pytest.fixture(scope="module")
def base_run() -> tuple[GateReport, list[RunRecord]]:
    return _run("base")


@pytest.fixture(scope="module")
def broken_run() -> tuple[GateReport, list[RunRecord]]:
    return _run("base-broken-policy", ids=SUBSET)


def test_base_pack_passes_gate(base_run: tuple[GateReport, list[RunRecord]]) -> None:
    report, _ = base_run
    assert report.passed
    assert len(report.rows) == 30


def test_broken_set_regresses_on_route_change(
    broken_run: tuple[GateReport, list[RunRecord]],
) -> None:
    # дошли до ассерта → replay нашёл кассеты (miss = громкая ошибка) → краснота из-за МАРШРУТА
    report, _ = broken_run
    assert not report.passed
    assert {r.request_id for r in report.regressions} == REGRESSED


def test_controls_stay_green_no_false_alarm(
    broken_run: tuple[GateReport, list[RunRecord]],
) -> None:
    report, _ = broken_run
    assert {r.request_id for r in report.rows if r.ok} == CONTROLS


def test_runrecord_jsonl_roundtrip(
    base_run: tuple[GateReport, list[RunRecord]], tmp_path: Path
) -> None:
    _, records = base_run
    path = tmp_path / "base.jsonl"
    write_records(records, path)
    assert read_records(path) == records
