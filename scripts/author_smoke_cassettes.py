"""Авторские кассеты smoke-набора: $0, идемпотентно (детерминированное содержимое).

# aw-lite: авторские кассеты (usage синтетический, messages отсутствуют) → реальный record
# базовой пачки — iter 1. Формат — боевой: usage хранится, per-node cost в iter 3–4 считается.

Сценарии путей smoke-фикстуры (потолок retry N=2):
  PA-smoke-001: approve без retry
  PA-smoke-002: request-info ↻1 → approve
  PA-smoke-003: escalate (out_of_policy)
  PA-smoke-004: request-info ↻2 → терминальный request-info (документы так и не собраны)
"""

from app.config import get_settings
from app.domain.schemas import Classification, PolicyCheckResult
from app.llm import cassettes
from app.llm.tiers import resolve_model


def _classify(case_type: str) -> str:
    # содержимое строится domain-схемой — кассета валидна по построению
    return Classification.model_validate(
        {"case_type": case_type, "urgency": "routine"}
    ).model_dump_json()


def _policy(status: str, missing: list[str] | None = None, rationale: str = "") -> str:
    return PolicyCheckResult.model_validate(
        {"status": status, "missing": missing or [], "rationale": rationale}
    ).model_dump_json()


# (request_id, node, attempt) -> (content, usage) — ключ кассеты по контракту №4
CASSETTES: dict[tuple[str, str, int], tuple[str, dict[str, int]]] = {
    ("PA-smoke-001", "classify", 1): (
        _classify("imaging"),
        {"prompt_tokens": 168, "completion_tokens": 14, "total_tokens": 182},
    ),
    ("PA-smoke-001", "policy-check", 1): (
        _policy(
            "sufficient",
            rationale="Order, conservative therapy and neuro exam meet MRI criteria.",
        ),
        {"prompt_tokens": 291, "completion_tokens": 38, "total_tokens": 329},
    ),
    ("PA-smoke-002", "classify", 1): (
        _classify("medication"),
        {"prompt_tokens": 152, "completion_tokens": 14, "total_tokens": 166},
    ),
    ("PA-smoke-002", "policy-check", 1): (
        _policy(
            "missing_info",
            missing=["Recent HbA1c lab results"],
            rationale="GLP-1 coverage requires a current HbA1c value.",
        ),
        {"prompt_tokens": 268, "completion_tokens": 41, "total_tokens": 309},
    ),
    ("PA-smoke-002", "policy-check", 2): (
        _policy(
            "sufficient",
            rationale="HbA1c 8.1% supports medical necessity for GLP-1 therapy.",
        ),
        {"prompt_tokens": 297, "completion_tokens": 35, "total_tokens": 332},
    ),
    ("PA-smoke-003", "classify", 1): (
        _classify("procedure"),
        {"prompt_tokens": 149, "completion_tokens": 14, "total_tokens": 163},
    ),
    ("PA-smoke-003", "policy-check", 1): (
        _policy(
            "out_of_policy",
            rationale="Cosmetic rhinoplasty is excluded from coverage.",
        ),
        {"prompt_tokens": 262, "completion_tokens": 33, "total_tokens": 295},
    ),
    ("PA-smoke-004", "classify", 1): (
        _classify("dme"),
        {"prompt_tokens": 143, "completion_tokens": 13, "total_tokens": 156},
    ),
    ("PA-smoke-004", "policy-check", 1): (
        _policy(
            "missing_info",
            missing=["Qualifying blood gas or oximetry study", "Physician order for home oxygen"],
            rationale="Home oxygen requires a qualifying study and a physician order.",
        ),
        {"prompt_tokens": 251, "completion_tokens": 47, "total_tokens": 298},
    ),
    ("PA-smoke-004", "policy-check", 2): (
        _policy(
            "missing_info",
            missing=["Physician order for home oxygen"],
            rationale="SpO2 94% at rest does not qualify; physician order still absent.",
        ),
        {"prompt_tokens": 283, "completion_tokens": 45, "total_tokens": 328},
    ),
    ("PA-smoke-004", "policy-check", 3): (
        _policy(
            "missing_info",
            missing=["Physician order for home oxygen"],
            rationale="Progress note received, but the physician order is still absent.",
        ),
        {"prompt_tokens": 309, "completion_tokens": 44, "total_tokens": 353},
    ),
}


def main() -> None:
    settings = get_settings()
    model = resolve_model("cheap", settings.tiers_path)
    for (request_id, node, attempt), (content, usage) in CASSETTES.items():
        path = cassettes.cassette_path(settings.cassettes_dir, "smoke", request_id, node, attempt)
        cassettes.save(path, model=model, content=content, usage=usage)
        print(f"wrote {path.relative_to(settings.cassettes_dir.parent)}")


if __name__ == "__main__":
    main()
