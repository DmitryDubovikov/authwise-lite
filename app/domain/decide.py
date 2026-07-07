"""Ветвление decide — детерминированная чистая функция над структурированным выходом
policy-check (правило 3). С iter 4 сюда добавится остаток бюджета рана — новых веток не будет.
"""

from typing import Literal

from app.domain.schemas import PolicyCheckResult

# Терминалы + "retry" (ещё одна прокрутка retry-loop; в PathTrace.branch не попадает)
Decision = Literal["approve", "escalate", "retry", "request-info"]


def decide(policy: PolicyCheckResult, *, retry_cycles: int, retry_limit: int) -> Decision:
    if policy.status == "sufficient":
        return "approve"
    if policy.status == "out_of_policy":
        return "escalate"
    # missing_info: до-запрос, пока не исчерпан потолок N; дальше — терминальный request-info
    return "retry" if retry_cycles < retry_limit else "request-info"
