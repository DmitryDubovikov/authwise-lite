"""Оркестрация golden-сета: загрузка разметки, сборка записей Evaluation Dataset,
заливка и verify. Про MLflow-драйвер знает только persistence (правило 6).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.golden import SINGLETON_QUOTA, GoldenRecord, singleton_share
from app.domain.schemas import PARequest
from app.persistence import golden as golden_store
from app.workflow.fixtures import load_jsonl


def load_golden(path: Path) -> list[GoldenRecord]:
    return load_jsonl(path, GoldenRecord)


def build_dataset_records(
    requests: list[PARequest], records: list[GoldenRecord]
) -> list[dict[str, Any]]:
    """inputs = то, что потребляет граф (id, text, supplemental); expectations = допустимые пути
    (+ note — благодаря ему запись стора поднимается обратно в GoldenRecord).
    Разметка обязана биективно накрывать пачку и держать квоту singleton — иначе заливать нечего.
    """
    by_id = {g.request_id: g for g in records}
    if len(by_id) != len(records):
        raise ValueError("дубли request_id в golden-разметке")
    if {r.id for r in requests} != set(by_id):
        raise ValueError("golden-разметка не совпадает с пачкой заявок по request_id")
    share = singleton_share(records)
    if share < SINGLETON_QUOTA:
        raise ValueError(f"квота singleton нарушена: {share:.0%} < {SINGLETON_QUOTA:.0%}")
    return [
        {
            "inputs": {
                "request_id": request.id,
                "text": request.text,
                "supplemental": request.supplemental,
            },
            "expectations": {
                "allowed_paths": [p.model_dump() for p in by_id[request.id].allowed_paths],
                "note": by_id[request.id].note,
            },
        }
        for request in requests
    ]


def upload_golden(
    requests: list[PARequest], records: list[GoldenRecord], *, tracking_uri: str
) -> int:
    dataset_records = build_dataset_records(requests, records)
    golden_store.upload(dataset_records, tracking_uri=tracking_uri)
    return len(dataset_records)


@dataclass(frozen=True)
class GoldenVerification:
    """Сводка verify: всё посчитано по данным ИЗ стора (правило 9), не по локальным файлам."""

    records: list[GoldenRecord]
    singleton_share: float
    missing_ids: frozenset[str]  # есть в пачке, нет в сторе
    extra_ids: frozenset[str]  # есть в сторе, нет в пачке (сироты после правки inputs)

    def ok(self) -> bool:
        return (
            not self.missing_ids and not self.extra_ids and self.singleton_share >= SINGLETON_QUOTA
        )


def verify_golden(*, tracking_uri: str, expected_ids: set[str]) -> GoldenVerification:
    records = golden_store.fetch(tracking_uri=tracking_uri)
    store_ids = {r.request_id for r in records}
    return GoldenVerification(
        records=records,
        singleton_share=singleton_share(records),
        missing_ids=frozenset(expected_ids - store_ids),
        extra_ids=frozenset(store_ids - expected_ids),
    )
