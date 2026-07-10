# authwise-lite

A **trajectory-eval control plane** built over a deliberately narrow fixture: routing synthetic
Prior Authorization (PA) requests for a fictional payer (*Northfield Health*). The app is a
fixture; **path-level measurement is the product** — trajectory golden-set, CI path-assertion
gates, per-node cost/latency SLO, and path-distribution drift monitoring. See `CLAUDE.md`
(constitution) and `ROADMAP.md` (iteration backbone).

> **Status: iteration 3 closed** — **per-node cost/latency attribution**. Every request run is now a
> Langfuse trace whose spans are named after graph nodes (`classify`, `policy-check`, `decide`), with
> a per-node *generation* carrying the model, token usage, and our own USD cost from `llm-tiers.yaml`
> — so spend is attributed to the step of the agent, not the run as a whole (a retry-loop fires
> `policy-check` three times, and it shows). Wired through the LangGraph `CallbackHandler`, which
> enables Langfuse's **Agent Graph** view. Tracing is opt-in: only when both `AW_LANGFUSE_*` keys are
> set — by default (tests, CI, plain replay) it's a pure no-op and `langfuse` isn't even imported.
> `make obs-up` brings up the Langfuse stack, `make trace-base` replays the base pack into it ($0),
> and `make langfuse-verify` proves the attribution *from the store* (Langfuse API, not a UI screen).
> Iter 2's CI path-assertion gate (`make path-gate`) and iter 1's golden-set in MLflow
> (`make golden-upload`/`make golden-verify`) still stand. The quickstart heading names the last
> iteration it actually covers, as in the sibling projects.

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

## Quickstart (after iter 3 — per-node cost/latency attribution)

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
```

Make targets: `make check` (lint+types+tests, includes the path-gate), `make smoke` (run the smoke
fixture), `make path-gate`/`make path-gate-broken` (trajectory regression gate — green base pack /
red route-change demo), `make up`/`make down` (MLflow / everything), `make golden-upload`/`make
golden-verify` (trajectory golden-set in MLflow), `make obs-up` + `make trace-base` +
`make langfuse-verify` (per-node cost/latency attribution in Langfuse),
`make author-cassettes`/`make author-broken-cassettes` (regenerate the $0 cassettes), `make test`,
`make fmt`.

`AW_LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit the provider and cost money — gated by an explicit go, as in the sibling
projects. All env vars go through `Settings` with the `AW_` prefix (see `.env.example`).
