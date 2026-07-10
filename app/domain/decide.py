"""Ветвление decide — детерминированная чистая функция над структурированным выходом
policy-check и остатком бюджета рана (правило 3, контракт №2): retry-loop продолжается только
при положительном остатке, исчерпание бюджета — маршрут `escalate`, а не исключение.
"""

from typing import Literal

from app.domain.schemas import PolicyCheckResult

# Терминалы + "retry" (ещё одна прокрутка retry-loop; в PathTrace.branch не попадает)
Decision = Literal["approve", "escalate", "retry", "request-info"]


def decide(
    policy: PolicyCheckResult,
    *,
    retry_cycles: int,
    retry_limit: int,
    budget_remaining_usd: float,
) -> Decision:
    if policy.status == "sufficient":
        return "approve"
    if policy.status == "out_of_policy":
        return "escalate"
    # missing_info: до-запрос, пока не исчерпаны ни потолок N, ни бюджет рана. Исчерпанный
    # потолок — терминальный request-info («документы так и не получены»); исчерпанный
    # бюджет — escalate (человек дешевле ещё одного LLM-цикла).
    if retry_cycles >= retry_limit:
        return "request-info"
    return "retry" if budget_remaining_usd > 0 else "escalate"
