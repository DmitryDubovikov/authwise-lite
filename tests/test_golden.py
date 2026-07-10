"""Гейт iter 1: golden-разметка честная (правило 3) и заливается идемпотентно.
Всё offline: домен — чистые функции; идемпотентность merge — на временном sqlite-сторе,
это тот же SQL-бэкенд, что в slim-Compose, без docker и без сети.
"""

from pathlib import Path

import pytest
from conftest import ROOT

from app.domain.golden import (
    SINGLETON_QUOTA,
    AllowedPath,
    GoldenRecord,
    path_allowed,
    singleton_share,
)
from app.domain.path import PathTrace
from app.workflow.fixtures import load_requests
from app.workflow.golden import build_dataset_records, load_golden, upload_golden, verify_golden

JOKERS = {"PA-base-027", "PA-base-028", "PA-base-029", "PA-base-030"}  # поимённо (спека 01)


@pytest.fixture(scope="module")
def golden() -> list[GoldenRecord]:
    return load_golden(ROOT / "fixtures" / "golden-base.jsonl")


@pytest.fixture(scope="module")
def requests() -> list:
    return load_requests(ROOT / "fixtures" / "requests-base.jsonl")


def test_golden_covers_base_pack_bijectively(golden: list[GoldenRecord], requests: list) -> None:
    assert len(golden) == 30
    assert {g.request_id for g in golden} == {r.id for r in requests}


def test_singleton_quota_holds(golden: list[GoldenRecord]) -> None:
    assert singleton_share(golden) >= SINGLETON_QUOTA


def test_jokers_are_exactly_the_named_ones(golden: list[GoldenRecord]) -> None:
    assert {g.request_id for g in golden if not g.is_singleton} == JOKERS


def test_path_allowed_is_membership() -> None:
    record = GoldenRecord(
        request_id="PA-x-001",
        allowed_paths=[
            AllowedPath(branch="approve", retry_cycles=0),
            AllowedPath(branch="approve", retry_cycles=1),
        ],
        note="джокер для теста",
    )
    assert path_allowed(PathTrace(branch="approve", retry_cycles=1, nodes=()), record)
    assert not path_allowed(PathTrace(branch="approve", retry_cycles=2, nodes=()), record)
    assert not path_allowed(PathTrace(branch="escalate", retry_cycles=0, nodes=()), record)


def test_joker_without_note_is_rejected() -> None:
    with pytest.raises(ValueError, match="без note"):
        GoldenRecord(
            request_id="PA-x-002",
            allowed_paths=[
                AllowedPath(branch="approve", retry_cycles=0),
                AllowedPath(branch="escalate", retry_cycles=0),
            ],
        )


def test_duplicate_allowed_paths_are_rejected() -> None:
    with pytest.raises(ValueError, match="дубли"):
        GoldenRecord(
            request_id="PA-x-003",
            allowed_paths=[
                AllowedPath(branch="approve", retry_cycles=0),
                AllowedPath(branch="approve", retry_cycles=0),
            ],
            note="дубль",
        )


def test_build_dataset_records_shape(golden: list[GoldenRecord], requests: list) -> None:
    records = build_dataset_records(requests, golden)
    assert len(records) == len(requests)
    by_id = {r["inputs"]["request_id"]: r for r in records}
    joker = by_id["PA-base-030"]
    assert joker["inputs"]["supplemental"]  # inputs несут то, что потребляет граф
    assert len(joker["expectations"]["allowed_paths"]) == 2


def test_build_dataset_records_rejects_id_mismatch(
    golden: list[GoldenRecord], requests: list
) -> None:
    with pytest.raises(ValueError, match="request_id"):
        build_dataset_records(requests[:-1], golden)


def test_upload_is_idempotent(golden: list[GoldenRecord], requests: list, tmp_path: Path) -> None:
    """Двойная заливка + verify на временном sqlite-сторе: записи не плодятся."""
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    expected_ids = {r.id for r in requests}
    assert upload_golden(requests, golden, tracking_uri=uri) == 30
    assert upload_golden(requests, golden, tracking_uri=uri) == 30
    verification = verify_golden(tracking_uri=uri, expected_ids=expected_ids)
    assert len(verification.records) == 30
    assert verification.ok()
