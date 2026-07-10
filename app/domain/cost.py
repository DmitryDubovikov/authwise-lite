"""cost_usd — единственная функция стоимости (сквозной контракт №5): cost ноды = usage × цена.
Потребители: Langfuse-generation (iter 3), Prometheus/SLO-расчёты (iter 4). Чистая функция без
I/O — цены приходят аргументами (из llm-tiers.yaml через слой llm/tiers.py).
"""

from collections.abc import Mapping
from typing import Any


def cost_usd(
    usage: Mapping[str, Any] | None, *, input_per_1m: float, output_per_1m: float
) -> float | None:
    """Стоимость LLM-вызова в USD; None — ответ без usage (нечего атрибутировать)."""
    if usage is None:
        return None
    return (
        usage.get("prompt_tokens", 0) * input_per_1m
        + usage.get("completion_tokens", 0) * output_per_1m
    ) / 1_000_000
