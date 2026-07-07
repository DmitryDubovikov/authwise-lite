"""Кассеты record/replay. Ключ — (request_id, node, attempt), НЕ хэш содержимого запроса
(контракт №4): смена промпта не рвёт replay — это структурное решение ловушки демо-регрессии
iter 2. Наборы живут рядом в cassettes/<set>/, выбор — env AW_CASSETTE_SET.
Формат обязан хранить usage ответа — per-node cost в iter 3–4 считается из него.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Cassette:
    model: str
    content: str
    usage: dict[str, Any] | None


def cassette_path(root: Path, set_name: str, request_id: str, node: str, attempt: int) -> Path:
    return root / set_name / f"{request_id}__{node}__a{attempt}.json"


def load(path: Path) -> Cassette:
    if not path.exists():
        raise FileNotFoundError(
            f"нет кассеты {path}: replay никогда не бьёт в сеть — сгенерируй авторскую "
            "(make author-cassettes) или запиши явно (AW_LLM_MODE=record, деньги)"
        )
    data = json.loads(path.read_text())
    response = data["response"]
    return Cassette(model=data["model"], content=response["content"], usage=response.get("usage"))


def save(
    path: Path,
    *,
    model: str,
    content: str,
    usage: dict[str, Any] | None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """`messages` — провенанс live-записи; авторские кассеты пишутся без него."""
    payload: dict[str, Any] = {"model": model, "response": {"content": content, "usage": usage}}
    if messages is not None:
        payload["messages"] = messages
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
