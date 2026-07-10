# Итерация 03 — Per-node cost/latency attribution (Langfuse)

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 03 добавляет к пути **экономику по нодам**: каждый прогон заявки становится
> трейсом в Langfuse, где стоимость и задержка привязаны к **конкретной ноде графа** (classify /
> policy-check), а не к рану целиком. Видно, во что обходится каждый шаг агента — и что retry-loop
> на policy-check дороже одиночного прохода.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. К iter 2 у команды уже есть эталон путей в
реестре и гейт, который краснит CI при регрессии маршрутизации. Но пока никто не видит **цену**
этих маршрутов: агент ходит по графу, тратит токены на каждом шаге — а счёт приходит один, на весь
ран. Ценность именно этой итерации в том, что теперь стоимость и задержка **разложены по шагам
агента**: ops-инженер открывает трейс заявки и видит, что policy-check с двумя retry-циклами
прокрутил LLM три раза и стоил втрое дороже classify. Это фундамент agent-level FinOps: чтобы
ставить SLO на ноду и ловить, какой именно шаг просел (iter 4), сначала нужно измерять по ноде, а
не по рану. Для payer'а это разница между «агент в этом месяце стоил $X» и «дороже всего нам
обходятся заявки, уходящие в retry-loop на policy-check, — вот на сколько».

## 🧵 Что это дало резюме

Пункт north-star iter 3 — **Per-node cost/latency attribution (graph-level LLM FinOps: измерение)**
— стал демонстрируемым. Доказательство: `make trace-base` прогоняет базовую пачку в replay ($0) и
пишет в Langfuse трейс на заявку, где **спан назван именем ноды графа**, а внутри LLM-нод лежит
generation с моделью, usage и **нашей** стоимостью из `llm-tiers.yaml`. `make langfuse-verify`
подтверждает это **запросом к Langfuse API** (правило 9, не скрин UI): в свежем трейсе спаны
атрибутированы по нодам, generation вложен в спан своей ноды и несёт usage+cost. Подключение —
через LangGraph `CallbackHandler`, что включает Langfuse **Agent Graph**-вид (голый OTel структуру
графа не рисует) — кадр для финальной витрины.

## TL;DR (простыми словами)

Было (после iter 2): граф ходит по маршрутам, гейт стережёт сам маршрут, но во что каждый шаг
обходится — не видно. Стало: подключили Langfuse как приёмник трейсов и **атрибутировали
cost/latency к ноде графа**. Теперь прогон заявки — это трейс с деревом спанов: корень → спан
`classify` → спан `policy-check` (столько раз, сколько было retry-циклов) → спан `decide`, а внутри
LLM-нод — «generation» с моделью, числом токенов и стоимостью в долларах. Цену считает **одна наша
domain-функция** `cost_usd` из цен в `llm-tiers.yaml`, автоинференс цен Langfuse не используем.
Трейсинг включается **только когда заданы оба ключа** `AW_LANGFUSE_*` — по умолчанию (тесты, CI,
обычный replay) это чистый no-op: langfuse даже не импортируется, сервер не нужен. Заодно закрыли
отложенный из iter 2 контракт №3: `RunRecord`/JSONL теперь несёт per-node usage/latency (`node_stats`)
— его будут читать Prometheus (iter 4) и Phoenix (iter 5).

## Что это за техника

**Per-node attribution (атрибуция по ноде графа)** — это привязка метрик (стоимость, задержка,
токены) не к рану целиком, а к отдельному шагу агента. В обычном трейсинге LLM-приложения ты
видишь «этот запрос стоил $Y»; per-node attribution показывает «из них $A ушло в classify, $B — в
policy-check, причём policy-check дёрнулся три раза». Это первый (измерительный) кирпич
graph-level LLM FinOps: без разбивки по нодам нельзя поставить SLO на конкретный шаг (iter 4).

Мы собрали это на **уже имеющемся** стеке нулём новых техник-изобретений — Langfuse перенесён из
triagewise, ново только *подключение через LangGraph-интеграцию* и *объект атрибуции — нода графа*:

- **Langfuse `CallbackHandler`** — это готовый мост LangGraph→Langfuse: передаёшь handler в
  `config={"callbacks": [...]}` при запуске графа, и он сам заводит корень трейса и **спан на каждую
  ноду**. Почему именно handler, а не голый OTLP (как в policywise): только handler включает
  Langfuse **Agent Graph**-вид — картинку графа с реально пройденным маршрутом. Голый OTel рисует
  плоский список спанов, структуру графа не восстанавливает.
- **generation-спан** — в семантике Langfuse это спан именно LLM-вызова (с моделью, usage, cost),
  в отличие от обычного спана-«ноды». Тонкость нашего графа: LLM-вызов спрятан внутри `route()`
  (наш единственный шов к LiteLLM), куда handler не дотягивается. Поэтому generation создаёт **сам
  `route()`** через контекст-менеджер `tracing.generation(...)`; OTel-контекст Langfuse v3
  автоматически вкладывает этот generation **под спан текущей ноды** — так и получается атрибуция.
- **`cost_usd`** — чистая domain-функция `usage × цена_тира` (сквозной контракт №5). Цену пишем
  **явно** в generation (`cost_details`), а не отдаём Langfuse считать по её собственной таблице
  моделей: один источник цен на весь проект — `llm-tiers.yaml`. Ту же функцию в iter 4 использует
  Prometheus/SLO-расчёт.

Ключевые термины, которыми оперируем дальше:
- **трейс** — дерево спанов одного прогона заявки (корень + ноды + generation'ы).
- **спан ноды** — отрезок трейса, названный именем ноды графа (`classify`, `policy-check`,
  `decide`); его заводит handler. В типах Langfuse это `CHAIN` (LangChain-семантика).
- **generation** — вложенный в спан ноды отрезок LLM-вызова с usage и cost; его заводит `route()`.
- **`node_stats`** — per-node запись `{node, attempt, usage, latency_ms}`, которую ноды собирают в
  стейт графа; попадает в `RunRecord`/JSONL (контракт №3). Это **не** телеметрия — это domain-данные
  для потребителей iter 4/5; источник истины путей по-прежнему `PathTrace` (правило 6).
- **no-op-гейт трейсинга** — при отсутствии ключей `tracing.*` возвращают пустышки, langfuse не
  импортируется. Тот же приём, что lazy-import LiteLLM в replay: выключенная фича не тянет свой SDK.

## Поток данных

Оператор хочет прогнать базовую пачку и увидеть, во что обходится каждый шаг агента, и запускает
`make trace-base` (это `python -m app.cli fixtures/requests-base.jsonl` с выставленными ключами
`AW_LANGFUSE_*`). Дальше цепочка такая. Чтобы трейсинг вообще включился, `run_pa_request` на
boundary спрашивает `tracing.langgraph_handler(settings)` — тот вернёт `CallbackHandler`, только
если оба ключа заданы (иначе `None` и весь трейсинг — no-op). Handler кладётся в `config["callbacks"]`
и передаётся в граф; при прогоне он заводит корень трейса и спан на каждую посещённую ноду. Внутри
LLM-нод граф зовёт `route()`, а тот оборачивает сам вызов LiteLLM в `tracing.generation(node, tier)`
— generation-спан с usage и cost, который OTel-контекст вкладывает под спан текущей ноды. Спаны
батчатся SDK и уходят в Langfuse; на границе пачки `run_batch` зовёт `tracing.flush()`, чтобы дожать
батч перед выходом короткоживущего CLI-процесса. Проверяем не UI, а стор: `make langfuse-verify`
дёргает Langfuse public API и утверждает, что в свежем трейсе спаны названы нодами, а generation'ы
вложены в свои ноды и несут usage+cost.

```
make trace-base  (AW_LANGFUSE_* заданы)
      │
      ▼
app.cli → run_batch → run_pa_request(request)          [app/workflow/runner.py, graph.py]
      │        │
      │        ├─ tracing.langgraph_handler(settings) ──► CallbackHandler | None
      │        │        (None ⟺ ключей нет ⟺ трейсинг no-op)
      │        │
      │        └─ _GRAPH.ainvoke(state, config={"callbacks": [handler]})
      │                 │
      │                 ├─ node classify   ─┐ handler: спан "classify"
      │                 │    └─ route() ──► tracing.generation("classify", tier) ─► generation (usage+cost)
      │                 ├─ node policy-check ┐ handler: спан "policy-check" (×N retry)
      │                 │    └─ route() ──► tracing.generation("policy-check", tier) ─► generation
      │                 └─ node decide       ┘ handler: спан "decide"  (чистая функция, LLM нет)
      │
      ├─ tracing.flush()  ──► дожать батч SDK ──► Langfuse (pg + clickhouse + s3)
      │
      └─ (на выходе) каждая нода вернула node_stats{node,attempt,usage,latency_ms} в стейт
                     │
                     ▼
             RunRecord.node_stats  ──► runs/base.jsonl (пишет make path-gate; читают iter 4/5)

make langfuse-verify ──► Langfuse public API ──► спаны=ноды? generation вложен в свою ноду? usage+cost есть? ──► ✅/❌
```

Cost считает `cost_usd` (domain), НЕ Langfuse:

```
usage (из кассеты) ──► cost_usd(usage, input_per_1m, output_per_1m) ──► generation.cost_details["total"]
                                    ▲
                      цены тира из llm-tiers.yaml (один источник на проект)
```

Честные оговорки — что в этой итерации **не** происходит:
- **SLO и алертов ещё нет.** Здесь только *измерение* по нодам (attribution). Пороги, алерт-правила
  и Grafana — скоуп iter 4 (Prometheus/Grafana, единственный новый инструмент проекта). Langfuse
  тут = трейсинг/атрибуция; Prom/Grafana там = SLO/алертинг — перекрытие осознанное.
- **Латентность в replay ≈ 0.** Кассеты читаются с диска за микросекунды (`latency_ms` в JSONL —
  сотые доли мс). Это ожидаемо: replay = $0 и мгновенно. Осмысленные абсолютные задержки будут при
  live-прогонах; для существования атрибуции достаточно, что поле есть и привязано к ноде. Демо
  SLO-алерта в iter 4 обойдёт это ужатым порогом.
- **Cost считаем мы, не Langfuse.** Автоинференс цен Langfuse по её таблице моделей **выключен** —
  цену пишем явным `cost_details` из `llm-tiers.yaml`. Один источник цен на весь проект; резюме-строка
  «per-node cost» остаётся честной (число из нашего прайс-листа, а не из чужой таблицы).
- **`PathTrace` не тронут (заморожен, правило 3).** Per-node usage/latency живут **рядом**, в
  `node_stats`, не внутри `PathTrace`. Трейсинг — только наблюдаемость; golden/CI-ассерты
  по-прежнему сверяют `PathTrace` из domain, а не спаны (правило 6). Поэтому в CI трейсинг выключен.

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `tracing.langgraph_handler` (`app/llm/tracing.py`) | заводит `CallbackHandler` при наличии ключей; иначе `None` | — (возвращает handler в `run_pa_request`) |
| Langfuse `CallbackHandler` | корень трейса + спан на каждую ноду графа + Agent Graph-вид | Langfuse (async batch → worker → pg/clickhouse) |
| `tracing.generation` в `route()` (`app/llm/router.py`) | generation-спан вокруг LLM-вызова; usage+cost по ноде | вкладывается под спан ноды (OTel-контекст) |
| `cost_usd` (`app/domain/cost.py`) | чистая математика `usage × цена тира` | возвращает USD → `cost_details` generation'а |
| `node_stats` в нодах (`app/workflow/graph.py`) | собирают `{node,attempt,usage,latency_ms}` в стейт | → `RunRecord`/`runs/*.jsonl` (контракт №3) |
| `scripts/langfuse_verify.py` + `make langfuse-verify` | verify the store: запрос к Langfuse API, ассерт атрибуции по нодам | stdout + exit-код |
| docker-compose профиль `obs` + `make obs-up` | поднимает Langfuse-стек (web/worker/pg/clickhouse/redis/minio) | named volumes (переживают `down`) |

## Слои и направление зависимостей

Трейсинг лёг поперечным слоем `llm/`, не нарушив швы правила 6: `domain/cost.py` остаётся чистой
математикой, а весь Langfuse-код заперт в `llm/tracing.py`, откуда его зовут только `route()` и
boundary раннера.

```
transport   app/cli/main.py ─┐   scripts/langfuse_verify.py ─┐      (тонкие адаптеры)
                             │                                │
workflow    run_batch / run_pa_request (runner.py, graph.py) │  ── handler на boundary, flush на границе пачки
                 │           │            │                   │
llm (cross) route() ──uses──► tracing.generation / langgraph_handler / flush  (app/llm/tracing.py)
                                          │                                       │ lazy import langfuse
domain      cost_usd (app/domain/cost.py) ◄── uses ── tracing (единственный вызов domain из трейсинга)
            PathTrace (app/domain/path.py) ◄── источник истины ассертов; трейсинг его НЕ трогает
```

`app/domain/` по-прежнему не импортирует ничего из `app/*` — `cost_usd` берёт цены аргументами.
`tracing.py` импортирует `domain.cost` и `Settings`, но `domain` про трейсинг не знает. Langfuse
(`from langfuse import ...`) импортируется **только** внутри функций `tracing.py` и только при
включённых ключах — выключенный трейсинг SDK не тянет.

## Карта «где в коде»

> Номера строк — ориентир на момент закрытия iter 3; надёжнее искать по именам символов.

1. **`cost_usd` — единственная функция стоимости (контракт №5)** — `app/domain/cost.py:10`. Чистая
   функция без I/O: цены приходят аргументами (из `llm-tiers.yaml` через `llm/tiers.py`), на выходе
   USD. `None` на входе usage → `None` на выходе (ответ без usage — атрибутировать нечего).
   Потребители — трейсинг (здесь) и Prometheus/SLO (iter 4): цену на всём проекте считает **одна**
   функция.

   ```python
   def cost_usd(
       usage: Mapping[str, Any] | None, *, input_per_1m: float, output_per_1m: float
   ) -> float | None:
       """Стоимость LLM-вызова в USD; None — ответ без usage (нечего атрибутировать)."""
       if usage is None:
           return None
       return (
           usage.get("prompt_tokens", 0) * input_per_1m
           + usage.get("completion_tokens", 0) * output_per_1m
       ) / 1_000_000
   ```

2. **`Tier` носит цены токенов** — `app/llm/tiers.py:13`. К модели тира добавлены `input_per_1m` /
   `output_per_1m` (USD за 1M токенов), парсятся из `llm-tiers.yaml` рядом с моделью. Пин-гейт
   снапшота (имя модели матчит `-YYYY-MM-DD$`) остаётся. `resolve_model` переименован в
   `resolve_tier` — теперь потребителю нужна не только модель, но и цены (шов в `route()`).

   ```python
   class Tier(BaseModel):
       model: str
       input_per_1m: float  # USD за 1M input-токенов
       output_per_1m: float  # USD за 1M output-токенов
   ```

3. **`tracing.generation` — generation-спан вокруг LLM-вызова** — `app/llm/tracing.py:40`.
   Контекст-менеджер: при выключенном трейсинге отдаёт no-op `record` и не трогает langfuse; при
   включённом — открывает `start_as_current_generation(name=node, model=...)` (имя = нода → дашборд
   бьёт cost по нодам) и отдаёт `record(usage)`, который пишет `usage_details` и **наш**
   `cost_details` через `cost_usd`. OTel-контекст сам вложит generation под спан текущей ноды.

   ```python
   @contextmanager
   def generation(node: str, tier: Tier, settings: Settings) -> Iterator[Recorder]:
       if not enabled(settings):
           yield lambda usage: None
           return
       with _client(settings).start_as_current_generation(name=node, model=tier.model) as gen:
           def record(usage: dict[str, Any] | None) -> None:
               if usage is None:
                   return
               gen.update(
                   usage_details={"input": usage.get("prompt_tokens", 0),
                                  "output": usage.get("completion_tokens", 0)},
                   cost_details={"total": cost_usd(usage, input_per_1m=tier.input_per_1m,
                                                   output_per_1m=tier.output_per_1m)},
               )
           yield record
   ```

4. **`enabled` / `langgraph_handler` / `flush` — гейт трейсинга и мост LangGraph** —
   `app/llm/tracing.py:23`, `:68`, `:79`. `enabled` — оба ключа заданы. `langgraph_handler` при
   включённых ключах инициализирует синглтон Langfuse **нашими** ключами (иначе handler взял бы их
   из env как попало) и возвращает `CallbackHandler` — только он даёт Agent Graph-вид. `flush`
   дожимает батч-экспортер перед выходом CLI. Все три — no-op без ключей, `from langfuse import ...`
   спрятан внутрь (lazy).

   ```python
   def langgraph_handler(settings: Settings) -> Any | None:
       if not enabled(settings):
           return None
       _client(settings)  # инициализировать синглтон нашими ключами до создания handler'а
       from langfuse.langchain import CallbackHandler
       return CallbackHandler()
   ```

5. **`route()` — generation-шов и замер латентности** — `app/llm/router.py:37`. Вызов LLM (replay
   или live) обёрнут в `tracing.generation(...)`; сразу после ответа зовётся `record(usage)`.
   Латентность меряется здесь же (`time.perf_counter`) и едет в `LLMReply.latency_ms` → `node_stats`
   (контракт №3). Это шов **Langfuse**, а НЕ callback LiteLLM (правило 5: LiteLLM без callbacks).

   ```python
   with tracing.generation(node, tier_spec, settings) as record:
       start = time.perf_counter()
       if settings.llm_mode == "replay":
           cassette = cassettes.load(path)
           content, usage = cassette.content, cassette.usage
       else:
           content, usage = await _live_completion(tier_spec.model, messages, settings)
       latency_ms = (time.perf_counter() - start) * 1000
       record(usage)
   ```

6. **`node_stats` в нодах графа + wiring handler'а на boundary** — `app/workflow/graph.py:63`
   (classify), `:84` (policy-check), `:145` (`run_pa_request`). Каждая LLM-нода возвращает
   `NodeStat(node, attempt, usage, latency_ms)` в аккумулируемое поле стейта; `run_pa_request`
   вешает handler в `config["callbacks"]`, только если он не `None`. `PathTrace` не трогается —
   usage/latency живут рядом.

   ```python
   handler = tracing.langgraph_handler(settings)  # None — трейсинг выключен (дефолт)
   if handler is not None:
       config["callbacks"] = [handler]
   ```

7. **`RunRecord.node_stats` + JSONL (контракт №3, отложен из iter 2)** — `app/workflow/runner.py:20`,
   `_to_dict`/`_from_dict`. `RunRecord` получил `node_stats` рядом с `trace`; `run_batch` зовёт
   `tracing.flush()` на границе пачки; сериализация пишет per-node usage/latency в `runs/*.jsonl`.
   Именно этот артефакт в iter 4/5 читают Prometheus и Phoenix.

   ```python
   @dataclass(frozen=True)
   class RunRecord:
       request_id: str
       trace: PathTrace  # источник истины golden/CI-ассертов (правило 6)
       node_stats: tuple[NodeStat, ...]  # per-node usage/latency (контракт №3), не ассертится
   ```

8. **`scripts/langfuse_verify.py` — verify the store (правило 9)** — `scripts/langfuse_verify.py:31`.
   Берёт свежий трейс через Langfuse public API и ассертит атрибуцию: все ноды графа присутствуют
   спанами; по каждой LLM-ноде есть generation; **generation вложен в спан своей одноимённой ноды**
   (а не висит на run целиком); у каждого generation есть usage и cost. Доказательство — из стора,
   не из UI.

   ```python
   # сама атрибуция: generation вложен в спан ОДНОИМЁННОЙ ноды, а не висит на run целиком
   orphans = [
       g["name"] for g in generations if name_by_id.get(g["parentObservationId"]) != g["name"]
   ]
   if orphans:
       problems.append(f"generation не вложен в спан своей ноды: {orphans}")
   ```

9. **Compose-профиль `obs` + Makefile + Settings** — `docker-compose.yml` (сервисы `langfuse-*` под
   `profiles: ["obs"]`), `Makefile` (`obs-up`/`obs-down`, `trace-base`, `langfuse-verify`,
   константа `LANGFUSE_KEYS = pk-aw/sk-aw`), `app/config.py:30` (`langfuse_host` = `http://localhost:3001`,
   `langfuse_public_key`/`secret_key`). Ключи детерминированы через `LANGFUSE_INIT_*` в compose —
   трейсинг и verify знают креды заранее, без клика в UI. Порт 3001: 3000 занят Langfuse сиблинга
   policywise. `conftest.py` жёстко гасит ключи в тестах — трейсинг в тестах всегда no-op.
