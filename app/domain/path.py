"""PathTrace — first-class domain-объект, единственный источник истины для golden/CI-ассертов
(правило 6: OTel-спаны — только наблюдаемость). Схема заморожена: {branch, retry_cycles, nodes}.
"""

from dataclasses import dataclass
from typing import Literal

# Три терминала (контракт №2); терминальный request-info = «недостающие документы
# не получены после N до-запросов».
Branch = Literal["approve", "request-info", "escalate"]


@dataclass(frozen=True)
class PathTrace:
    branch: Branch
    retry_cycles: int  # число прокруток retry-loop до терминала
    nodes: tuple[str, ...]  # информационное поле (витрина, Langfuse) — в golden/CI не ассертится


def render_path(trace: PathTrace) -> str:
    """Витринная строка пути: `classify → policy-check → request-info ↻2 → approve`."""
    core = "classify → policy-check"
    if trace.retry_cycles:
        core += f" → request-info ↻{trace.retry_cycles}"
        if trace.branch == "request-info":  # терминал и есть request-info — не задваиваем
            return core
    return f"{core} → {trace.branch}"
