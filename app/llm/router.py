"""route() — единственный шов к LLM (перенос triagewise). Дисциплина LiteLLM (правило 5,
красная линия): только SDK, один голый acompletion, телеметрия и callbacks выключены
непосредственно перед вызовом, lazy import — replay никогда не импортирует SDK.
"""

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.llm import cassettes
from app.llm.tiers import resolve_model


@dataclass(frozen=True)
class LLMReply:
    content: str
    usage: dict[str, Any] | None


async def route(
    tier: str,
    messages: list[dict[str, Any]],
    *,
    request_id: str,
    node: str,
    attempt: int,
    settings: Settings,
) -> LLMReply:
    model = resolve_model(tier, settings.tiers_path)
    path = cassettes.cassette_path(
        settings.cassettes_dir, settings.cassette_set, request_id, node, attempt
    )
    if settings.llm_mode == "replay":
        cassette = cassettes.load(path)
        return LLMReply(content=cassette.content, usage=cassette.usage)
    reply = await _live_completion(model, messages, settings)
    if settings.llm_mode == "record":
        cassettes.save(
            path, model=model, content=reply.content, usage=reply.usage, messages=messages
        )
    return reply


async def _live_completion(
    model: str, messages: list[dict[str, Any]], settings: Settings
) -> LLMReply:
    if settings.openai_api_key is None:
        raise RuntimeError("AW_OPENAI_API_KEY не задан — режимы record/live недоступны")
    import litellm  # lazy: replay никогда не импортирует SDK

    litellm.telemetry = False
    litellm.callbacks = []
    litellm.success_callback = []
    litellm.failure_callback = []
    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=0,  # контракт №6: детерминизм, иначе retry_cycles невоспроизводимы
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
    )
    content = resp.choices[0].message.content or ""
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else None
    return LLMReply(content=content, usage=usage)
