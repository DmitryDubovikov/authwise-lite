"""Репозиторий trajectory golden-сета: MLflow Evaluation Dataset (штатная сущность ≥3.4).
Единственное место, знающее MLflow-драйвер (правило 6); tracking_uri приходит аргументом
с boundary. merge_records upsert-ится по хэшу inputs → повторная заливка не плодит записи
(идемпотентность done-gate iter 1); правка text/supplemental заявки оставит осиротевшую
старую запись — verify покажет её как «лишнюю в сторе», чистка — вручную или новым датасетом.
"""

from typing import Any

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.genai import datasets

from app.domain.golden import GoldenRecord

DATASET_NAME = "pa-trajectory-golden-base"


def _dataset(name: str, tracking_uri: str) -> datasets.EvaluationDataset:
    mlflow.set_tracking_uri(tracking_uri)
    try:
        return datasets.get_dataset(name=name)
    except MlflowException as exc:
        if exc.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
        return datasets.create_dataset(name=name)


def upload(records: list[dict[str, Any]], *, tracking_uri: str, name: str = DATASET_NAME) -> None:
    """Get-or-create датасета по имени + merge_records — повторный прогон = no-op."""
    _dataset(name, tracking_uri).merge_records(records)


def fetch(*, tracking_uri: str, name: str = DATASET_NAME) -> list[GoldenRecord]:
    """Записи из стора, поднятые в domain-схему (verify the store, not the UI — правило 9)."""
    mlflow.set_tracking_uri(tracking_uri)
    frame = datasets.get_dataset(name=name).to_df()
    return [
        GoldenRecord(
            request_id=row["inputs"]["request_id"],
            allowed_paths=row["expectations"]["allowed_paths"],
            note=row["expectations"].get("note", ""),
        )
        for row in frame.to_dict("records")
    ]
