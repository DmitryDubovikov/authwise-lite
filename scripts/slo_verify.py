"""Verify the store (правило 9): SLO-гардрейл доказывается запросами к API, не скрином UI.
Prometheus HTTP API — per-node серии (latency/cost) и счётчик budget-эскалаций реально
скрейпятся; Grafana API — alert rule существует и находится в состоянии Firing (демо-порог
ужат — см. slo/grafana/provisioning/alerting/aw-slo.yml).
"""

from app.config import get_settings
from scripts.verify_http import check_alert_firing, prom_query, report

LLM_NODES = {"classify", "policy-check"}  # cost/latency несут LLM-ноды графа
ALERT_TITLE = "Per-node latency SLO"


def _prom_nodes(prometheus_url: str, metric: str) -> set[str]:
    return {r["metric"].get("node", "") for r in prom_query(prometheus_url, metric)} - {""}


def main() -> None:
    settings = get_settings()
    problems = []

    latency_nodes = _prom_nodes(settings.prometheus_url, "aw_node_latency_ms_avg")
    cost_nodes = _prom_nodes(settings.prometheus_url, "aw_node_cost_usd")
    escalation_series = prom_query(settings.prometheus_url, "aw_budget_escalations")

    print(f"latency-серии по нодам: {sorted(latency_nodes) or '—'}")
    print(f"cost-серии по нодам: {sorted(cost_nodes) or '—'}")
    for series in escalation_series:
        print(f"budget-эскалаций (set={series['metric'].get('set')}): {series['value'][1]}")

    if missing := LLM_NODES - latency_nodes:
        problems.append(
            f"в Prometheus нет latency-серий нод {sorted(missing)} — make metrics-push?"
        )
    if missing := LLM_NODES - cost_nodes:
        problems.append(f"в Prometheus нет cost-серий нод {sorted(missing)}")
    if not escalation_series:
        problems.append("в Prometheus нет счётчика aw_budget_escalations")

    if problem := check_alert_firing(settings, ALERT_TITLE, push_hint="make metrics-push"):
        problems.append(problem)
    report(
        problems,
        failed="SLO-гардрейл не подтверждён",
        ok=(
            "per-node метрики скрейпятся Prometheus, "
            f"alert rule {ALERT_TITLE!r} Firing и называет просевшую ноду"
        ),
    )


if __name__ == "__main__":
    main()
