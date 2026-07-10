"""Per-node агрегаты батча для Prometheus (iter 4): свёртка RunRecord → NodeAggregate;
cost — через одну domain-функцию (контракт №5), цены cheap-тира из llm-tiers.yaml.
"""

import pytest
from conftest import replay_settings

from app.domain.path import PathTrace
from app.domain.schemas import NodeStat
from app.workflow.costs import spent_usd
from app.workflow.metrics import aggregate_batch
from app.workflow.runner import RunRecord


def _stat(node: str, attempt: int, prompt: int, completion: int, latency: float) -> NodeStat:
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    return NodeStat(node=node, attempt=attempt, tier="cheap", usage=usage, latency_ms=latency)


RECORDS = [
    RunRecord(
        request_id="PA-x-001",
        trace=PathTrace(branch="approve", retry_cycles=0, nodes=()),
        node_stats=(_stat("classify", 1, 100, 10, 2.0), _stat("policy-check", 1, 200, 20, 4.0)),
    ),
    RunRecord(
        request_id="PA-x-002",
        trace=PathTrace(branch="escalate", retry_cycles=1, nodes=()),
        node_stats=(
            _stat("classify", 1, 100, 10, 6.0),
            _stat("policy-check", 1, 200, 20, 8.0),
            _stat("policy-check", 2, 300, 30, 10.0),
        ),
        budget_escalated=True,
    ),
]


def test_aggregate_batch_per_node() -> None:
    batch = aggregate_batch(RECORDS, settings=replay_settings("base"))
    assert batch.runs == 2
    assert batch.budget_escalations == 1
    assert set(batch.nodes) == {"classify", "policy-check"}

    classify = batch.nodes["classify"]
    assert classify.calls == 2
    assert classify.latency_ms_avg == pytest.approx(4.0)
    # cheap-тир: $0.10/1M input, $0.40/1M output → 2×(100×0.10 + 10×0.40)/1e6
    assert classify.cost_usd == pytest.approx(2 * (100 * 0.10 + 10 * 0.40) / 1_000_000)

    policy = batch.nodes["policy-check"]
    assert policy.calls == 3
    assert policy.latency_ms_avg == pytest.approx((4.0 + 8.0 + 10.0) / 3)


def test_spent_usd_ignores_missing_usage() -> None:
    stats = [
        _stat("classify", 1, 100, 10, 1.0),
        NodeStat(node="policy-check", attempt=1, tier="cheap", usage=None, latency_ms=1.0),
    ]
    settings = replay_settings("base")
    assert spent_usd(stats, settings) == pytest.approx((100 * 0.10 + 10 * 0.40) / 1_000_000)
