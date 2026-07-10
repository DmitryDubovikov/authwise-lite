"""route() — единственный шов к LLM (перенос triagewise). Дисциплина LiteLLM (правило 5,
красная линия): только SDK, один голый acompletion, телеметрия и callbacks выключены
непосредственно перед вызовом, lazy import — replay никогда не импортирует SDK.
Наблюдаемость (iter 3): вызов обёрнут generation-спаном tracing (no-op без ключей) — это шов
Langfuse, НЕ callback LiteLLM; латентность меряется здесь же (контракт №3).
"""

import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.llm import cassettes, tracing
from app.llm.tiers import resolve_tier


@dataclass(frozen=True)
class LLMReply:
    content: str
    usage: dict[str, Any] | None
    latency_ms: float  # per-node latency в RunRecord (контракт №3)


async def route(
    tier: str,
    messages: list[dict[str, Any]],
    *,
    request_id: str,
    node: str,
    attempt: int,
    settings: Settings,
) -> LLMReply:
    tier_spec = resolve_tier(tier, settings.tiers_path)
    path = cassettes.cassette_path(
        settings.cassettes_dir, settings.cassette_set, request_id, node, attempt
    )
    with tracing.generation(node, tier_spec, settings) as record:
        start = time.perf_counter()
        if settings.llm_mode == "replay":
            cassette = cassettes.load(path)
            content, usage = cassette.content, cassette.usage
        else:
            content, usage = await _live_completion(tier_spec.model, messages, settings)
        latency_ms = (time.perf_counter() - start) * 1000
        record(usage)
    if settings.llm_mode == "record":
        cassettes.save(path, model=tier_spec.model, content=content, usage=usage, messages=messages)
    return LLMReply(content=content, usage=usage, latency_ms=latency_ms)


async def _live_completion(
    model: str, messages: list[dict[str, Any]], settings: Settings
) -> tuple[str, dict[str, Any] | None]:
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
    return content, usage
