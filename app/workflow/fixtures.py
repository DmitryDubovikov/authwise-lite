"""Загрузка фикстур из JSONL (контракт №1: один формат для всех пачек)."""

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.domain.schemas import PARequest

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    return [
        model.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]


def load_requests(path: Path) -> list[PARequest]:
    return load_jsonl(path, PARequest)
