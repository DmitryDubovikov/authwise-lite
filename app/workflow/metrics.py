"""Per-node агрегаты батч-прогона для Prometheus (iter 4). Читаем RunRecord (контракт №3 —
метрики не гоняют граф), cost — через workflow/costs.py → domain cost_usd (контракт №5).
Чистая свёртка: I/O (чтение JSONL, push в Pushgateway) живёт в scripts/metrics_push.py.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.config import Settings
from app.domain.schemas import NodeStat
from app.workflow.costs import stat_cost_usd
from app.workflow.runner import RunRecord


@dataclass(frozen=True)
class NodeAggregate:
    calls: int
    latency_ms_avg: float
    cost_usd: float


@dataclass(frozen=True)
class BatchAggregate:
    runs: int
    budget_escalations: int
    nodes: dict[str, NodeAggregate]


def aggregate_batch(records: Iterable[RunRecord], *, settings: Settings) -> BatchAggregate:
    by_node: dict[str, list[NodeStat]] = defaultdict(list)
    runs = 0
    budget_escalations = 0
    for record in records:
        runs += 1
        budget_escalations += record.budget_escalated
        for stat in record.node_stats:
            by_node[stat.node].append(stat)
    nodes = {
        node: NodeAggregate(
            calls=len(stats),
            latency_ms_avg=sum(s.latency_ms for s in stats) / len(stats),
            cost_usd=sum(stat_cost_usd(s, settings) or 0.0 for s in stats),
        )
        for node, stats in by_node.items()
    }
    return BatchAggregate(runs=runs, budget_escalations=budget_escalations, nodes=nodes)
