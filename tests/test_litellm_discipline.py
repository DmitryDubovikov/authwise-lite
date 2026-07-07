"""Механический гейт дисциплины LiteLLM (правило 5, красная линия — перенос triagewise):
SDK-only, единственный шов, телеметрия/callbacks off до вызова, replay не тянет SDK, пин версии.
"""

import re
import subprocess
import sys

from conftest import ROOT

ROUTER = ROOT / "app" / "llm" / "router.py"

_ALLOWED_ATTRS = {"telemetry", "callbacks", "success_callback", "failure_callback", "acompletion"}


def test_router_is_the_single_import_site() -> None:
    offenders = [
        py
        for py in (ROOT / "app").rglob("*.py")
        if py != ROUTER and re.search(r"^\s*(import litellm|from litellm)", py.read_text(), re.M)
    ]
    assert not offenders, f"litellm импортируется вне router.py: {offenders}"
    assert re.search(r"^\s+import litellm", ROUTER.read_text(), re.M), "lazy import пропал"


def test_attr_surface_is_minimal() -> None:
    for py in (ROOT / "app").rglob("*.py"):
        used = set(re.findall(r"litellm\.(\w+)", py.read_text()))
        extra = used - _ALLOWED_ATTRS
        assert not extra, f"{py}: неожиданные атрибуты litellm: {extra}"


def test_no_proxy_traces() -> None:
    # Proxy не требует импорта SDK (префикс litellm_proxy/... в имени модели) —
    # ловим подстроками по всему app/ и llm-tiers.yaml, как в triagewise
    files = [*(ROOT / "app").rglob("*.py"), ROOT / "llm-tiers.yaml"]
    offenders = [f for f in files if re.search(r"litellm\.proxy|litellm_proxy", f.read_text())]
    assert not offenders, f"след LiteLLM Proxy (правило 5, красная линия): {offenders}"


def test_leak_guards_precede_the_call() -> None:
    src = ROUTER.read_text()
    call = src.index("litellm.acompletion")
    for guard in (
        "litellm.telemetry = False",
        "litellm.callbacks = []",
        "litellm.success_callback = []",
        "litellm.failure_callback = []",
    ):
        assert src.index(guard) < call, f"гард {guard!r} должен стоять до acompletion"


def test_replay_import_does_not_pull_sdk() -> None:
    code = "import sys, app.llm.router; sys.exit(1 if 'litellm' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT)
    assert result.returncode == 0, "импорт router.py затянул litellm — lazy import сломан"


def test_version_is_pinned() -> None:
    assert re.search(r'"litellm>=[\d.]+,<2"', (ROOT / "pyproject.toml").read_text())
    lock = (ROOT / "uv.lock").read_text()
    assert re.search(r'name = "litellm"\nversion = "[\d.]+"', lock), "litellm не запиннен в uv.lock"
