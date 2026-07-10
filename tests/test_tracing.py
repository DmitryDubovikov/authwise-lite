"""Трейсинг — только наблюдаемость (правило 6): без AW_LANGFUSE_*-ключей (дефолт, тесты, CI) —
чистый no-op, langfuse не импортируется, сервер не нужен, replay-прогоны не меняются.
"""

import subprocess
import sys

from conftest import ROOT, replay_settings

from app.llm import tracing
from app.llm.tiers import Tier

_TIER = Tier(model="test-2025-01-01", input_per_1m=0.10, output_per_1m=0.40)


def test_disabled_tracing_is_noop() -> None:
    settings = replay_settings("smoke")
    assert not tracing.enabled(settings)
    assert tracing.langgraph_handler(settings) is None
    with tracing.generation("classify", _TIER, settings) as record:
        record({"prompt_tokens": 1, "completion_tokens": 1})  # не падает и никуда не шлёт
    tracing.flush(settings)


def test_disabled_tracing_does_not_import_langfuse() -> None:
    """Replay-прогон целиком (граф + route) без ключей не тянет langfuse — как lazy-гейт LiteLLM."""
    code = (
        "import sys, asyncio; sys.path.insert(0, 'tests'); "
        "from conftest import ROOT, replay_settings; "
        "from app.workflow.fixtures import load_requests; "
        "from app.workflow.runner import run_batch; "
        "requests = load_requests(ROOT / 'fixtures' / 'requests-smoke.jsonl'); "
        "asyncio.run(run_batch(requests, settings=replay_settings('smoke'))); "
        "sys.exit(1 if 'langfuse' in sys.modules else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT)
    assert result.returncode == 0, "выключенный трейсинг затянул langfuse — lazy import сломан"
