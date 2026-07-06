# authwise-lite — рабочая конституция

> 🎯 **Цель проекта:** добавить в резюме то, чего нет в четырёх предыдущих, — **trajectory-eval:
> оценку пути многошагового агента, а не его финального ответа**. Минимальными затратами,
> **один-единственный новый инструмент на весь проект (Prometheus/Grafana — SLO-алертинг,
> iter 4)**, в остальном одна новая **техника** на итерацию, проверка по факту существования,
> **не по точности** PA-решений.

Это учебный pet-проект — **пятый сиблинг** семьи. Семья и оси:

- **policywise-lite** — *пассивный QA по статике* (vector/hybrid/rerank, LangGraph, eval, observability).
- **dossier-lite** — *активный агент, добывающий знание* (crew, browser, граф знаний, chat-UI).
- **sentiment-mlops** — *классический supervised MLOps* (MLflow/Prefect/DVC/Compose).
- **triagewise-lite** — *LLMOps control plane над **одним вызовом*** (registry, eval-gate, drift, FinOps).
- **authwise-lite** — **тот же control plane, но объект измерения — путь агента по графу.**

**Сдвиг сути (держим осознанно).** triagewise измеряет *ответ одного prompt-вызова*; authwise
измеряет *маршрут многошагового графа* — какая ветка сработала и сколько retry-циклов
прокрутилось. Девиз: **«приложение — фикстура, путь — продукт»**. Почти ни один инструмент не
нов (единственное исключение — Prometheus/Grafana, правило 2) — нова техника; поэтому потолок
итераций ниже triagewise (правило «нет нового инструмента → не нужен каркас на его освоение»),
а стек-строка резюме явно помечается как «то же оборудование, применённое к траектории».

---

## 🧵 Красная нить: что этот проект кладёт в резюме (north star)

> Это **главная цель и инвариант**. Каждая итерация обязана продвинуть хотя бы один пункт и не
> дать ему издрейфовать. Итерация, не двигающая красную нить, не нужна.

**Net-new ПРАКТИКИ (главное золото — их нет ни в одном сиблинге):**

1. **Agent trajectory evaluation** — зонтичный термин: eval пути, а не ответа.
2. **Trajectory-as-artifact** — golden-путь как версионируемый объект реестра (не только промпт).
3. **CI path-assertion gate / trajectory regression testing** — регрессия *маршрутизации* блокирует мёрдж.
4. **Per-node cost/latency SLO** — graph-level agent FinOps: атрибуция к ноде (Langfuse, iter 3)
   + SLO-алертинг (Prometheus/Grafana, iter 4).
5. **Runtime budget controls** — agent FinOps guardrail: retry-loop ограничен бюджетом рана,
   исчерпание бюджета — это **маршрут** (`escalate`), а не исключение; видно на уровне траектории.
6. **Path-distribution drift monitoring** — дрейф распределения веток, не качества ответа.
7. **Routing-policy as versioned artifact** — application-версия пинит версии промптов (iter 6).
8. **Continuous trajectory-eval loop** (опц. хвост) — промоушен routing-policy по gate на путь.

**Net-new ИНСТРУМЕНТЫ: ОДИН — Prometheus + Grafana (iter 4; решение 2026-07-06).** Пары нет ни
в одном сиблинге при максимальной частотности в вакансиях, а SLO без alert rule — просто лог.
Исключение единственное; всё остальное оборудование уже в портфолио и применяется к новому
объекту измерения — это по-прежнему позиционирование проекта.

**Что НЕ добавится — не дублировать в резюме (честность против раздувания):**
- LangGraph, LiteLLM, кассеты, tier-routing — уже **policywise/dossier**.
- MLflow Registry, promptfoo/DeepEval, OTel+Langfuse, Phoenix, Prefect, champion/challenger
  *как механика* — уже **triagewise/sentiment-mlops**.
- Eval *ответа*, LLM-as-judge, semantic caching — территория **policywise/triagewise**.

**Резюме-строки, к которым идём (формулировки фиксируем сейчас, чтобы не уплыли):**
- *«Built a trajectory-eval control plane for a multi-step LangGraph agent: a versioned
  trajectory golden-set and routing-policy versions pinning per-node prompt versions (MLflow),
  CI path-assertion gates that block merges on routing regressions (branch + retry-count), and
  path-distribution drift monitoring (Arize Phoenix).»*
- *«Attributed cost/latency SLOs to individual graph nodes (agent-level LLM FinOps) via
  OpenTelemetry — per-node dashboards in Langfuse, SLO alerting in Prometheus/Grafana — and
  enforced runtime budget controls: a cost-bounded retry loop with budget-exhaustion
  escalation.»*
- Стек-строка: `Agent trajectory evaluation · trajectory golden-set · CI path-assertion gates ·
  per-node cost/latency SLO · runtime budget controls · path-drift monitoring · LangGraph ·
  MLflow · Prometheus/Grafana · Arize Phoenix`

---

## Главные правила

1. **Existence-gate, не accuracy-gate.** Итерация готова, когда техника *работает и видна* **И**
   пункт красной нити стал демонстрируемым: golden-сет — версия в реестре; CI реально краснеет
   при регрессии маршрутизации; Grafana-алерт называет просевшую ноду; ужатый бюджет уводит
   retry-loop в `escalate`; Phoenix рисует дрейф веток.
   **Качество PA-решений — НЕ ворота.** Сознательный срез помечай `# aw-lite: <потолок> → <апгрейд>`.

   **Красная линия (что gate НЕ разрешает резать):** корректность демонстрируемой техники;
   направление зависимостей (правило 6); `PathTrace` как единственный источник истины ассертов;
   утечка секретов; **дисциплина LiteLLM (правило 5)**; сам факт продвижения красной нити.

2. **Один новый инструмент на весь проект (Prometheus/Grafana, iter 4); одна новая техника на
   итерацию.** Перенос каркаса из policywise (LangGraph, LiteLLM, кассеты) и triagewise (MLflow,
   promptfoo/DeepEval, OTel, Langfuse, Phoenix, Prefect) — не считается. Единственный новый
   инструмент получает **собственную итерацию-каркас** — то же правило «новый инструмент →
   каркас на освоение», работающее в обе стороны; второго исключения не будет. Новая техника
   обязана быть **не показанной ни в одном сиблинге** — иначе строчка резюме дублируется.

3. **Домен — фикстура.** Вымышленный payer **Northfield Health**, поток **Prior Authorization
   (PA)**-заявок (English product, Russian docs). **Граф заморожен после iter 0:**
   `classify → policy-check → decide{approve | request-info (retry-loop, ≤N) | escalate}`.
   LLM живёт в `classify` и `policy-check`; **ветвление `decide` — детерминированная функция над
   структурированным выходом policy-check и остатком бюджета рана** (budget controls, iter 4:
   retry-loop продолжается только при положительном остатке, исчерпание → `escalate`; дефолтный
   бюджет калиброван так, что golden-пути не меняются, — демо через ужатый бюджет в env). Путь
   воспроизводим в replay и атрибутируем к промпту policy-check. **Ширину заморозить:** новых
   веток и новых полей `PathTrace` не добавляем — масштаб числом заявок.

   **`PathTrace` (заморожен): `{branch, retry_cycles, nodes}`** — возвращается граф-раннером
   как значение вместе с ответом. **Golden-сет ~30 заявок:** запись = **список допустимых путей**
   (ассерт — membership); **≥80% записей — singleton** (= exact match), джокеры (объективно
   неоднозначные заявки) перечислены поимённо. Дизайн-контракт фикстуры: джокеры дают
   champion/challenger-гейту что различать; вторая («пострелизная») пачка заявок сдвигает
   распределение веток — мониторингу (iter 5) есть что ловить.

4. **Cost-дисциплина (cloud-only, OpenAI через тиры — как triagewise).** Тиры в
   `llm-tiers.yaml` (`cheap`/`mid`/`smart`), **ноды графа по умолчанию на `cheap`**; смена —
   env через `Settings`, не правка кода. **Снапшоты пиннить** (имя матчит `-\d{4}-\d{2}-\d{2}$`
   — пин-гейт из triagewise). Кассеты `replay` = **$0** и дефолт, **никогда не бьют в сеть**;
   `live`/`record` = деньги → **спросить перед прогоном с оценкой** (весь проект ≈ $1–3).

5. **Дисциплина LiteLLM (security — повтор triagewise, красная линия).** Только **SDK, НИКОГДА
   Proxy**. Один голый `acompletion`, без callbacks. Телеметрия off до первого вызова. Пиннинг
   версии + `uv.lock`. base_url/ключи только через `Settings`.

6. **Слои `app/`.** Транспорт (`cli`) — тонкий адаптер. Workflow (граф-раннер, eval-прогон,
   gate, промоушен) — не знает про драйвер реестра. Domain — чистые функции + схемы
   (`PathTrace`, golden-схема, сравнение путей, решение gate), без I/O. Persistence —
   MLflow-репозитории. `llm/` — поперечное (router/кассеты).

   **Швы (фиксируем один раз):** `domain/` не импортирует `app/*`; поток строго
   `transport → workflow → domain/persistence`; зависимости аргументами, без DI-фреймворка;
   реестр-хендл открывается на boundary; env — только `Settings`. **OTel-спаны (iter 3) — только
   наблюдаемость; источник истины для golden/CI-ассертов — `PathTrace` из domain, не телеметрия.**

7. **Eval-движок — не герой.** Ассерты пути — **pytest + membership-сравнение `PathTrace`**
   (рекомендация; финализация — `/iterationStart 2`, ROADMAP → Заметки); красная нить от движка
   не зависит. Новых eval-фреймворков не тащим: agentevals — отраслевая референс-точка, не
   зависимость; promptfoo/DeepEval уже показаны в triagewise/policywise.

8. **Наглядность — свойство финала, не итераций.** Итерации НЕ обязаны производить визуальные
   артефакты — но обязаны **не закрывать путь** к финальной витрине: выбирать реализации, чей
   результат в конце можно показать (пример: Langfuse подключается через LangGraph-интеграцию,
   иначе Agent Graph-вид недоступен). Материал витрины собирается один раз, при сборке
   финального showcase-README; чек-лист кадров — ROADMAP → «Витрина (финал)».

9. **Verify the store, not the UI.** Golden-версия — запросом к MLflow; alias-swap (iter 6) —
   тем же способом. UI — для витрины, не для доказательства.

10. **`jq` вместо `python3 -c`** для разбора JSON в shell.

11. **Коммиты:** автор — пользователь. Никогда не добавляй `Co-Authored-By: Claude`.

## Цикл итерации

`/iterationStart N` (спека → реализация → ревью-пайплайн → `/simplify`) → `/iterationClose N`
(церемония без правок кода: `make check` → доки → ROADMAP → стейдж + предложенный
commit-месседж) → пользователь коммитит. Каждая спека **цитирует строку «🧵 красная нить»** из
ROADMAP как цель итерации **и следует сквозным контрактам** (ROADMAP → «Сквозные контракты»:
форматы фикстур/кассет/`RunRecord`, семантика `PathTrace` и терминалов, бюджет в USD,
temperature=0, env-конвенция `AW_`) — локально переизобретать их нельзя.

## Что осознанно НЕ делаем

новые ветки/ноды графа (заморожен iter 0) · новые инструменты сверх единственного исключения
Prometheus/Grafana (правило 2 — позиционирование) ·
eval качества ответа / LLM-as-judge (triagewise) · semantic caching (triagewise) · мульти-агент
(dossier) · RAG (policywise) · fine-tuning / LoRA · **LiteLLM Proxy** (правило 5) · prod-deploy /
k8s · DVC (golden-путь и есть артефакт реестра — ROADMAP → Заметки) · собственные
accuracy-метрики PA-решений (existence-gate, не accuracy).

## Стек: развилки уже решены (2026-07-03)

- **OpenAI** (cloud, тиры + пиннинг — перенос triagewise 1-в-1).
- **LangGraph** — граф; паттерн policywise.
- **LiteLLM SDK-only** + кассеты record/replay — каркас policywise/triagewise.
- **MLflow, три уровня сущностей (решение «Г»):** (а) **trajectory golden-сет** — **MLflow
  Evaluation Dataset** (штатная сущность ≥3.4 для эталонов с expectations; sqlite-бэкенд
  поддерживается, пин MLflow ≥3.4) — артефакт iter 1; (б) **промпты `classify` и `policy-check`** — каждый
  версионируется в Prompt Registry **отдельно** (у каждого своя история); (в) **«routing-policy»**
  — версия приложения (LoggedModel), **пинящая конкретные версии обоих промптов** — штатный
  механизм MLflow 3 (`prompts=` при логировании / `set_active_model()`), не самодельный бандл.
  Alias `champion`/`challenger` вешаются на неё — **одну** сущность, swap атомарный. Iter 2
  ломает «во вред» промпт policy-check; iter 6 регистрирует, пинит и вручную свапает
  (**не** опц. — закрывает строку резюме про routing-policy); iter 7 (опц.) промоутит по
  расписанию. **Скоуп:** до iter 6 промпты живут в коде; регистрация + пиннинг + alias-загрузка —
  скоуп iter 6. **Fallback:** если механика LoggedModel в iter 6 окажется тяжёлой — деградация
  до alias на одном промпте policy-check, помеченная `# aw-lite:`.
- **`PathTrace` — first-class domain-объект**; OTel — не источник истины ассертов (правило 6).
- **Golden-семантика — membership + квота ≥80% singleton** (правило 3). Это отраслевая практика
  trajectory-eval: exact-match по эталонной траектории считается хрупким, фреймворки (Vertex,
  Strands, LangSmith) допускают multiple reference trajectories.
- **Движок path-ассертов — pytest + собственный membership-ассерт** (рекомендация; agentevals —
  отраслевой референс, не тащим; promptfoo — наиболее искусственный, понижен); финализация на
  `/iterationStart 2`. **Phoenix path-drift — проверено (2026-07-03):** Inferences
  (primary/reference) берёт категориальные колонки без эмбеддингов; легаси-уголок Phoenix —
  версию пиннить; fallback χ²/PSI остаётся (ROADMAP → Заметки).
- **Langfuse через LangGraph-интеграцию (callback handler)** — per-node атрибуция + Agent
  Graph-вид (iter 3; голый OTel структуру графа не рисует) · **Arize Phoenix** — path-drift
  (iter 5) · **Prefect** — опц. iter 7.
- **Prometheus + Grafana — единственный новый инструмент (решение 2026-07-06, iter 4):**
  per-node метрики (latency, cost, счётчик budget-эскалаций) + Grafana-дашборд + alert rule на
  SLO-порог. В replay латентность ~0 → демо алерта через ужатый порог; cost — из `usage`,
  сохранённого в кассетах (требование к формату кассет — iter 0). Способ экспорта метрик
  (prometheus-client vs OTel-экспортер) — деталь `/iterationStart 4`. Перекрытие с Langfuse
  осознанное: Langfuse = трейсинг/атрибуция, Prom/Grafana = SLO/алертинг.

**Не пересматривать без явного решения.**
