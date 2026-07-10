"""Схемы domain-слоя: заявка-фикстура, структурированные выходы LLM-нод и per-node
статистика LLM-вызова (контракт №3). Без I/O."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class PARequest(BaseModel):
    """Заявка-фикстура (контракт №1): JSONL {"id": "PA-<pack>-<NNN>", "text", "meta"}."""

    id: str
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def supplemental(self) -> list[str]:
        """Документы, которые заявитель может дослать по request-info (по одному за цикл)."""
        return list(self.meta.get("supplemental", []))


class Classification(BaseModel):
    """Структурированный выход ноды classify."""

    case_type: Literal["imaging", "medication", "dme", "procedure", "other"]
    urgency: Literal["routine", "urgent"]


class PolicyCheckResult(BaseModel):
    """Структурированный выход ноды policy-check; ветвление decide — функция над ним."""

    status: Literal["sufficient", "missing_info", "out_of_policy"]
    missing: list[str] = Field(default_factory=list)
    rationale: str = ""


@dataclass(frozen=True)
class NodeStat:
    """Per-node usage/latency LLM-вызова (контракт №3): наблюдаемость, в golden/CI не ассертится."""

    node: str
    attempt: int
    tier: str  # тир фиксируется в момент вызова — cost прогона не переоценивается текущим env
    usage: dict[str, Any] | None
    latency_ms: float


def json_object(raw: str) -> str:
    """Вырезает JSON-объект из сырого ответа LLM (терпит code-fence и преамбулу)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"в ответе LLM нет JSON-объекта: {raw!r}")
    return raw[start : end + 1]


def parse_classification(raw: str) -> Classification:
    return Classification.model_validate_json(json_object(raw))


def parse_policy_check(raw: str) -> PolicyCheckResult:
    return PolicyCheckResult.model_validate_json(json_object(raw))
