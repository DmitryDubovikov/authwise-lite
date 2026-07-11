"""Оркестрация routing-policy (решение «Г», iter 6): состав промптов и версий политики —
здесь; MLflow-драйвер — только в persistence (правило 6). Champion пинит промпты из кода,
challenger — rubber-stamp policy-check (материализованный нарратив демо-регрессии iter 2).
"""

from dataclasses import dataclass

from app.persistence import routing_policy as store
from app.workflow.prompts import CLASSIFY_PROMPT, POLICY_CHECK_PROMPT, PromptBundle

PROMPT_CLASSIFY = "pa-classify"
PROMPT_POLICY_CHECK = "pa-policy-check"

# Challenger-фикстура (iter 6): материализованный «сломанный» промпт нарратива демо-регрессии
# iter 2 (cassettes/base-broken-policy — «потерял критерии и штампует всё как sufficient»):
# критерии missing_info/out_of_policy выброшены, ревьюеру велено доверять документации.
# Живёт рядом с сидом, который его регистрирует (policy-check v2, пин challenger), —
# в рантайм-модуль промптов не попадает.
POLICY_CHECK_PROMPT_RUBBER_STAMP = """\
You are a policy reviewer for Northfield Health prior-authorization (PA) requests.
Provider documentation is reliable; unless something is clearly wrong, treat the service as
covered and the documentation as complete.
Return ONLY a JSON object, no prose:
{{"status": "sufficient" | "missing_info" | "out_of_policy",
 "missing": ["<required document>", ...],
 "rationale": "<one sentence>"}}

Case type: {case_type} (urgency: {urgency})
PA request:
{text}
{received_block}"""


@dataclass(frozen=True)
class SeedResult:
    """Что сид обеспечил в сторе (версии — фактические, не предполагаемые)."""

    classify_version: int
    policy_check_version: int  # код-вариант (пин champion)
    policy_check_rubber_stamp_version: int  # challenger-фикстура
    champion_version: int  # версия registered model под alias по умолчанию
    challenger_version: int
    aliases_set: dict[str, bool]  # alias → поставлен сейчас (False — существовал, не тронут)


def _ensure_alias(alias: str, version: int, tracking_uri: str) -> bool:
    """Ставит alias, только если он ещё не разрешается: повторный сид не откатывает swap.
    True — поставлен сейчас, False — существовал и не тронут."""
    if store.alias_version(alias, tracking_uri=tracking_uri) is not None:
        return False
    store.set_alias(alias, version, tracking_uri=tracking_uri)
    return True


def seed_policy(*, tracking_uri: str) -> SeedResult:
    """Идемпотентный сид: промпты → LoggedModel-версии с пинами → registered-версии → alias.
    Существующие сущности переиспользуются, существующие alias не перевешиваются."""
    classify_v = store.ensure_prompt_version(
        PROMPT_CLASSIFY, CLASSIFY_PROMPT, tracking_uri=tracking_uri
    )
    policy_v = store.ensure_prompt_version(
        PROMPT_POLICY_CHECK, POLICY_CHECK_PROMPT, tracking_uri=tracking_uri
    )
    rubber_stamp_v = store.ensure_prompt_version(
        PROMPT_POLICY_CHECK, POLICY_CHECK_PROMPT_RUBBER_STAMP, tracking_uri=tracking_uri
    )
    champion_model = store.ensure_policy_version(
        {PROMPT_CLASSIFY: classify_v, PROMPT_POLICY_CHECK: policy_v}, tracking_uri=tracking_uri
    )
    challenger_model = store.ensure_policy_version(
        {PROMPT_CLASSIFY: classify_v, PROMPT_POLICY_CHECK: rubber_stamp_v},
        tracking_uri=tracking_uri,
    )
    champion_version = store.ensure_registered_version(champion_model, tracking_uri=tracking_uri)
    challenger_version = store.ensure_registered_version(
        challenger_model, tracking_uri=tracking_uri
    )
    aliases_set = {
        store.CHAMPION: _ensure_alias(store.CHAMPION, champion_version, tracking_uri),
        store.CHALLENGER: _ensure_alias(store.CHALLENGER, challenger_version, tracking_uri),
    }
    return SeedResult(
        classify_version=classify_v,
        policy_check_version=policy_v,
        policy_check_rubber_stamp_version=rubber_stamp_v,
        champion_version=champion_version,
        challenger_version=challenger_version,
        aliases_set=aliases_set,
    )


@dataclass(frozen=True)
class PolicyVerification:
    """Сводка verify: всё по данным ИЗ стора (правило 9). Проверки структурные и
    инвариантные к swap: обе роли разрешаются консистентно (кросс-чек пинов — в resolve),
    политики разделяют classify и различаются policy-check."""

    policies: dict[str, store.ResolvedPolicy]  # alias → разрешённая политика
    problems: list[str]

    def ok(self) -> bool:
        return not self.problems


def verify_policy(*, tracking_uri: str) -> PolicyVerification:
    policies: dict[str, store.ResolvedPolicy] = {}
    problems: list[str] = []
    for alias in (store.CHAMPION, store.CHALLENGER):
        try:
            # консистентность params ↔ linkedPrompts проверяет сам resolve (драйверное
            # знание о двух кодировках пинов); неконсистентный стор — ValueError
            resolved = store.resolve(alias, tracking_uri=tracking_uri)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if resolved is None:
            problems.append(f"alias {alias!r} не разрешается — стор не засеян (make policy-seed)")
            continue
        policies[alias] = resolved
        expected_names = {PROMPT_CLASSIFY, PROMPT_POLICY_CHECK}
        if set(resolved.prompt_versions) != expected_names:
            problems.append(
                f"{alias}: пины params {sorted(resolved.prompt_versions)} != "
                f"{sorted(expected_names)}"
            )
        if not all(resolved.templates.values()):
            problems.append(f"{alias}: пустой шаблон в Prompt Registry")
    if len(policies) == 2:
        champion, challenger = policies[store.CHAMPION], policies[store.CHALLENGER]
        if champion.registered_version == challenger.registered_version:
            problems.append("champion и challenger указывают на одну версию routing-policy")
        if champion.prompt_versions.get(PROMPT_CLASSIFY) != challenger.prompt_versions.get(
            PROMPT_CLASSIFY
        ):
            problems.append("политики расходятся по classify — задумана общая версия")
        if champion.prompt_versions.get(PROMPT_POLICY_CHECK) == challenger.prompt_versions.get(
            PROMPT_POLICY_CHECK
        ):
            problems.append("политики пинят один policy-check — challenger не отличается")
    return PolicyVerification(policies=policies, problems=problems)


def swap_policy(*, tracking_uri: str) -> tuple[int, int]:
    """Ручной swap champion ↔ challenger — обмен composed из alias-примитивов persistence
    (симметрично сиду). Возвращает (новая версия champion, новая версия challenger)."""
    champion = store.alias_version(store.CHAMPION, tracking_uri=tracking_uri)
    challenger = store.alias_version(store.CHALLENGER, tracking_uri=tracking_uri)
    if champion is None or challenger is None:
        raise ValueError("alias champion/challenger не разрешаются — сначала make policy-seed")
    # aw-lite: пара переназначений не транзакционна (обрыв между вызовами оставит оба alias
    # на одной версии) → verify_policy это ловит, повторный policy-swap чинит
    store.set_alias(store.CHAMPION, challenger, tracking_uri=tracking_uri)
    store.set_alias(store.CHALLENGER, champion, tracking_uri=tracking_uri)
    return challenger, champion


def describe_pins(resolved: store.ResolvedPolicy) -> str:
    """Рендер пинов для витринной печати транспортов: «pa-classify v1, pa-policy-check v2»."""
    return ", ".join(f"{name} v{v}" for name, v in sorted(resolved.prompt_versions.items()))


def load_bundle(alias: str, *, tracking_uri: str) -> tuple[PromptBundle, store.ResolvedPolicy]:
    """Alias-загрузка (boundary): alias → запиненные шаблоны из реестра → PromptBundle."""
    resolved = store.resolve(alias, tracking_uri=tracking_uri)
    if resolved is None:
        raise ValueError(f"routing-policy alias {alias!r} не найден — сначала make policy-seed")
    return (
        PromptBundle(
            classify=resolved.templates[PROMPT_CLASSIFY],
            policy_check=resolved.templates[PROMPT_POLICY_CHECK],
        ),
        resolved,
    )
