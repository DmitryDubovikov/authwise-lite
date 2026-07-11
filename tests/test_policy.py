"""Registry-механика routing-policy (iter 6) на локальном sqlite-сторе (offline, $0):
сид идемпотентен и не откатывает swap, resolve отдаёт пины и шаблоны, swap обменивает alias;
alias-загрузка реально доезжает до нод и не меняет пути (кассеты ключуются структурно, №4).
Модульный стор общий — мутирующий тест обязан вернуть исходное состояние alias.
"""

import asyncio
from collections.abc import Iterator

import mlflow
import pytest
from conftest import ROOT, replay_settings
from mlflow import MlflowClient

from app.domain.schemas import PARequest
from app.persistence import routing_policy as store
from app.workflow import policy
from app.workflow.fixtures import load_requests
from app.workflow.graph import run_pa_request
from app.workflow.prompts import CLASSIFY_PROMPT, POLICY_CHECK_PROMPT, PromptBundle


@pytest.fixture(scope="module")
def tracking_uri(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Герметичный стор: и sqlite-БД, и artifact root LoggedModel — во временном каталоге.
    Артефакты sqlite-бэкенд кладёт в ./mlruns относительно CWD, поэтому chdir на весь модуль
    (пути тестов абсолютные — ROOT); иначе прогоны мусорили бы mlruns/ в корень репо."""
    root = tmp_path_factory.mktemp("mlflow")
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(root)
        uri = f"sqlite:///{root}/registry.db"
        policy.seed_policy(tracking_uri=uri)
        yield uri


def _smoke_request(request_id: str) -> PARequest:
    requests = load_requests(ROOT / "fixtures" / "requests-smoke.jsonl")
    return next(r for r in requests if r.id == request_id)


def _alias_versions(uri: str) -> dict[str, int]:
    verification = policy.verify_policy(tracking_uri=uri)
    assert verification.ok(), verification.problems
    return {alias: p.registered_version for alias, p in verification.policies.items()}


def test_seed_is_idempotent(tracking_uri: str) -> None:
    before = _alias_versions(tracking_uri)
    result = policy.seed_policy(tracking_uri=tracking_uri)  # повторный сид
    assert _alias_versions(tracking_uri) == before
    assert result.aliases_set == {store.CHAMPION: False, store.CHALLENGER: False}
    # версии не распухли: у policy-check ровно 2 (код + rubber-stamp), у политики ровно 2
    mlflow.set_tracking_uri(tracking_uri)
    latest = mlflow.genai.load_prompt(f"prompts:/{policy.PROMPT_POLICY_CHECK}@latest")
    assert latest.version == 2
    versions = MlflowClient().search_model_versions(f"name = '{store.MODEL_NAME}'")
    assert len(versions) == 2


def test_champion_pins_code_prompts_challenger_rubber_stamp(tracking_uri: str) -> None:
    champion = store.resolve(store.CHAMPION, tracking_uri=tracking_uri)
    challenger = store.resolve(store.CHALLENGER, tracking_uri=tracking_uri)
    assert champion is not None and challenger is not None
    assert champion.templates[policy.PROMPT_CLASSIFY] == CLASSIFY_PROMPT
    assert champion.templates[policy.PROMPT_POLICY_CHECK] == POLICY_CHECK_PROMPT
    assert (
        challenger.templates[policy.PROMPT_POLICY_CHECK] == policy.POLICY_CHECK_PROMPT_RUBBER_STAMP
    )
    # кросс-чек params ↔ mlflow.linkedPrompts выполняет сам resolve (ValueError при
    # расхождении) — успешный resolve выше уже доказывает консистентность пинов


def test_swap_exchanges_aliases_and_seed_keeps_swap(tracking_uri: str) -> None:
    before = _alias_versions(tracking_uri)
    try:
        policy.swap_policy(tracking_uri=tracking_uri)
        swapped = _alias_versions(tracking_uri)
        assert swapped[store.CHAMPION] == before[store.CHALLENGER]
        assert swapped[store.CHALLENGER] == before[store.CHAMPION]
        # сид после swap не перевешивает alias (иначе демо-swap откатился бы любым сидом)
        policy.seed_policy(tracking_uri=tracking_uri)
        assert _alias_versions(tracking_uri) == swapped
    finally:
        policy.swap_policy(tracking_uri=tracking_uri)  # вернуть модульный стор к исходному
    assert _alias_versions(tracking_uri) == before


def test_resolve_missing_alias_returns_none(tracking_uri: str) -> None:
    assert store.resolve("shadow", tracking_uri=tracking_uri) is None


def test_load_bundle_feeds_graph_without_changing_paths(tracking_uri: str) -> None:
    """Alias-загрузка не меняет пути: кассеты ключуются (request_id, node, attempt), не
    содержимым промпта (контракт №4) — replay с бандлом challenger идёт по тем же кассетам."""
    bundle, resolved = policy.load_bundle(store.CHALLENGER, tracking_uri=tracking_uri)
    assert bundle.policy_check == policy.POLICY_CHECK_PROMPT_RUBBER_STAMP
    assert resolved.alias == store.CHALLENGER
    result = asyncio.run(
        run_pa_request(
            _smoke_request("PA-smoke-004"), settings=replay_settings("smoke"), prompts=bundle
        )
    )
    assert (result.trace.branch, result.trace.retry_cycles) == ("request-info", 2)


def test_bundle_templates_actually_reach_nodes() -> None:
    """Шаблон из бандла реально форматируется нодой: неизвестный плейсхолдер падает KeyError —
    доказательство, что classify использует переданный шаблон, а не константу кода."""
    bundle = PromptBundle(classify="{unknown_placeholder}", policy_check=POLICY_CHECK_PROMPT)
    with pytest.raises(KeyError, match="unknown_placeholder"):
        asyncio.run(
            run_pa_request(
                _smoke_request("PA-smoke-001"), settings=replay_settings("smoke"), prompts=bundle
            )
        )
