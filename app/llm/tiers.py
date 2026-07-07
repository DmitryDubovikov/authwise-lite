"""Тиры моделей: пин-гейт снапшотов (перенос triagewise) + цены токенов (контракт №5)."""

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


class Tier(BaseModel):
    model: str
    input_per_1m: float  # USD за 1M input-токенов
    output_per_1m: float  # USD за 1M output-токенов


@lru_cache
def load_tiers(path: Path) -> dict[str, Tier]:
    raw = yaml.safe_load(path.read_text())
    tiers = {name: Tier.model_validate(spec) for name, spec in raw["tiers"].items()}
    for name, tier in tiers.items():
        if not _SNAPSHOT_RE.search(tier.model):
            raise ValueError(
                f"тир {name!r}: модель {tier.model!r} не является датированным снапшотом "
                "(пин-гейт: имя обязано матчить -YYYY-MM-DD$)"
            )
    return tiers


def resolve_model(tier: str, tiers_path: Path) -> str:
    tiers = load_tiers(tiers_path)
    if tier not in tiers:
        raise KeyError(f"неизвестный тир {tier!r}; доступны: {sorted(tiers)}")
    return tiers[tier].model
