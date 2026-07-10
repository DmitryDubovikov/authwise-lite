# authwise-lite

A **trajectory-eval control plane** built over a deliberately narrow fixture: routing synthetic
Prior Authorization (PA) requests for a fictional payer (*Northfield Health*). The app is a
fixture; **path-level measurement is the product** — trajectory golden-set, CI path-assertion
gates, per-node cost/latency SLO, and path-distribution drift monitoring. See `CLAUDE.md`
(constitution) and `ROADMAP.md` (iteration backbone).

> **Status: iteration 2 closed** — a **CI path-assertion gate** now runs the graph over the golden
> pack (30 requests, replay/$0) and asserts each request's *route* — branch + retry-cycle count, not
> the answer text. It ships inside `make check` (so CI runs it), and `make path-gate` prints the
> "expected vs actual path" table. A deliberately broken policy-check cassette set
> (`make path-gate-broken`) turns the gate **red on a route change** — not a cassette-miss — proving
> it catches routing regressions. Iter 1's trajectory golden-set still lives in MLflow as a versioned
> Evaluation Dataset (`make golden-upload`/`make golden-verify`). The quickstart heading names the
> last iteration it actually covers, as in the sibling projects.

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

## Quickstart (after iter 2 — CI path-assertion gate)

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
```

Make targets: `make check` (lint+types+tests, includes the path-gate), `make smoke` (run the smoke
fixture), `make path-gate`/`make path-gate-broken` (trajectory regression gate — green base pack /
red route-change demo), `make up`/`make down` (MLflow), `make golden-upload`/`make golden-verify`
(trajectory golden-set in MLflow), `make author-cassettes`/`make author-broken-cassettes`
(regenerate the $0 cassettes), `make test`, `make fmt`.

`AW_LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit the provider and cost money — gated by an explicit go, as in the sibling
projects. All env vars go through `Settings` with the `AW_` prefix (see `.env.example`).
