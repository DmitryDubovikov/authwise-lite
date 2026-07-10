"""Общее для тестов: корень репозитория + офлайн-Settings для replay-прогонов ($0)."""

from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent


def replay_settings(cassette_set: str) -> Settings:
    """Офлайн-скелет Settings: значащие поля явными аргументами, чтобы env/.env не влияли на
    тест (replay=$0, никогда не бьёт в сеть). Меняется только набор кассет."""
    return Settings(
        llm_mode="replay",
        cassette_set=cassette_set,
        retry_limit=2,
        tier_classify="cheap",
        tier_policy_check="cheap",
        cassettes_dir=ROOT / "cassettes",
        tiers_path=ROOT / "llm-tiers.yaml",
        fixtures_dir=ROOT / "fixtures",
    )
