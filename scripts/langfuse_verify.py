"""Verify the store (правило 9): per-node атрибуция доказывается запросом к Langfuse public
API, не скрином UI. Берём свежий трейс и проверяем: спаны названы нодами графа (атрибуция по
ноде, не по всему run), внутри LLM-нод — generation с usage и нашим cost (контракт №5).
"""

import base64
import json
import urllib.parse
import urllib.request
from typing import Any

from app.config import Settings, get_settings
from app.llm import tracing

GRAPH_LLM_NODES = {"classify", "policy-check"}  # generation обязателен: тут живёт LLM
GRAPH_NODES = GRAPH_LLM_NODES | {"decide"}  # request-info — только на retry-путях


def _get(settings: Settings, path: str, **params: str) -> dict[str, Any]:
    assert settings.langfuse_public_key and settings.langfuse_secret_key
    creds = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key.get_secret_value()}"
    token = base64.b64encode(creds.encode()).decode()
    url = f"{settings.langfuse_host}/api/public{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def main() -> None:
    settings = get_settings()
    if not tracing.enabled(settings):
        raise SystemExit("AW_LANGFUSE_PUBLIC_KEY/SECRET_KEY не заданы — см. make langfuse-verify")

    traces = _get(settings, "/traces", limit="1", orderBy="timestamp.desc")["data"]
    if not traces:
        raise SystemExit("в Langfuse нет трейсов — сначала make obs-up и make trace-base")
    trace_id = traces[0]["id"]
    observations = _get(settings, "/observations", traceId=trace_id, limit="100")["data"]

    # ноды графа handler пишет типом CHAIN (LangChain-семантика); generation — наш шов в route()
    node_spans = {o["name"] for o in observations if o["type"] != "GENERATION"}
    generations = [o for o in observations if o["type"] == "GENERATION"]
    name_by_id = {o["id"]: o["name"] for o in observations}
    for generation in sorted(generations, key=lambda o: o["startTime"]):
        usage = generation.get("usage") or {}
        # calculatedTotalCost — поле API; наш явный cost_details ложится туда (total)
        cost = generation.get("calculatedTotalCost")
        cost_str = f"${cost:.6f}" if cost is not None else "—"
        print(
            f"{generation['name']}: model={generation.get('model')} "
            f"in={usage.get('input')} out={usage.get('output')} cost={cost_str}"
        )

    problems = []
    if missing := GRAPH_NODES - node_spans:
        problems.append(f"нет спанов нод: {sorted(missing)} (есть: {sorted(node_spans)})")
    if missing := GRAPH_LLM_NODES - {g["name"] for g in generations}:
        problems.append(f"нет generation по LLM-нодам: {sorted(missing)}")
    # сама атрибуция: generation вложен в спан ОДНОИМЁННОЙ ноды, а не висит на run целиком
    orphans = [
        g["name"] for g in generations if name_by_id.get(g["parentObservationId"]) != g["name"]
    ]
    if orphans:
        problems.append(f"generation не вложен в спан своей ноды: {orphans}")
    if without_usage := [g["name"] for g in generations if not (g.get("usage") or {}).get("total")]:
        problems.append(f"generation без usage: {without_usage}")
    if without_cost := [g["name"] for g in generations if not g.get("calculatedTotalCost")]:
        problems.append(f"generation без cost: {without_cost}")

    rule = "─" * 60
    if problems:
        print(f"{rule}\n❌  VERIFY FAILED — атрибуция по нодам не подтверждена:")
        for problem in problems:
            print(f"  · {problem}")
        raise SystemExit(1)
    print(
        f"{rule}\n✅  VERIFY OK — трейс {trace_id}: спаны атрибутированы по нодам графа, "
        f"{len(generations)} generation с usage и cost из llm-tiers.yaml"
    )


if __name__ == "__main__":
    main()
