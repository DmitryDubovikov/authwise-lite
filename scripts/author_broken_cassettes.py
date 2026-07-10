"""cassettes/base-broken-policy/ — authored subset для демо-регрессии iter 2 ($0, идемпотентно).

# aw-lite: authored subset → real record. Кассеты сочинены вручную, а не записаны реальным
# сломанным промптом (правило 4: replay=$0 — дефолт, existence-gate, не accuracy). Гейту это
# безразлично: он ловит СМЕНУ МАРШРУТА, а не происхождение ответа — сломанному набору хватает
# других статусов policy-check, чтобы путь ушёл с golden-ветки. Реальный record поверх — опц.
# (деньги, гейтируется).

Нарратив поломки: «промпт policy-check потерял критерии и штампует всё как sufficient». classify
не тронут — копируется из base как есть. Ключ кассеты — (request_id, node, attempt), контракт №4:
смена промпта НЕ рвёт replay (иначе демо-регрессия дала бы cassette-miss, а не смену маршрута —
ловушка ROADMAP Заметки №2). Отсюда — свой набор рядом с base, а не правка base in-place.

Subset (golden → фактический путь на сломанном наборе):
  PA-base-001  approve ↻0       → approve ↻0   контроль: гейт НЕ краснеет без регрессии
  PA-base-003  approve ↻0       → approve ↻0   контроль
  PA-base-015  approve ↻1       → approve ↻0   РЕГРЕССИЯ retry-count (число циклов retry-loop)
  PA-base-019  request-info ↻2  → approve ↻0   РЕГРЕССИЯ ветки
  PA-base-021  escalate ↻0      → approve ↻0   РЕГРЕССИЯ ветки
"""

import shutil

from app.config import get_settings
from app.domain.schemas import PolicyCheckResult
from app.llm import cassettes
from app.llm.tiers import resolve_model

BROKEN_SET = "base-broken-policy"
# заявки subset (ids определяют, для чего гейт краснеет/остаётся зелёным — импортируются тестом)
SUBSET: tuple[str, ...] = (
    "PA-base-001",
    "PA-base-003",
    "PA-base-015",
    "PA-base-019",
    "PA-base-021",
)
# «сломанный» вердикт одинаков для всех — rubber-stamp; usage синтетический (авторские кассеты)
_RATIONALE = "Documentation appears adequate."
_USAGE = {"prompt_tokens": 270, "completion_tokens": 20, "total_tokens": 290}


def _sufficient() -> str:
    return PolicyCheckResult.model_validate(
        {"status": "sufficient", "missing": [], "rationale": _RATIONALE}
    ).model_dump_json()


def main() -> None:
    settings = get_settings()
    model = resolve_model("cheap", settings.tiers_path)  # тот же тир/снапшот, что в base
    for request_id in SUBSET:
        # classify не затронут поломкой policy-check → копируем из base как есть
        src = cassettes.cassette_path(settings.cassettes_dir, "base", request_id, "classify", 1)
        dst = cassettes.cassette_path(settings.cassettes_dir, BROKEN_SET, request_id, "classify", 1)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        # policy-check a1 — сломанный: sufficient → decide уводит в approve ↻0 (терминал на a1)
        policy = cassettes.cassette_path(
            settings.cassettes_dir, BROKEN_SET, request_id, "policy-check", 1
        )
        cassettes.save(policy, model=model, content=_sufficient(), usage=_USAGE)
        print(f"wrote {dst.relative_to(settings.cassettes_dir.parent)}")
        print(f"wrote {policy.relative_to(settings.cassettes_dir.parent)}")


if __name__ == "__main__":
    main()
