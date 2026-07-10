"""RunRecord — единый артефакт батч-прогона (контракт №3): один раннер в workflow-слое гонит
пачку через граф и отдаёт `{request_id, path_trace, per-node usage/latency}`. CI-таблица
(iter 2), Prometheus (iter 4), Phoenix (iter 5), Prefect (iter 7) читают ЕГО, а не гоняют граф
каждый по-своему. Новых полей PathTrace нет — usage/latency живут рядом, в node_stats.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.domain.path import PathTrace
from app.domain.schemas import NodeStat, PARequest
from app.llm import tracing
from app.workflow.graph import run_pa_request


@dataclass(frozen=True)
class RunRecord:
    request_id: str
    trace: PathTrace  # источник истины golden/CI-ассертов (правило 6)
    node_stats: tuple[NodeStat, ...]  # per-node usage/latency (контракт №3), не ассертится
    budget_escalated: bool = False  # escalate по исчерпанию бюджета (iter 4) → счётчик метрик


async def run_batch(requests: list[PARequest], *, settings: Settings) -> list[RunRecord]:
    """Прогнать пачку через граф (в replay — $0) → RunRecord на заявку, в порядке пачки."""
    results = await asyncio.gather(*(run_pa_request(r, settings=settings) for r in requests))
    tracing.flush(settings)  # дожать батч-экспортер Langfuse на границе прогона (no-op без ключей)
    return [
        RunRecord(
            request_id=request.id,
            trace=result.trace,
            node_stats=result.node_stats,
            budget_escalated=result.budget_escalated,
        )
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
        "node_stats": [
            {
                "node": s.node,
                "attempt": s.attempt,
                "tier": s.tier,
                "usage": s.usage,
                "latency_ms": s.latency_ms,
            }
            for s in record.node_stats
        ],
        "budget_escalated": record.budget_escalated,
    }


def _from_dict(data: dict[str, object]) -> RunRecord:
    trace = data["path_trace"]
    assert isinstance(trace, dict)
    stats = data["node_stats"]
    assert isinstance(stats, list)
    return RunRecord(
        request_id=str(data["request_id"]),
        trace=PathTrace(
            branch=trace["branch"],
            retry_cycles=int(trace["retry_cycles"]),
            nodes=tuple(trace["nodes"]),
        ),
        node_stats=tuple(
            NodeStat(
                node=str(s["node"]),
                attempt=int(s["attempt"]),
                tier=str(s["tier"]),
                usage=s["usage"],
                latency_ms=float(s["latency_ms"]),
            )
            for s in stats
        ),
        budget_escalated=bool(data.get("budget_escalated", False)),
    )


def records_path(settings: Settings) -> Path:
    """Конвенция имени артефакта прогона (контракт №3): runs/<cassette_set>.jsonl — одно место
    вместо копий в каждом транспорте (CLI, path-gate, metrics-push; Phoenix в iter 5)."""
    return settings.runs_dir / f"{settings.cassette_set}.jsonl"


def write_records(records: list[RunRecord], path: Path) -> None:
    """JSONL-артефакт прогона (контракт №3) — его читают потребители следующих итераций."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(_to_dict(r), ensure_ascii=False, sort_keys=True) for r in records)
    path.write_text("\n".join(lines) + "\n")


def read_records(path: Path) -> list[RunRecord]:
    return [_from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
