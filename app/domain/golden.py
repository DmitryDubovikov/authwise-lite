"""Golden-разметка траекторий (правило 3): запись = список допустимых путей, ассерт —
membership по (branch, retry_cycles). Exact-match по одной эталонной траектории хрупок
(отраслевая практика — multiple reference trajectories), а квота ≥80% singleton не даёт
разметке размякнуть: джокеры — только объективно неоднозначные заявки, поимённо и с
объяснением. Чистые функции + схемы, без I/O (правило 6).
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field, model_validator

from app.domain.path import Branch, PathTrace

SINGLETON_QUOTA = 0.8  # ≥80% записей — единственный допустимый путь (= exact match)


class AllowedPath(BaseModel):
    """Один допустимый путь: терминальная ветка + число прокруток retry-loop (контракт №2)."""

    branch: Branch
    retry_cycles: int = Field(ge=0)


class GoldenRecord(BaseModel):
    """Разметка одной заявки. >1 допустимого пути — «джокер»: note обязан объяснять,
    почему заявка объективно неоднозначна."""

    request_id: str
    allowed_paths: list[AllowedPath] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _honest_markup(self) -> "GoldenRecord":
        pairs = [(p.branch, p.retry_cycles) for p in self.allowed_paths]
        if len(pairs) != len(set(pairs)):
            raise ValueError(f"{self.request_id}: дубли в allowed_paths")
        if not self.is_singleton and not self.note:
            raise ValueError(f"{self.request_id}: джокер без note — неоднозначность не объяснена")
        return self

    @property
    def is_singleton(self) -> bool:
        return len(self.allowed_paths) == 1


def path_allowed(trace: PathTrace, record: GoldenRecord) -> bool:
    """Membership-ассерт: фактический путь входит в список допустимых."""
    return any(
        p.branch == trace.branch and p.retry_cycles == trace.retry_cycles
        for p in record.allowed_paths
    )


def singleton_share(records: Sequence[GoldenRecord]) -> float:
    """Доля singleton-записей; пустой набор — 0.0 (квота ≥80% на нём честно провалится)."""
    if not records:
        return 0.0
    return sum(r.is_singleton for r in records) / len(records)
