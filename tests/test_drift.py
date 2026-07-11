"""Path-distribution drift (iter 5): доли веток и PSI — чистые domain-функции."""

import math

import pytest

from app.domain.drift import BRANCHES, PSI_DRIFT_THRESHOLD, branch_distribution, psi


def test_branch_distribution_has_all_terminals() -> None:
    # все три терминала контракта №2 присутствуют всегда — нулевой бин остаётся видимым
    dist = branch_distribution(["approve", "approve", "escalate"])
    assert set(dist) == set(BRANCHES)
    assert dist["approve"] == pytest.approx(2 / 3)
    assert dist["escalate"] == pytest.approx(1 / 3)
    assert dist["request-info"] == 0.0


def test_branch_distribution_rejects_empty() -> None:
    with pytest.raises(ValueError):
        branch_distribution([])


def test_psi_identical_distributions_is_zero() -> None:
    dist = branch_distribution(["approve", "escalate", "request-info"])
    assert psi(dist, dist) == pytest.approx(0.0)


def test_psi_is_symmetric() -> None:
    reference = branch_distribution(["approve"] * 3 + ["escalate"])
    primary = branch_distribution(["approve", "escalate", "escalate", "request-info"])
    assert psi(reference, primary) == pytest.approx(psi(primary, reference))


def test_psi_known_value() -> None:
    # ручной расчёт по формуле Σ (p−r)·ln(p/r) без сглаживания (нулевых бинов нет):
    # (−0.25)·ln(½) + 0 + 0.25·ln(2) = 0.5·ln 2
    reference = {"approve": 0.5, "request-info": 0.25, "escalate": 0.25}
    primary = {"approve": 0.25, "request-info": 0.25, "escalate": 0.5}
    assert psi(reference, primary) == pytest.approx(0.5 * math.log(2))


def test_psi_zero_bin_is_finite_and_significant() -> None:
    # ветка, которой в reference не было вовсе, даёт большой, но конечный вклад —
    # и уводит PSI за алерт-порог
    reference = {"approve": 0.75, "request-info": 0.0, "escalate": 0.25}
    primary = {"approve": 0.4, "request-info": 0.2, "escalate": 0.4}
    value = psi(reference, primary)
    assert value != float("inf")
    assert value > PSI_DRIFT_THRESHOLD


def test_psi_small_shift_stays_under_threshold() -> None:
    reference = {"approve": 0.72, "request-info": 0.03, "escalate": 0.25}
    primary = {"approve": 0.70, "request-info": 0.05, "escalate": 0.25}
    assert psi(reference, primary) < PSI_DRIFT_THRESHOLD
