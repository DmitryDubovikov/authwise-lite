"""Path-distribution drift (iter 5): доли веток и PSI — чистые функции, без I/O.

PSI (Population Stability Index) — отраслевая метрика сдвига распределения между эталонной
(reference) и текущей (primary) выборкой: Σ (pᵢ − rᵢ) · ln(pᵢ / rᵢ) по бинам. Конвенция
порогов: <0.1 — сдвига нет, 0.1–0.2 — умеренный, >0.2 — значимый. Бины здесь — три терминала
контракта №2, поэтому нулевая доля реальна (ветка может не встретиться в пачке вовсе) и
сглаживается ε: появившаяся ветка даёт большой, но конечный вклад.
"""

import math
from collections import Counter
from collections.abc import Iterable
from typing import get_args

from app.domain.path import Branch

BRANCHES: tuple[Branch, ...] = get_args(Branch)

# Отраслевая конвенция порога «значимого» сдвига; алерт-порог продублирован в Grafana rule
# (slo/grafana/provisioning/alerting/aw-drift.yml) — правь синхронно.
PSI_DRIFT_THRESHOLD = 0.2

_EPSILON = 1e-4  # сглаживание нулевых долей — стандартный приём PSI для пустых бинов


def branch_distribution(branches: Iterable[Branch]) -> dict[Branch, float]:
    """Доли веток по фиксированным терминалам (все три ключа присутствуют всегда)."""
    counts = Counter(branches)
    total = counts.total()
    if total == 0:
        raise ValueError("распределение веток по пустой выборке не определено")
    return {branch: counts[branch] / total for branch in BRANCHES}


def psi(reference: dict[Branch, float], primary: dict[Branch, float]) -> float:
    """PSI между двумя распределениями долей веток (ключи — BRANCHES, суммы ~1)."""
    value = 0.0
    for branch in BRANCHES:
        ref = max(reference[branch], _EPSILON)
        cur = max(primary[branch], _EPSILON)
        value += (cur - ref) * math.log(cur / ref)
    return value
