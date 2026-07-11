"""Тонкий транспорт: прогнать заявки фикстуры через граф и напечатать путь каждой."""

import argparse
import asyncio
from pathlib import Path

from app.config import get_settings
from app.domain.path import render_path
from app.workflow.fixtures import load_requests
from app.workflow.runner import records_path, run_batch, write_records


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="authwise",
        description="Прогон PA-заявок через граф; печатает путь (PathTrace) каждой заявки.",
    )
    parser.add_argument("fixture", type=Path, help="JSONL-файл с заявками (контракт №1)")
    parser.add_argument("--id", dest="request_id", default=None, help="только одна заявка")
    args = parser.parse_args()

    settings = get_settings()
    requests = load_requests(args.fixture)
    if args.request_id is not None:
        requests = [r for r in requests if r.id == args.request_id]
        if not requests:
            raise SystemExit(f"заявка {args.request_id!r} не найдена в {args.fixture}")
    records = asyncio.run(run_batch(requests, settings=settings))
    if args.request_id is None:
        # RunRecord JSONL (контракт №3) — только полный прогон: дебаг одной заявки через --id
        # не должен молча затирать батч-артефакт, который читают metrics-push и drift-push
        write_records(records, records_path(settings))
    for record in records:
        marker = "  [budget]" if record.budget_escalated else ""
        print(f"{record.request_id}: {render_path(record.trace)}{marker}")


if __name__ == "__main__":
    main()
