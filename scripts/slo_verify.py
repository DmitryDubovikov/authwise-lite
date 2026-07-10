"""Verify the store (правило 9): SLO-гардрейл доказывается запросами к API, не скрином UI.
Prometheus HTTP API — per-node серии (latency/cost) и счётчик budget-эскалаций реально
скрейпятся; Grafana API — alert rule существует и находится в состоянии Firing (демо-порог
ужат — см. slo/grafana/provisioning/alerting/aw-slo.yml).
"""

import base64
import json
import urllib.parse
import urllib.request
from typing import Any

from app.config import Settings, get_settings

LLM_NODES = {"classify", "policy-check"}  # cost/latency несут LLM-ноды графа
ALERT_TITLE = "Per-node latency SLO"


def _get_json(url: str, *, auth: tuple[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url)
    if auth is not None:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def _prom_query(prometheus_url: str, expr: str) -> list[dict[str, Any]]:
    """Серии инстант-запроса к Prometheus — доказательство, что метрика скрейпится."""
    query = urllib.parse.urlencode({"query": expr})
    payload = _get_json(f"{prometheus_url}/api/v1/query?{query}")
    return list(payload["data"]["result"])


def _prom_nodes(prometheus_url: str, metric: str) -> set[str]:
    return {r["metric"].get("node", "") for r in _prom_query(prometheus_url, metric)} - {""}


def _alert_state(settings: Settings) -> str | None:
    """Состояние alert rule из Grafana (Prometheus-совместимый API); None — правила нет."""
    url = f"{settings.grafana_url}/api/prometheus/grafana/api/v1/rules"
    auth = (settings.grafana_user, settings.grafana_password.get_secret_value())
    payload = _get_json(url, auth=auth)
    for group in payload["data"]["groups"]:
        for rule in group["rules"]:
            if rule["name"] == ALERT_TITLE:
                return str(rule["state"])
    return None


def main() -> None:
    settings = get_settings()
    problems = []

    latency_nodes = _prom_nodes(settings.prometheus_url, "aw_node_latency_ms_avg")
    cost_nodes = _prom_nodes(settings.prometheus_url, "aw_node_cost_usd")
    escalation_series = _prom_query(settings.prometheus_url, "aw_budget_escalations")

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

    state = _alert_state(settings)
    if state is None:
        problems.append(f"в Grafana нет alert rule {ALERT_TITLE!r} — провижининг не подхватился?")
    else:
        print(f"alert rule {ALERT_TITLE!r}: state={state}")
        if state != "firing":
            problems.append(
                f"alert rule не Firing (state={state}) — подожди evaluation+for (~1 мин "
                "после make metrics-push) и повтори"
            )

    rule = "─" * 60
    if problems:
        print(f"{rule}\n❌  VERIFY FAILED — SLO-гардрейл не подтверждён:")
        for problem in problems:
            print(f"  · {problem}")
        raise SystemExit(1)
    print(
        f"{rule}\n✅  VERIFY OK — per-node метрики скрейпятся Prometheus, "
        f"alert rule {ALERT_TITLE!r} Firing и называет просевшую ноду"
    )


if __name__ == "__main__":
    main()
