"""Общие HTTP-хелперы verify-скриптов (правило 9: доказательство — запросом к API, не UI).
stdlib-only, как весь транспортный слой скриптов; используются slo_verify и drift_verify.
"""

import base64
import json
import urllib.parse
import urllib.request
from typing import Any

from app.config import Settings


def get_json(url: str, *, auth: tuple[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url)
    if auth is not None:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def prom_query(prometheus_url: str, expr: str) -> list[dict[str, Any]]:
    """Серии инстант-запроса к Prometheus — доказательство, что метрика скрейпится."""
    query = urllib.parse.urlencode({"query": expr})
    payload = get_json(f"{prometheus_url}/api/v1/query?{query}")
    return list(payload["data"]["result"])


def grafana_alert_state(settings: Settings, title: str) -> str | None:
    """Состояние alert rule из Grafana (Prometheus-совместимый API); None — правила нет."""
    url = f"{settings.grafana_url}/api/prometheus/grafana/api/v1/rules"
    auth = (settings.grafana_user, settings.grafana_password.get_secret_value())
    payload = get_json(url, auth=auth)
    for group in payload["data"]["groups"]:
        for rule in group["rules"]:
            if rule["name"] == title:
                return str(rule["state"])
    return None


def check_alert_firing(settings: Settings, title: str, *, push_hint: str) -> str | None:
    """Проверка «правило существует и Firing»: None — всё хорошо, иначе текст проблемы."""
    state = grafana_alert_state(settings, title)
    if state is None:
        return f"в Grafana нет alert rule {title!r} — провижининг не подхватился?"
    print(f"alert rule {title!r}: state={state}")
    if state != "firing":
        return (
            f"alert rule не Firing (state={state}) — подожди evaluation+for (~1 мин "
            f"после {push_hint}) и повтори"
        )
    return None


def report(problems: list[str], *, failed: str, ok: str) -> None:
    """Единый вердикт verify-скрипта: перечень проблем + exit≠0 либо ✅."""
    rule = "─" * 60
    if problems:
        print(f"{rule}\n❌  VERIFY FAILED — {failed}:")
        for problem in problems:
            print(f"  · {problem}")
        raise SystemExit(1)
    print(f"{rule}\n✅  VERIFY OK — {ok}")
