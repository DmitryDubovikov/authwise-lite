"""Промпты LLM-нод. До iter 6 живут в коде; регистрация в Prompt Registry — скоуп iter 6."""

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


def classify_messages(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": CLASSIFY_PROMPT.format(text=text)}]


def policy_check_messages(
    text: str, classification: Classification, received: list[str]
) -> list[dict[str, str]]:
    received_block = ""
    if received:
        docs = "\n".join(f"- {doc}" for doc in received)
        received_block = f"\nAdditional documents received after request-info:\n{docs}\n"
    content = POLICY_CHECK_PROMPT.format(
        case_type=classification.case_type,
        urgency=classification.urgency,
        text=text,
        received_block=received_block,
    )
    return [{"role": "user", "content": content}]
