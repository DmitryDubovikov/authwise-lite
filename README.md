# authwise-lite

A **trajectory-eval control plane** built over a deliberately narrow fixture: routing synthetic
Prior Authorization (PA) requests for a fictional payer (*Northfield Health*). The app is a
fixture; **path-level measurement is the product** — trajectory golden-set, CI path-assertion
gates, per-node cost/latency SLO, and path-distribution drift monitoring. See `CLAUDE.md`
(constitution) and `ROADMAP.md` (iteration backbone).

> **Status: iteration 0 closed** — the branching graph with a real branch-point and retry-loop
> is in place, runs offline ($0, replay cassettes) and returns its path as a typed value
> (`PathTrace`). The quickstart heading names the last iteration it actually covers, as in the
> sibling projects.

## The object of measurement

The routing graph is small on purpose and **frozen after iter 0** — complexity goes into the
measurement, not the graph:

```
classify → policy-check → decide ─┬─ approve
                                  ├─ request-info (retry-loop, ≤ N attempts)
                                  └─ escalate
```

What gets versioned, asserted, and monitored is **the path a request takes** — which branch
fired and how many retry cycles ran — not the text of the final answer. Every iteration in the
ROADMAP (golden-set, CI gate, SLO, drift) targets that path.

## Relation to the sibling -lite projects

Fifth in the series, and deliberately **not a new axis of tools**: policywise-lite covers
architecture + RAG (LangGraph), dossier-lite covers multi-agent orchestration, sentiment-mlops
covers classic supervised MLOps, triagewise-lite covers single-call LLMOps. authwise-lite
reuses their stack wholesale — the branching-graph pattern, LiteLLM, and cassettes from
`policywise-lite`; MLflow, promptfoo/DeepEval, OTel, Langfuse, and Phoenix from
`triagewise-lite` — and applies it to the one thing none of them measures: **the trajectory of
a multi-step agent, not just the answer it gives**. The single deliberate exception is
Prometheus/Grafana, introduced for per-node SLO alerting and runtime budget controls.

## Quickstart (after iter 0 — branching-graph skeleton)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use

# Route the smoke PA requests through the graph — replay mode, offline/$0.
# Prints one path per request; all three terminals + the retry-loop are exercised:
#   PA-smoke-002: classify → policy-check → request-info ↻1 → approve
make smoke

# Or a single request:
uv run python -m app.cli fixtures/requests-smoke.jsonl --id PA-smoke-002

make check                      # ruff + format + mypy + pytest (static gate, no LLM)
make up                         # control-plane backend (MLflow) at localhost:5051 — empty until iter 1
make down                       # stop MLflow
```

Make targets: `make check` (lint+types+tests), `make smoke` (run the smoke fixture),
`make up`/`make down` (MLflow), `make author-cassettes` (regenerate the $0 smoke cassettes),
`make test`, `make fmt`.

`AW_LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit the provider and cost money — gated by an explicit go, as in the sibling
projects. All env vars go through `Settings` with the `AW_` prefix (see `.env.example`).
