"""RunRecord — единый артефакт батч-прогона (контракт №3): один раннер в workflow-слое гонит
пачку через граф и отдаёт `{request_id, path_trace}`. CI-таблица (iter 2), Prometheus (iter 4),
Phoenix (iter 5), Prefect (iter 7) читают ЕГО, а не гоняют граф каждый по-своему. Здесь только
путь — per-node usage/latency добавятся в iter 3/4 (контракт №3), новых полей PathTrace нет.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.domain.path import PathTrace
from app.domain.schemas import PARequest
from app.workflow.graph import run_pa_request


@dataclass(frozen=True)
class RunRecord:
    request_id: str
    trace: PathTrace  # источник истины golden/CI-ассертов (правило 6)
    # aw-lite: per-node usage/latency → iter 3/4 (контракт №3), здесь только путь


async def run_batch(requests: list[PARequest], *, settings: Settings) -> list[RunRecord]:
    """Прогнать пачку через граф (в replay — $0) → RunRecord на заявку, в порядке пачки."""
    results = await asyncio.gather(*(run_pa_request(r, settings=settings) for r in requests))
    return [
        RunRecord(request_id=request.id, trace=result.trace)
        for request, result in zip(requests, results, strict=True)
    ]


def _to_dict(record: RunRecord) -> dict[str, object]:
    return {
        "request_id": record.request_id,
        "path_trace": {
            "branch": record.trace.branch,
            "retry_cycles": record.trace.retry_cycles,
            "nodes": list(record.trace.nodes),
        },
    }


def _from_dict(data: dict[str, object]) -> RunRecord:
    trace = data["path_trace"]
    assert isinstance(trace, dict)
    return RunRecord(
        request_id=str(data["request_id"]),
        trace=PathTrace(
            branch=trace["branch"],
            retry_cycles=int(trace["retry_cycles"]),
            nodes=tuple(trace["nodes"]),
        ),
    )


def write_records(records: list[RunRecord], path: Path) -> None:
    """JSONL-артефакт прогона (контракт №3) — его читают потребители следующих итераций."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(_to_dict(r), ensure_ascii=False, sort_keys=True) for r in records)
    path.write_text("\n".join(lines) + "\n")


def read_records(path: Path) -> list[RunRecord]:
    return [_from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
