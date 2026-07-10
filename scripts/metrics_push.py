"""Тонкий транспорт: RunRecord JSONL → Pushgateway (решение спеки 04: прогон — короткоживущий
батч, pull-модели Prometheus скрейпить некого; Pushgateway — официальный компаньон для
батч-джобов). Агрегаты — app/workflow/metrics.py; cost — из usage кассет через domain cost_usd.

Идемпотентно: push замещает группу job=authwise-batch целиком (last-write) — повторный прогон
не плодит серий. Gauge, не Counter: значения — снапшот последнего батча, не монотонный счётчик.
"""

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from app.config import get_settings
from app.workflow.metrics import aggregate_batch
from app.workflow.runner import read_records, records_path


def main() -> None:
    settings = get_settings()
    path = records_path(settings)
    if not path.exists():
        raise SystemExit(
            f"нет артефакта прогона {path} — сначала прогон, пишущий RunRecord "
            "(make replay-base / budget-demo / path-gate)"
        )
    batch = aggregate_batch(read_records(path), settings=settings)

    registry = CollectorRegistry()
    labels = ["node", "set"]
    calls = Gauge("aw_node_calls", "LLM-вызовов на ноду за батч", labels, registry=registry)
    avg = Gauge("aw_node_latency_ms_avg", "средняя латентность ноды, ms", labels, registry=registry)
    cost = Gauge("aw_node_cost_usd", "суммарный cost ноды за батч, USD", labels, registry=registry)
    runs = Gauge("aw_runs", "заявок в батче", ["set"], registry=registry)
    escalations = Gauge(
        "aw_budget_escalations",
        "ранов, ушедших в escalate по исчерпанию бюджета (FinOps guardrail)",
        ["set"],
        registry=registry,
    )

    cassette_set = settings.cassette_set
    for node, agg in sorted(batch.nodes.items()):
        calls.labels(node=node, set=cassette_set).set(agg.calls)
        avg.labels(node=node, set=cassette_set).set(agg.latency_ms_avg)
        cost.labels(node=node, set=cassette_set).set(agg.cost_usd)
        print(
            f"{node}: calls={agg.calls} latency_avg={agg.latency_ms_avg:.3f}ms "
            f"cost=${agg.cost_usd:.6f}"
        )
    runs.labels(set=cassette_set).set(batch.runs)
    escalations.labels(set=cassette_set).set(batch.budget_escalations)
    print(f"runs={batch.runs} budget_escalations={batch.budget_escalations}")

    # grouping_key=set: пуш замещает группу только СВОЕГО набора — сеты сосуществуют,
    # как и обещает метка set на сериях
    push_to_gateway(
        settings.pushgateway_url,
        job="authwise-batch",
        grouping_key={"set": cassette_set},
        registry=registry,
    )
    print(f"→ pushed в {settings.pushgateway_url} (job=authwise-batch, set={cassette_set})")


if __name__ == "__main__":
    main()
