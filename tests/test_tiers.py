"""Пин-гейт снапшотов и цены токенов (контракт №5)."""

from pathlib import Path

import pytest
from conftest import ROOT

from app.llm.tiers import load_tiers, resolve_tier


def test_project_tiers_pass_pin_gate() -> None:
    tiers = load_tiers(ROOT / "llm-tiers.yaml")
    assert set(tiers) == {"cheap", "mid", "smart"}
    for tier in tiers.values():
        assert tier.input_per_1m > 0 and tier.output_per_1m > 0


def test_floating_alias_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "tiers.yaml"
    bad.write_text(
        "tiers:\n  cheap:\n    model: gpt-4.1-nano\n    input_per_1m: 0.1\n    output_per_1m: 0.4\n"
    )
    with pytest.raises(ValueError, match="пин-гейт"):
        load_tiers(bad)


def test_unknown_tier_rejected() -> None:
    with pytest.raises(KeyError, match="неизвестный тир"):
        resolve_tier("free", ROOT / "llm-tiers.yaml")
