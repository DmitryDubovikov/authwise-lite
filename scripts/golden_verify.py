"""Тонкий транспорт: verify golden-сета В СТОРЕ (правило 9) — читает Evaluation Dataset
через MLflow API, печатает записи с expectations, проверяет покрытие пачки по id и квоту
singleton. Вся семантика verify — в workflow (GoldenVerification), здесь только печать.
"""

from app.config import get_settings
from app.domain.golden import SINGLETON_QUOTA, GoldenRecord
from app.persistence.golden import DATASET_NAME
from app.workflow.fixtures import load_requests
from app.workflow.golden import verify_golden


def _render(record: GoldenRecord) -> str:
    return " | ".join(f"{p.branch} ↻{p.retry_cycles}" for p in record.allowed_paths)


def main() -> None:
    settings = get_settings()
    expected_ids = {r.id for r in load_requests(settings.fixtures_dir / "requests-base.jsonl")}
    result = verify_golden(tracking_uri=settings.mlflow_tracking_uri, expected_ids=expected_ids)
    for record in sorted(result.records, key=lambda r: r.request_id):
        joker = "  [джокер]" if not record.is_singleton else ""
        print(f"{record.request_id}: {_render(record)}{joker}")
    print()  # отделить построчный дамп от сводки
    for label, ids in (("нет в сторе", result.missing_ids), ("лишние в сторе", result.extra_ids)):
        if ids:
            print(f"{label}: {', '.join(sorted(ids))}")
    # singleton — строгость разметки (её настоящий гейт — pytest); здесь справочно, не вердикт
    below = "" if result.singleton_share >= SINGLETON_QUOTA else "  ← ниже квоты"
    print(f"singleton {result.singleton_share:.0%} (квота ≥{SINGLETON_QUOTA:.0%}){below}")

    rule = "─" * 60
    if not result.ok():
        print(f"{rule}\n❌  VERIFY FAILED — стор не соответствует ожиданиям (см. выше)")
        raise SystemExit(1)
    print(
        f"{rule}\n✅  VERIFY OK — {DATASET_NAME}: "
        f"{len(result.records)} записей (ожидалось {len(expected_ids)}), расхождений с пачкой нет"
    )


if __name__ == "__main__":
    main()
