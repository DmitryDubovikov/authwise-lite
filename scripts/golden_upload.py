"""Тонкий транспорт: залить trajectory golden-сет в MLflow Evaluation Dataset (идемпотентно)."""

from app.config import get_settings
from app.persistence.golden import DATASET_NAME
from app.workflow.fixtures import load_requests
from app.workflow.golden import load_golden, upload_golden


def main() -> None:
    settings = get_settings()
    requests = load_requests(settings.fixtures_dir / "requests-base.jsonl")
    records = load_golden(settings.fixtures_dir / "golden-base.jsonl")
    count = upload_golden(requests, records, tracking_uri=settings.mlflow_tracking_uri)
    print(f"залито {count} записей в Evaluation Dataset {DATASET_NAME!r} (merge — идемпотентно)")


if __name__ == "__main__":
    main()
