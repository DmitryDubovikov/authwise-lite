"""Единственный шлюз к env: все переменные — через Settings с префиксом AW_ (контракт №7)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent

LLMMode = Literal["replay", "record", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AW_", env_file=".env", extra="ignore")

    # replay = $0 и дефолт, никогда не бьёт в сеть; record/live — деньги (правило 4)
    llm_mode: LLMMode = "replay"
    cassette_set: str = "smoke"  # cassettes/<set>/ — контракт №4
    retry_limit: int = 2  # потолок retry-цикла N (контракт №2)
    tier_classify: str = "cheap"
    tier_policy_check: str = "cheap"

    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None

    tiers_path: Path = _ROOT / "llm-tiers.yaml"
    cassettes_dir: Path = _ROOT / "cassettes"
    # 5051: 5050 занят MLflow сиблинга triagewise-lite (см. docker-compose.yml)
    mlflow_tracking_uri: str = "http://localhost:5051"


@lru_cache
def get_settings() -> Settings:
    return Settings()
