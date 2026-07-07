"""Загрузка заявок-фикстур (контракт №1: JSONL, один формат для всех пачек)."""

from pathlib import Path

from app.domain.schemas import PARequest


def load_requests(path: Path) -> list[PARequest]:
    return [
        PARequest.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
