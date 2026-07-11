"""Промпты LLM-нод. Дефолт — из кода (CI/тесты offline); эти же тексты сид iter 6 регистрирует
в Prompt Registry, alias-загрузка подставляет запиненные версии из реестра на boundary."""

from dataclasses import dataclass

from app.domain.schemas import Classification

CLASSIFY_PROMPT = """\
You are an intake classifier for Northfield Health prior-authorization (PA) requests.
Classify the request below. Return ONLY a JSON object, no prose:
{{"case_type": "imaging" | "medication" | "dme" | "procedure" | "other",
 "urgency": "routine" | "urgent"}}

PA request:
{text}
"""

POLICY_CHECK_PROMPT = """\
You are a policy reviewer for Northfield Health prior-authorization (PA) requests.
Check the request against coverage policy and documentation requirements.
Return ONLY a JSON object, no prose:
{{"status": "sufficient" | "missing_info" | "out_of_policy",
 "missing": ["<required document>", ...],
 "rationale": "<one sentence>"}}

- "sufficient": documentation supports approval.
- "missing_info": specific required documents are absent — list them in "missing".
- "out_of_policy": the service is excluded from coverage (e.g. cosmetic, experimental).

Case type: {case_type} (urgency: {urgency})
PA request:
{text}
{received_block}"""


@dataclass(frozen=True)
class PromptBundle:
    """Шаблоны обеих LLM-нод одним объектом: дефолт — из кода; alias-загрузка (iter 6)
    подставляет версии из Prompt Registry на boundary, ноды графа разницы не видят."""

    classify: str
    policy_check: str


CODE_BUNDLE = PromptBundle(classify=CLASSIFY_PROMPT, policy_check=POLICY_CHECK_PROMPT)


# template — обязательный: единственный владелец дефолта «промпты из кода» — run_pa_request
# (CODE_BUNDLE на boundary), молчаливого фолбэка мимо бандла нет
def classify_messages(text: str, *, template: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": template.format(text=text)}]


def policy_check_messages(
    text: str,
    classification: Classification,
    received: list[str],
    *,
    template: str,
) -> list[dict[str, str]]:
    received_block = ""
    if received:
        docs = "\n".join(f"- {doc}" for doc in received)
        received_block = f"\nAdditional documents received after request-info:\n{docs}\n"
    content = template.format(
        case_type=classification.case_type,
        urgency=classification.urgency,
        text=text,
        received_block=received_block,
    )
    return [{"role": "user", "content": content}]
