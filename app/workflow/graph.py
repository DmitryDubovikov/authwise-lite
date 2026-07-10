"""Граф PA-заявки (заморожен после iter 0, правило 3):

    classify → policy-check → decide{approve | request-info (retry-loop, ≤N) | escalate}

LLM живёт в classify и policy-check; decide — чистая domain-функция. Паттерн policywise:
решение пишется нодой в стейт, условное ребро — тривиальный lookup; deps — через
config["configurable"], не через стейт и не через глобалы.
"""

import math
import operator
from dataclasses import dataclass
from typing import Annotated, NotRequired, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.domain.decide import Decision, decide
from app.domain.path import PathTrace
from app.domain.schemas import (
    Classification,
    NodeStat,
    PARequest,
    PolicyCheckResult,
    parse_classification,
    parse_policy_check,
)
from app.llm import tracing
from app.llm.router import route
from app.workflow.costs import spent_usd
from app.workflow.prompts import classify_messages, policy_check_messages


class PAState(TypedDict):
    request_id: str
    text: str
    supplemental: list[str]  # что заявитель может дослать (фикстура, по одному за цикл)
    received: Annotated[list[str], operator.add]  # что уже дослал по request-info
    nodes: Annotated[list[str], operator.add]  # посещённые ноды → PathTrace.nodes
    node_stats: Annotated[list[NodeStat], operator.add]  # → RunRecord (контракт №3)
    classification: NotRequired[Classification]
    policy: NotRequired[PolicyCheckResult]
    retry_cycles: NotRequired[int]
    decision: NotRequired[Decision]
    budget_escalated: NotRequired[bool]  # escalate по исчерпанию бюджета (iter 4) → RunRecord


def _settings(config: RunnableConfig) -> Settings:
    return cast(Settings, config["configurable"]["settings"])


async def classify(state: PAState, config: RunnableConfig) -> dict[str, object]:
    settings = _settings(config)
    reply = await route(
        settings.tier_classify,
        classify_messages(state["text"]),
        request_id=state["request_id"],
        node="classify",
        attempt=1,
        settings=settings,
    )
    return {
        "classification": parse_classification(reply.content),
        "nodes": ["classify"],
        "node_stats": [
            NodeStat(
                node="classify",
                attempt=1,
                tier=settings.tier_classify,
                usage=reply.usage,
                latency_ms=reply.latency_ms,
            )
        ],
    }


async def policy_check(state: PAState, config: RunnableConfig) -> dict[str, object]:
    settings = _settings(config)
    # номер вызова policy-check (ключ кассеты) выводим: прокруток retry-loop + 1
    attempt = state.get("retry_cycles", 0) + 1
    reply = await route(
        settings.tier_policy_check,
        policy_check_messages(state["text"], state["classification"], state["received"]),
        request_id=state["request_id"],
        node="policy-check",
        attempt=attempt,
        settings=settings,
    )
    return {
        "policy": parse_policy_check(reply.content),
        "nodes": ["policy-check"],
        "node_stats": [
            NodeStat(
                node="policy-check",
                attempt=attempt,
                tier=settings.tier_policy_check,
                usage=reply.usage,
                latency_ms=reply.latency_ms,
            )
        ],
    }


def decide_node(state: PAState, config: RunnableConfig) -> dict[str, object]:
    settings = _settings(config)
    remaining = settings.run_budget_usd - spent_usd(state["node_stats"], settings)
    retry_cycles = state.get("retry_cycles", 0)
    decision = decide(
        state["policy"],
        retry_cycles=retry_cycles,
        retry_limit=settings.retry_limit,
        budget_remaining_usd=remaining,
    )
    # budget-эскалация = расхождение с безлимитным решением: PathTrace заморожен, факт живёт
    # флагом в RunRecord (счётчик Prometheus, iter 4); перезапись при каждом decide — финальный
    # проход и определяет терминал
    unbounded = decide(
        state["policy"],
        retry_cycles=retry_cycles,
        retry_limit=settings.retry_limit,
        budget_remaining_usd=math.inf,
    )
    return {"decision": decision, "budget_escalated": decision != unbounded, "nodes": ["decide"]}


def request_info(state: PAState, config: RunnableConfig) -> dict[str, object]:
    """Один цикл до-запроса: заявитель присылает следующий пакет документов из фикстуры."""
    cycle = state.get("retry_cycles", 0)
    received = state["supplemental"][cycle : cycle + 1]
    return {"received": received, "retry_cycles": cycle + 1, "nodes": ["request-info"]}


def route_decision(state: PAState) -> Decision:
    """Условное ребро: тривиальный lookup решения, проставленного decide-нодой."""
    return state["decision"]


def build_pa_graph() -> StateGraph[PAState, None, PAState, PAState]:
    builder = StateGraph(PAState)
    builder.add_node("classify", classify)
    builder.add_node("policy-check", policy_check)
    builder.add_node("decide", decide_node)
    builder.add_node("request-info", request_info)
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "policy-check")
    builder.add_edge("policy-check", "decide")
    builder.add_conditional_edges(
        "decide",
        route_decision,
        {"retry": "request-info", "approve": END, "escalate": END, "request-info": END},
    )
    builder.add_edge("request-info", "policy-check")
    return builder


_GRAPH = build_pa_graph().compile()  # структура статична → компилируем на импорте


@dataclass(frozen=True)
class PARunResult:
    trace: PathTrace  # источник истины golden/CI-ассертов (правило 6)
    policy: PolicyCheckResult  # финальный вердикт policy-check («ответ» приложения-фикстуры)
    node_stats: tuple[NodeStat, ...]  # per-node usage/latency (контракт №3)
    budget_escalated: bool  # escalate по исчерпанию бюджета рана (iter 4), не ассертится


async def run_pa_request(request: PARequest, *, settings: Settings) -> PARunResult:
    """Boundary workflow-слоя: одна заявка через граф → ответ + PathTrace."""
    config: RunnableConfig = {"configurable": {"settings": settings}}
    handler = tracing.langgraph_handler(settings)  # None — трейсинг выключен (дефолт)
    if handler is not None:
        config["callbacks"] = [handler]
    final = cast(
        PAState,
        await _GRAPH.ainvoke(
            {
                "request_id": request.id,
                "text": request.text,
                "supplemental": request.supplemental,
                "received": [],
                "nodes": [],
                "node_stats": [],
            },
            config=config,
        ),
    )
    decision = final["decision"]
    if decision == "retry":  # недостижимо: retry всегда уводит в request-info
        raise RuntimeError("граф завершился на нетерминальном решении")
    trace = PathTrace(
        branch=decision,
        retry_cycles=final.get("retry_cycles", 0),
        nodes=tuple(final["nodes"]),
    )
    return PARunResult(
        trace=trace,
        policy=final["policy"],
        node_stats=tuple(final["node_stats"]),
        budget_escalated=final.get("budget_escalated", False),
    )
