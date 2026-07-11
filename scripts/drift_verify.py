"""Verify the store (правило 9): path-drift доказывается запросами к API, не скрином UI.
Prometheus HTTP API — доли веток обеих пачек и PSI-гейдж реально скрейпятся; PSI выше
отраслевого порога (сдвиг «пострелизной» пачки настоящий, порог не ужат); Grafana API —
alert rule существует и Firing.
"""

from typing import Any

from app.config import get_settings
from app.domain.drift import BRANCHES, PSI_DRIFT_THRESHOLD
from scripts.verify_http import check_alert_firing, prom_query, report

ALERT_TITLE = "Path-distribution drift (PSI)"


def _branches_by_role(series: list[dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    """role → {"sets": имена пачек, "branches": ветки} из лейблов серий."""
    result: dict[str, dict[str, set[str]]] = {}
    for item in series:
        labels = item["metric"]
        role = result.setdefault(labels.get("role", ""), {"sets": set(), "branches": set()})
        role["sets"].add(labels.get("set", ""))
        role["branches"].add(labels.get("branch", ""))
    return result


def main() -> None:
    settings = get_settings()
    problems = []

    shares = _branches_by_role(prom_query(settings.prometheus_url, "aw_branch_share"))
    for role in ("reference", "primary"):
        found = shares.get(role, {"sets": set(), "branches": set()})
        sets, branches = ",".join(sorted(found["sets"])), found["branches"]
        print(f"aw_branch_share (role={role}, set={sets or '—'}): ветки {sorted(branches) or '—'}")
        if branches != set(BRANCHES):
            problems.append(f"в Prometheus нет полных долей веток роли {role!r} — make drift-push?")

    psi_series = prom_query(settings.prometheus_url, "aw_path_drift_psi")
    if not psi_series:
        problems.append("в Prometheus нет aw_path_drift_psi — make drift-push?")
    else:
        value = float(psi_series[0]["value"][1])
        print(f"aw_path_drift_psi = {value:.3f} (порог {PSI_DRIFT_THRESHOLD})")
        if value <= PSI_DRIFT_THRESHOLD:
            problems.append(
                f"PSI {value:.3f} не выше порога {PSI_DRIFT_THRESHOLD} — дрейф не виден "
                "(пачки перепутаны или прогнан один и тот же сет?)"
            )

    if problem := check_alert_firing(settings, ALERT_TITLE, push_hint="make drift-push"):
        problems.append(problem)
    report(
        problems,
        failed="path-drift не подтверждён",
        ok=(
            "доли веток обеих пачек скрейпятся Prometheus, PSI выше порога, "
            f"alert rule {ALERT_TITLE!r} Firing"
        ),
    )


if __name__ == "__main__":
    main()
