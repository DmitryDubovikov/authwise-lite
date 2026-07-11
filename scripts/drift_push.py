"""Тонкий транспорт path-drift (iter 5): два RunRecord-артефакта (контракт №3 — граф заново не
гоняется) → доли веток reference/primary + PSI → Pushgateway. Доли и PSI — чистый domain
(app/domain/drift.py); рельсы пуша — iter 4 (батч короткоживущий, pull-модели скрейпить некого).

Идемпотентно: push замещает группу job=authwise-drift целиком (last-write) — повторный прогон
не плодит серий. Gauge: снапшот последнего сравнения, не монотонный счётчик.
"""

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from app.config import Settings, get_settings
from app.domain.drift import BRANCHES, PSI_DRIFT_THRESHOLD, branch_distribution, psi
from app.domain.path import Branch
from app.workflow.runner import read_records, records_path


def _distribution(settings: Settings, cassette_set: str) -> dict[Branch, float]:
    path = records_path(settings, cassette_set=cassette_set)
    if not path.exists():
        raise SystemExit(
            f"нет артефакта прогона {path} — сначала прогон, пишущий RunRecord "
            f"(make replay-{cassette_set})"
        )
    return branch_distribution(record.trace.branch for record in read_records(path))


def main() -> None:
    settings = get_settings()
    reference_set, primary_set = settings.drift_reference_set, settings.drift_primary_set
    reference = _distribution(settings, reference_set)
    primary = _distribution(settings, primary_set)
    drift = psi(reference, primary)

    registry = CollectorRegistry()
    # Лейбл role — стабильная семантика (reference/primary), её пинят панели Grafana;
    # set — информационное имя пачки: ручки AW_DRIFT_*_SET крутятся без правки дашборда
    share = Gauge(
        "aw_branch_share",
        "доля терминальной ветки в батче пачки (role: reference — эталон, primary — текущая)",
        ["role", "set", "branch"],
        registry=registry,
    )
    psi_gauge = Gauge(
        "aw_path_drift_psi",
        "PSI распределения веток: primary против reference (одна серия сравнения)",
        registry=registry,
    )
    for role, cassette_set, dist in (
        ("reference", reference_set, reference),
        ("primary", primary_set, primary),
    ):
        for branch in BRANCHES:
            share.labels(role=role, set=cassette_set, branch=branch).set(dist[branch])
    psi_gauge.set(drift)

    # stdout-таблица — страховка витрины и глазная проверка до Grafana
    print(f"{'branch':<14}{reference_set:>10}{primary_set:>10}")
    for branch in BRANCHES:
        print(f"{branch:<14}{reference[branch]:>10.1%}{primary[branch]:>10.1%}")
    verdict = "значимый (> порога)" if drift > PSI_DRIFT_THRESHOLD else "ниже порога"
    print(f"PSI({primary_set} vs {reference_set}) = {drift:.3f} — {verdict} {PSI_DRIFT_THRESHOLD}")

    push_to_gateway(settings.pushgateway_url, job="authwise-drift", registry=registry)
    print(f"→ pushed в {settings.pushgateway_url} (job=authwise-drift)")


if __name__ == "__main__":
    main()
