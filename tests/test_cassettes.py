"""Кассеты: раскладка по контракту №4, usage в формате, replay-miss — громкая ошибка."""

from pathlib import Path

import pytest

from app.llm import cassettes


def test_path_layout_by_set_and_key(tmp_path: Path) -> None:
    path = cassettes.cassette_path(tmp_path, "base", "PA-base-007", "policy-check", 2)
    assert path == tmp_path / "base" / "PA-base-007__policy-check__a2.json"


def test_roundtrip_preserves_usage(tmp_path: Path) -> None:
    path = tmp_path / "smoke" / "c.json"
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    cassettes.save(path, model="gpt-4.1-nano-2025-04-14", content="{}", usage=usage)
    loaded = cassettes.load(path)
    assert loaded.usage == usage
    assert loaded.model == "gpt-4.1-nano-2025-04-14"


def test_replay_miss_is_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="replay никогда не бьёт в сеть"):
        cassettes.load(tmp_path / "smoke" / "absent.json")
