"""Стоимость LLM-вызовов рана: тир зафиксирован в NodeStat в момент вызова (cost прошлого
прогона не переоценивается текущим env), цены тира → cost_usd (контракт №5 — одна функция
стоимости в domain, здесь только wiring). Потребители: budget-гейт decide_node (iter 4) и
Prometheus-агрегаты (app/workflow/metrics.py).
"""

from collections.abc import Iterable

from app.config import Settings
from app.domain.cost import cost_usd
from app.domain.schemas import NodeStat
from app.llm.tiers import resolve_tier


def stat_cost_usd(stat: NodeStat, settings: Settings) -> float | None:
    """Стоимость одного LLM-вызова ноды; None — ответ без usage (нечего атрибутировать)."""
    tier = resolve_tier(stat.tier, settings.tiers_path)
    return cost_usd(stat.usage, input_per_1m=tier.input_per_1m, output_per_1m=tier.output_per_1m)


def spent_usd(stats: Iterable[NodeStat], settings: Settings) -> float:
    """Потрачено раном к текущему моменту — из него decide_node выводит остаток бюджета."""
    return sum(stat_cost_usd(stat, settings) or 0.0 for stat in stats)
