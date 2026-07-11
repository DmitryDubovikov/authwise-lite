# Итерация 06 — Routing-policy as versioned artifact (пиннинг промпт-версий)

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 06 материализует **саму маршрутизирующую конфигурацию агента как
> версионируемый артефакт реестра**: промпты обеих LLM-нод версионируются в MLflow Prompt
> Registry, а поверх них живёт версия приложения (routing-policy), которая **пинит конкретные
> версии обоих промптов**; alias `champion`/`challenger` указывают на эти версии, и ручной swap
> атомарно меняет, какая конфигурация «в проде». Новых инструментов нет — это штатный механизм
> MLflow 3, тот же стор, что держит golden-сет с iter 1.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. К iter 5 у ops-команды уже есть эталон путей,
CI-гейт против регрессий, per-node SLO, бюджет рана и мониторинг дрейфа трафика. Но одна вещь всё
ещё живёт «в коде»: **чем именно агент руководствуется, принимая решение о маршруте** — тексты
промптов classify и policy-check. Пока они хардкожены, «какая версия логики маршрутизации сейчас
работает» — вопрос к git-хешу, а не к реестру; нельзя показать «вот эта конфигурация — champion,
вот эта — challenger, я атомарно переключаю прод между ними, не трогая деплой». Ценность этой
итерации: маршрутизирующая политика становится **именованным версионируемым объектом в реестре** —
ops-инженер видит, какие версии промптов запинены в текущей политике, держит рядом
альтернативную (challenger) и **переключает прод одним swap alias**, а не выкаткой кода. Это
последний кусок контроля: не только *путь агента* под наблюдением, но и *конфигурация, которая
этот путь определяет*, — версионируется и переключается как артефакт.

## 🧵 Что это дало резюме

Пункт north-star №7 — **Routing-policy as versioned artifact** (application-версия пинит версии
промптов) — стал демонстрируемым, и им закрыта резюме-строка *«…routing-policy versions pinning
per-node prompt versions (MLflow)»*. Артефакт-доказательство: `make policy-verify` запросом к
MLflow API (правило 9) показывает `champion → pa-routing-policy v1 (pa-classify v1,
pa-policy-check v1)` и `challenger → v2 (…, pa-policy-check v2)`, `make policy-swap` атомарно
обменивает alias, а `AW_ROUTING_POLICY_ALIAS=champion make replay-base-champion` доказывает, что
запиненные шаблоны реально доезжают из реестра до нод графа, не меняя путей ($0, replay).

## TL;DR (простыми словами)

Было (после iter 5): весь контроль над *путём* агента есть, но тексты промптов, которые этот путь
определяют, зашиты в код — «какая версия маршрутизации в проде» нельзя спросить у реестра. Стало:
промпты обеих LLM-нод залиты в MLflow Prompt Registry как версионируемые объекты; поверх них
создана «routing-policy» — версия приложения, которая **пинит конкретные версии промптов**; две
таких версии (champion = промпты из кода, challenger = намеренно «сломанный» rubber-stamp
policy-check) висят под alias, и ручной swap атомарно меняет их местами. По умолчанию агент
по-прежнему берёт промпты из кода (CI и тесты остаются offline); alias-загрузка включается
опциональной env-переменной `AW_ROUTING_POLICY_ALIAS`. Всё в replay, $0 — новых записей кассет
итерация не потребовала.

## Что это за техника

**Двухуровневое версионирование маршрутизирующего приложения** (решение «Г» из `CLAUDE.md` →
Стек) — штатный механизм MLflow 3 для случая «у приложения несколько промптов, и надо
версионировать не каждый по отдельности, а их согласованный набор». Два уровня:

- **Нижний уровень — Prompt Registry.** Каждый промпт (`pa-classify`, `pa-policy-check`)
  версионируется **отдельно**, со своей историей: `register_prompt(name, template)` создаёт новую
  версию, `load_prompt("prompts:/<name>", version=N)` достаёт шаблон версии N. У policy-check две
  версии: v1 — текст из кода, v2 — **rubber-stamp** (challenger-фикстура, ниже).
- **Верхний уровень — routing-policy как external LoggedModel.** `create_external_model` создаёт
  версию приложения, в `params` которой записаны **пины** — какая версия какого промпта входит в
  эту политику (`{pa-classify: 1, pa-policy-check: 1}`); штатный `link_prompt_version_to_model`
  дополнительно фиксирует эти пины в теге `mlflow.linkedPrompts` (это и рисует связь в MLflow UI).
  У самого LoggedModel собственных alias нет, поэтому он регистрируется в Model Registry
  (`register_model("models:/<model_id>")`) — и уже на версиях registered model висят
  `champion`/`challenger`. Это штатный мост MLflow 3, не самодельный бандл.

Ключевые термины дальше по тексту:

- **routing-policy** — версия приложения (external LoggedModel + версия registered model поверх),
  пинящая конкретные версии обоих промптов. «Одна сущность под alias»: swap = переназначение двух
  alias на этой одной registered model, атомарно для каждого alias.
- **пин** — запись «эта политика использует ровно версию N промпта X»; хранится в двух местах
  (`params` LoggedModel и тег `mlflow.linkedPrompts`), и `resolve` кросс-чекает их согласованность.
- **rubber-stamp** — challenger-версия промпта policy-check: материализованный нарратив
  демо-регрессии iter 2 («ревьюер потерял критерии и штампует всё как sufficient»). Она — фикстура
  реестра, а не рантайм-промпт: живёт рядом с сидом, в модуль `prompts.py` не попадает.
- **PromptBundle** — пара шаблонов обеих нод одним объектом; дефолт — из кода (`CODE_BUNDLE`),
  alias-загрузка подставляет запиненные версии из реестра на boundary, и ноды графа разницы не видят.

## Поток данных

Здесь два независимых потока — **сид** (наполнить реестр) и **alias-загрузка** (взять из реестра в
рантайм), плюс **swap** как отдельная операция над alias.

**Сид.** Оператор набирает `make policy-seed`, чтобы материализовать политику в реестре. Скрипту
нужно, чтобы в сторе появились промпты, версии-политики и alias — но идемпотентно, без распухания
при повторе. Поэтому `seed_policy` не «создаёт», а **обеспечивает** (`ensure_*`): для каждого
промпта ищет версию с точно таким текстом и регистрирует новую, только если такой нет; для
политики ищет LoggedModel с ровно такими пинами; alias ставит, только если он ещё не разрешается —
и потому **не откатывает предыдущий swap**.

```
make policy-seed ─▶ scripts/policy_seed.py ─▶ app/workflow/policy.seed_policy()
   код-промпты ────────────────┐        (оркестрация: состав политики здесь)
   (prompts.py: CLASSIFY,      │              │ вызывает драйвер persistence ↓
    POLICY_CHECK) + rubber-     │              ▼
    stamp (policy.py)           │   app/persistence/routing_policy.py (единств. знает MLflow)
                                │     ensure_prompt_version  → Prompt Registry:
                                │        pa-classify v1, pa-policy-check v1 (код) + v2 (rubber-stamp)
                                │     ensure_policy_version   → external LoggedModel + пины (params)
                                │        + link_prompt_version_to_model (тег mlflow.linkedPrompts)
                                │     ensure_registered_version → Model Registry: pa-routing-policy v1, v2
                                ▼     _ensure_alias           → champion→v1, challenger→v2 (если ещё нет)
                          MLflow @ localhost:5051 (тот же стор, что golden-сет iter 1)
```

**Alias-загрузка.** Оператор хочет провести пачку **на промптах из реестра**, а не из кода, и
задаёт `AW_ROUTING_POLICY_ALIAS=champion` (env, контракт №7). CLI на boundary видит непустой alias,
резолвит его через MLflow (`champion → registered v1 → LoggedModel → пины → шаблоны из Prompt
Registry`), печатает загруженные версии и передаёт `PromptBundle` в ран через `config`. Workflow
драйвер реестра не знает (правило 6) — граф получает готовые шаблоны в `config["configurable"]`.

```
AW_ROUTING_POLICY_ALIAS=champion  ─▶  app/cli/main.py (boundary)
                                        │ settings.routing_policy_alias непусто
                                        ▼
                                  app/workflow/policy.load_bundle("champion")
                                        │ store.resolve → пины → templates из Prompt Registry
                                        ▼
                                  PromptBundle(classify=…, policy_check=…)
                                        │ run_batch(prompts=bundle) → config["configurable"]["prompts"]
                                        ▼
                                  ноды графа classify/policy-check .format(template) → replay-кассеты
                                  (кассеты ключуются (request_id, node, attempt), №4 → путь НЕ меняется)
```

**Swap.** `make policy-swap` вызывает `swap_policy`, который читает текущие версии обоих alias и
переставляет их местами двумя `set_alias`. Повторный swap возвращает исходное — это обмен, а не
промоушен-механика.

```
до swap:   champion → v1 (code policy-check)     после swap:  champion → v2 (rubber-stamp)
           challenger → v2 (rubber-stamp)                     challenger → v1 (code)
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| `scripts/policy_seed.py` (`make policy-seed`) | идемпотентный сид: промпты → версии-политики с пинами → alias | MLflow Prompt Registry + Model Registry |
| `app/persistence/routing_policy.py` | единственный драйвер MLflow: `ensure_*`, `resolve`, `set_alias` | MLflow @ localhost:5051 |
| `app/workflow/policy.py` | оркестрация: состав политики, rubber-stamp-фикстура, verify-семантика, swap | ничего (зовёт драйвер) |
| `scripts/policy_verify.py` (`make policy-verify`) | verify the store: alias→версия, пины, шаблоны запросом к MLflow | stdout (✅/❌ + exit-код) |
| `scripts/policy_swap.py` (`make policy-swap`) | ручной swap champion ↔ challenger | MLflow (переназначение двух alias) |
| `app/cli/main.py` (`make replay-base-champion`) | alias-загрузка на boundary: резолв → `PromptBundle` → граф | stdout (путь заявок) + `runs/base.jsonl` |

Честные оговорки. **Дефолт не изменился:** без `AW_ROUTING_POLICY_ALIAS` агент берёт промпты из
кода, CI-джоб и path-gate остаются offline и $0 — реестр им не нужен (это осознанный scope, iter 2
ломает промпт прямо в рабочем дереве). **Это не авто-промоушен:** swap ручной, никакого Prefect по
расписанию и re-eval challenger — тот хвост (iter 7) отменён (Заметки №7). **Существование, не
точность:** мы доказываем, что challenger *отличается* от champion (разный пин policy-check), а не
что он лучше/хуже — accuracy PA-решений не ворота (правило 1). **Swap не транзакционен** между
двумя `set_alias` — обрыв между вызовами оставит оба alias на одной версии; это помечено
`# aw-lite:`, ловится `verify_policy` и чинится повторным swap.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; надёжнее искать по именам символов.

1. **MLflow-драйвер routing-policy** — `app/persistence/routing_policy.py`. Единственное место,
   знающее про MLflow-механику двух уровней (правило 6); `tracking_uri` приходит аргументом с
   boundary. Все `ensure_*` идемпотентны — ищут существующую сущность по содержимому, прежде чем
   создавать, поэтому повторный сид не плодит версий. `ensure_prompt_version` регистрирует новую
   версию промпта, только если ни одна существующая не совпадает по тексту:

   ```python
   def ensure_prompt_version(name: str, template: str, *, tracking_uri: str) -> int:
       """Версия промпта с точно таким шаблоном; нет ни одной — регистрируется новая."""
       _connect(tracking_uri)
       latest = mlflow.genai.load_prompt(f"prompts:/{name}@latest", allow_missing=True)
       if latest is not None:
           for version in range(1, latest.version + 1):
               if mlflow.genai.load_prompt(name, version=version).template == template:
                   return version
       return mlflow.genai.register_prompt(name=name, template=template).version
   ```

2. **`resolve` — alias → пины → шаблоны, с кросс-чеком** — `app/persistence/routing_policy.py:108`.
   Идёт по цепочке `alias → версия registered model → LoggedModel → пины → шаблоны из Prompt
   Registry` и возвращает `ResolvedPolicy` (frozen dataclass). Здесь же — драйверное знание о двух
   кодировках пина: `params` LoggedModel и штатный тег `mlflow.linkedPrompts` должны совпадать,
   расхождение — `ValueError` (стор неконсистентен, а не «не засеян»). Отсутствующий alias —
   `None` (не исключение), чтобы verify отличил «не засеян» от «сломан»:

   ```python
   pins = {name: int(v) for name, v in (model.params or {}).items()}
   linked = {
       entry["name"]: int(entry["version"])
       for entry in json.loads(model.tags.get("mlflow.linkedPrompts", "[]"))
   }
   if linked != pins:
       raise ValueError(f"… linkedPrompts {linked} расходится с params {pins}")
   templates = {
       name: mlflow.genai.load_prompt(name, version=v).template for name, v in pins.items()
   }
   ```

3. **Оркестрация сида и rubber-stamp-фикстура** — `app/workflow/policy.py`. Состав политики
   (какие промпты, какие пины champion/challenger) живёт здесь, драйвер MLflow — нет (правило 6).
   `seed_policy` собирает всё из примитивов persistence; `_ensure_alias` ставит alias только если
   он ещё не разрешается — **это и есть «повторный сид не откатывает swap»**:

   ```python
   def _ensure_alias(alias: str, version: int, tracking_uri: str) -> bool:
       """Ставит alias, только если он ещё не разрешается: повторный сид не откатывает swap."""
       if store.alias_version(alias, tracking_uri=tracking_uri) is not None:
           return False
       store.set_alias(alias, version, tracking_uri=tracking_uri)
       return True
   ```

   Rubber-stamp-промпт (`POLICY_CHECK_PROMPT_RUBBER_STAMP`, `app/workflow/policy.py:19`) —
   материализованный «сломанный» policy-check нарратива iter 2: критерии `missing_info`/
   `out_of_policy` выброшены, ревьюеру велено доверять документации. Он challenger-фикстура, не
   рантайм-промпт, поэтому живёт в модуле сида, а не в `prompts.py`.

4. **`verify_policy` — семантика проверки стора** — `app/workflow/policy.py:105`. Разрешает оба
   alias и складывает структурные, инвариантные к swap проверки: обе роли резолвятся консистентно
   (кросс-чек пинов делает сам `resolve`), политики разделяют версию classify и различаются по
   policy-check (иначе challenger не отличается). Транспорт `policy_verify.py` только печатает
   результат — семантики в нём нет (правило: verify запросом к стору):

   ```python
   if champion.registered_version == challenger.registered_version:
       problems.append("champion и challenger указывают на одну версию routing-policy")
   if champion.prompt_versions.get(PROMPT_POLICY_CHECK) == challenger.prompt_versions.get(
       PROMPT_POLICY_CHECK
   ):
       problems.append("политики пинят один policy-check — challenger не отличается")
   ```

5. **`swap_policy` — ручной обмен alias** — `app/workflow/policy.py:143`. Composed из
   alias-примитивов persistence, симметрично сиду. Явно помеченный `# aw-lite:` осознанный срез:
   пара переназначений не транзакционна, но `verify_policy` это ловит, а повторный swap чинит:

   ```python
   # aw-lite: пара переназначений не транзакционна (обрыв между вызовами оставит оба alias
   # на одной версии) → verify_policy это ловит, повторный policy-swap чинит
   store.set_alias(store.CHAMPION, challenger, tracking_uri=tracking_uri)
   store.set_alias(store.CHALLENGER, champion, tracking_uri=tracking_uri)
   ```

6. **`PromptBundle` и alias-загрузка на boundary** — `app/workflow/prompts.py:36` (`PromptBundle`,
   `CODE_BUNDLE`) и `app/cli/main.py:23-35`. Промпты нод стали параметром: `classify_messages`/
   `policy_check_messages` принимают `template` обязательным аргументом (молчаливого фолбэка мимо
   бандла нет), единственный владелец дефолта «из кода» — `run_pa_request` (`CODE_BUNDLE` на
   boundary, `app/workflow/graph.py:190`). CLI резолвит alias лениво — импорт `mlflow` локальный,
   чтобы дефолтный offline-путь оставался быстрым:

   ```python
   if settings.routing_policy_alias:
       from app.workflow.policy import describe_pins, load_bundle
       prompts, resolved = load_bundle(
           settings.routing_policy_alias, tracking_uri=settings.mlflow_tracking_uri
       )
       print(f"routing-policy: {resolved.alias} → v{resolved.registered_version} "
             f"({describe_pins(resolved)})")
   ```

7. **Настройка, таргеты, тесты** — `Settings.routing_policy_alias` (`app/config.py:56`, дефолт
   пуст = offline); Make-таргеты `policy-seed`/`policy-swap`/`policy-verify`/`replay-base-champion`
   (`Makefile:64-75`); тесты `tests/test_policy.py` (6 штук на герметичном sqlite-сторе во
   временном каталоге, offline/$0): идемпотентность сида и не-откат swap, champion пинит
   код-промпты а challenger rubber-stamp, обмен alias с восстановлением, `resolve` отсутствующего
   alias → `None`, и — доказательство, что бандл реально доезжает до нод — `PromptBundle` с
   неизвестным плейсхолдером роняет `classify` через `KeyError`.
