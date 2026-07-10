# authwise-lite

A **trajectory-eval control plane** built over a deliberately narrow fixture: routing synthetic
Prior Authorization (PA) requests for a fictional payer (*Northfield Health*). The app is a
fixture; **path-level measurement is the product** — trajectory golden-set, CI path-assertion
gates, per-node cost/latency SLO, and path-distribution drift monitoring. See `CLAUDE.md`
(constitution) and `ROADMAP.md` (iteration backbone).

> **Status: iteration 4 closed** — **agent FinOps guardrails: per-node SLO alerting + runtime budget
> controls**. Two guardrails turn iter 3's measurement into enforcement. (1) **Runtime budget
> controls**: each run has a USD budget (`AW_RUN_BUDGET_USD`), and the retry-loop continues only while
> the budget is positive — exhaustion routes the request to `escalate` (a human is cheaper than
> another LLM cycle), so budget exhaustion is a **route** visible in the trajectory, not an exception.
> The default budget leaves golden paths unchanged; `make budget-demo` squeezes it via env and the
> retry-loop tips into `escalate  [budget]`. (2) **Per-node SLO alerting**: per-node latency/cost and a
> budget-escalation counter are pushed to Prometheus (via Pushgateway — the batch is short-lived),
> and a provisioned Grafana alert rule **names the node** that breaches the latency SLO. This is the
> project's single new tool (Prometheus + Grafana). `make slo-up` brings the stack up, `make
> metrics-push` lands the metrics ($0, from the RunRecord), and `make slo-verify` proves it *from the
> store* (Prometheus + Grafana APIs, not a UI screen). Iter 3's Langfuse attribution
> (`make trace-base`/`make langfuse-verify`), iter 2's CI path-assertion gate (`make path-gate`), and
> iter 1's golden-set in MLflow (`make golden-upload`/`make golden-verify`) still stand. The quickstart
> heading names the last iteration it actually covers, as in the sibling projects.

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

## Quickstart (after iter 4 — agent FinOps guardrails: per-node SLO alerting + runtime budget controls)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use

# Route the smoke PA requests through the graph — replay mode, offline/$0.
# Prints one path per request; all three terminals + the retry-loop are exercised:
#   PA-smoke-002: classify → policy-check → request-info ↻1 → approve
make smoke

# Or a single request:
uv run python -m app.cli fixtures/requests-smoke.jsonl --id PA-smoke-002

make check                      # ruff + format + mypy + pytest — includes the path-assertion gate

# CI path-assertion gate: run the graph over the golden-set (replay/$0) and assert the *route*.
make path-gate                  # base pack — prints "expected vs actual path" table, exit 0 (green)
make path-gate-broken           # authored-broken policy-check → gate goes RED on route change (not a cassette-miss)

make up                         # control-plane backend (MLflow) at localhost:5051

# Trajectory golden-set → MLflow Evaluation Dataset (offline/$0, no LLM):
make golden-upload              # land the golden-set (idempotent — get-or-create + merge)
make golden-verify              # read it back FROM the store, print each request's expected path
make down                       # stop MLflow

# Per-node cost/latency attribution (Langfuse) — replay/$0, tracing opt-in via keys:
make obs-up                     # bring up the Langfuse stack (profile obs); UI at localhost:3001
make trace-base                 # replay the base pack WITH tracing → per-node spans in Langfuse
make langfuse-verify            # verify FROM the store: spans named by node, generation carries usage+cost
make down                       # stop everything (incl. the obs profile)

# Agent FinOps guardrails (iter 4) — replay/$0.
# Runtime budget controls: a squeezed budget turns the retry-loop into escalate, visible in the path:
make budget-demo                # AW_RUN_BUDGET_USD squeezed → "… → request-info ↻1 → escalate  [budget]"
#                                 (default budget leaves golden paths unchanged: make path-gate stays green)

# Per-node SLO alerting: push per-node metrics to Prometheus, Grafana alert rule names the slow node.
make slo-up                     # Prometheus (9090) + Pushgateway (9091) + Grafana (3002; admin/lite-password)
make metrics-push               # RunRecord → Pushgateway: per-node latency/cost + budget-escalation counter
make slo-verify                 # verify FROM the store: per-node series (Prometheus) + alert rule Firing (Grafana)
make down                       # stop everything (incl. the obs + slo profiles)
```

Make targets: `make check` (lint+types+tests, includes the path-gate), `make smoke` (run the smoke
fixture), `make path-gate`/`make path-gate-broken` (trajectory regression gate — green base pack /
red route-change demo), `make up`/`make down` (MLflow / everything), `make golden-upload`/`make
golden-verify` (trajectory golden-set in MLflow), `make obs-up` + `make trace-base` +
`make langfuse-verify` (per-node cost/latency attribution in Langfuse), `make budget-demo` (runtime
budget controls — squeezed budget routes the retry-loop to `escalate`), `make slo-up` + `make
metrics-push` + `make slo-verify` (per-node SLO alerting in Prometheus/Grafana),
`make author-cassettes`/`make author-broken-cassettes` (regenerate the $0 cassettes), `make test`,
`make fmt`.

`AW_LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit the provider and cost money — gated by an explicit go, as in the sibling
projects. All env vars go through `Settings` with the `AW_` prefix (see `.env.example`).
