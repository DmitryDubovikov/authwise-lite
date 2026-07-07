"""Тонкий транспорт: прогнать заявки фикстуры через граф и напечатать путь каждой."""

import argparse
import asyncio
from pathlib import Path

from app.config import Settings, get_settings
from app.domain.path import render_path
from app.domain.schemas import PARequest
from app.workflow.fixtures import load_requests
from app.workflow.graph import PARunResult, run_pa_request


async def _run_all(requests: list[PARequest], settings: Settings) -> list[PARunResult]:
    return await asyncio.gather(*(run_pa_request(r, settings=settings) for r in requests))


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
    results = asyncio.run(_run_all(requests, settings))
    for request, result in zip(requests, results, strict=True):
        print(f"{request.id}: {render_path(result.trace)}")


if __name__ == "__main__":
    main()
