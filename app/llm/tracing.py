"""Langfuse-трейсинг — только наблюдаемость (правило 6): источник истины golden/CI-ассертов —
PathTrace из domain, не спаны. Включается, лишь когда в Settings заданы оба AW_LANGFUSE_*-ключа;
выключен (дефолт, тесты, CI) — чистый no-op: langfuse не импортируется, сервер не нужен.

Уживание с handler'ом (спека 03): LangGraph CallbackHandler даёт корень трейса + спан на ноду,
а LLM-вызов спрятан в route() (LiteLLM) — поэтому generation-спан создаёт сам route() через
generation(); OTel-контекст Langfuse v3 автоматически вкладывает его под спан текущей ноды.
Cost — только наша domain-функция cost_usd (контракт №5), автоинференс цен Langfuse не used.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.config import Settings
from app.domain.cost import cost_usd
from app.llm.tiers import Tier

# Recorder: usage ответа/кассеты → записать usage_details + cost_details в generation-спан
Recorder = Callable[[dict[str, Any] | None], None]


def enabled(settings: Settings) -> bool:
    return settings.langfuse_public_key is not None and settings.langfuse_secret_key is not None


def _client(settings: Settings) -> Any:
    """Синглтон Langfuse (SDK кэширует клиент по public_key); lazy import — при выключенном
    трейсинге langfuse (и его OTel-машинерия) не импортируются вовсе."""
    from langfuse import Langfuse

    assert settings.langfuse_secret_key is not None  # enabled() проверен вызывающим
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )


@contextmanager
def generation(node: str, tier: Tier, settings: Settings) -> Iterator[Recorder]:
    """Generation-спан вокруг LLM-вызова route(); имя = нода графа — дашборд бьёт cost по нодам."""
    if not enabled(settings):
        yield lambda usage: None
        return
    with _client(settings).start_as_current_generation(name=node, model=tier.model) as gen:

        def record(usage: dict[str, Any] | None) -> None:
            if usage is None:
                return
            gen.update(
                usage_details={
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                },
                cost_details={
                    "total": cost_usd(
                        usage,
                        input_per_1m=tier.input_per_1m,
                        output_per_1m=tier.output_per_1m,
                    )
                },
            )

        yield record


def langgraph_handler(settings: Settings) -> Any | None:
    """CallbackHandler для config["callbacks"] графа: спан на ноду + Agent Graph-вид
    (голый OTel структуру графа не рисует — решение ROADMAP iter 3). None — трейсинг выключен."""
    if not enabled(settings):
        return None
    _client(settings)  # инициализировать синглтон нашими ключами до создания handler'а
    from langfuse.langchain import CallbackHandler

    return CallbackHandler()


def flush(settings: Settings) -> None:
    """Дожать батч-экспортер перед выходом короткоживущего CLI-процесса; no-op без ключей."""
    if enabled(settings):
        _client(settings).flush()
