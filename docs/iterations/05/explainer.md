# Итерация 05 — Path-distribution drift monitoring (PSI + Prometheus/Grafana)

> 🎯 **Цель проекта:** trajectory-eval — оценка *пути* многошагового агента, а не его финального
> ответа. Итерация 05 добавляет **мониторинг дрейфа распределения маршрутов**: появляется
> «пострелизная» пачка заявок с честно сдвинутым трафиком, чистая domain-функция PSI измеряет,
> насколько распределение веток (`approve`/`request-info`/`escalate`) уехало от эталонного, а
> Grafana показывает обе пачки рядом и поднимает алерт по отраслевому порогу PSI > 0.2 — **без
> ужимания порога под демо**. Новых инструментов нет: всё едет по Prometheus/Grafana-рельсам
> iter 4.

## Зачем это (продукт и ценность)

Продукт (фикстура, но описываем как настоящий): payer **Northfield Health** маршрутизирует поток
Prior-Authorization-заявок — одобрить, дозапросить документы или эскалировать человеку — и держит
**сам маршрут** агента под операционным контролем. К iter 4 у ops-команды есть эталон путей, CI-гейт
против регрессий маршрутизации и FinOps-предохранители. Но всё это стережёт *агента*; никто не
стережёт *трафик*. А трафик живёт своей жизнью: страховой рынок накрывает волна заявок на
GLP-1-препараты для снижения веса (план их не покрывает → `escalate`), врачи начинают подавать
заявки наспех, без документов, которые дозапрос не спасает. Агент при этом работает **правильно** —
CI зелёный, SLO в норме — но доля заявок, уходящих к живым ревьюерам, тихо растёт, и штат перестаёт
справляться. Ценность этой итерации: ops-инженер получает **сигнал о сдвиге состава маршрутов** —
дашборд, где эталонное и текущее распределение веток стоят рядом, и алерт, который срабатывает,
когда сдвиг превышает отраслевой порог. Это ловит проблему, которую не поймает ни один гейт на
корректность: агент не сломался — **изменился мир вокруг него**.

## 🧵 Что это дало резюме

Пункт north-star №6 — **Path-distribution drift monitoring** (дрейф распределения веток, не
качества ответа) — стал демонстрируемым, и им закрыта последняя строка резюме-формулировки
*«…and path-distribution drift monitoring with PSI-based alerting (Prometheus/Grafana)»*.
Артефакты-доказательства: `make drift-push` печатает таблицу долей веток base vs post и
**PSI = 0.583** (сдвиг настоящий: 73/13/13 → 37/27/37), а `make drift-verify` запросом к
Prometheus и Grafana API (правило 9) подтверждает, что серии обеих пачек скрейпятся и alert rule
`Path-distribution drift (PSI)` в состоянии **Firing** при неужатом отраслевом пороге 0.2.

## TL;DR (простыми словами)

Было (после iter 4): агент под полным контролем — эталон путей, CI-гейт, per-node SLO, бюджет
рана, — но если изменится сам поток заявок, никто этого не заметит. Стало: есть вторая,
«пострелизная» пачка из 30 заявок с намеренно сдвинутым сюжетом (волна weight-loss-препаратов и
недооформленных заявок), одна формула (PSI) сравнивает распределение веток этой пачки с
эталонной, и если сдвиг значимый — в Grafana загорается алерт. Добавили два кусочка: чистую
функцию PSI в domain-слое и скрипт-пуш долей веток в уже стоящий Prometheus. Всё в replay, $0
(запись кассет новой пачки стоила ≈$0.01 — одобрено).

## Что это за техника

**Path-distribution drift monitoring** — это мониторинг сдвига *распределения маршрутов* агента
между двумя срезами трафика: эталонным (reference) и текущим (primary). В отличие от дрейфа
качества ответа или дрейфа эмбеддингов (территория triagewise), здесь объект категориальный —
доли трёх терминальных веток графа. Задача в этой итерации — заметить, что «пострелизный» трафик
уводит заявки в `escalate`/`request-info` чаще, чем эталонный, и превратить это в алерт.

**PSI (Population Stability Index)** — отраслевая метрика сдвига распределения:
`Σ (pᵢ − rᵢ) · ln(pᵢ / rᵢ)` по бинам, где `rᵢ` — доля бина в reference, `pᵢ` — в primary.
Конвенция порогов: меньше 0.1 — сдвига нет, 0.1–0.2 — умеренный, больше 0.2 — значимый. Бины у
нас — три терминала графа, поэтому нулевая доля реальна (ветка может не встретиться в пачке
вовсе) и сглаживается малым ε, чтобы логарифм не улетал в бесконечность.

Термины дальше по тексту: *reference/primary* — роли сравниваемых пачек (эталон и текущая);
*«пострелизная» пачка* (`post`) — 30 синтетических заявок, сюжетно сдвинутых относительно базовой;
*RunRecord* — артефакт батч-прогона (контракт №3): JSONL с `PathTrace` и per-node usage/latency
каждой заявки, который потребители читают вместо повторного прогона графа.

## Поток данных

Оператор хочет сравнить «пострелизный» трафик с эталонным. Сначала обоим сравниваемым срезам
нужны артефакты прогона: `make replay-post` гонит 30 заявок `fixtures/requests-post.jsonl` через
граф по кассетам `cassettes/post/` (LLM не зовётся, $0) и пишет `runs/post.jsonl`; эталонный
`runs/base.jsonl` точно так же оставлен командой `make replay-base` ещё с iter 4. Дальше оператор
набирает `make drift-push`: скрипту нужно два распределения — он читает **оба** RunRecord-артефакта
(граф заново не гоняется — это контракт №3), считает доли веток и PSI чистыми domain-функциями,
печатает таблицу в stdout (глазная проверка до всякой Grafana) и пушит три вида серий в
Pushgateway. Прогон — короткоживущий батч, скрейпить его pull-моделью некого, поэтому пуш — те же
рельсы, что у `metrics-push` iter 4. Prometheus скрейпит Pushgateway, Grafana каждые 10 секунд
вычисляет alert rule `PSI > 0.2` и через 30 секунд устойчивого превышения переводит его в Firing.

```
make replay-base ──▶ runs/base.jsonl ──┐            (reference, эталонный трафик)
                                       ▼
make replay-post ──▶ runs/post.jsonl ─▶ scripts/drift_push.py
   (граф по кассетам                      │ branch_distribution() + psi()   ← app/domain/drift.py
    cassettes/post/, $0)                  │ stdout: таблица долей + PSI
                                          ▼
                                    Pushgateway (job=authwise-drift, замещение группы)
                                          │ scrape
                                          ▼
                                     Prometheus ──▶ Grafana: дашборд aw-drift (base vs post)
                                          ▲              + alert rule «PSI > 0.2» → Firing
                                          │
                          make drift-verify — читает Prometheus API + Grafana API (правило 9)
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| `app/cli` (`make replay-post`) | гонит post-пачку через граф по кассетам, печатает путь каждой заявки | `runs/post.jsonl` (RunRecord) |
| `app/domain/drift.py` | чистые функции: доли веток по фиксированным терминалам + PSI со сглаживанием | никуда (без I/O) |
| `scripts/drift_push.py` (`make drift-push`) | читает оба RunRecord, считает доли/PSI, печатает таблицу | Pushgateway: `aw_branch_share{role,set,branch}`, `aw_path_drift_psi` |
| Prometheus | скрейпит Pushgateway | своё TSDB-хранилище |
| Grafana (provisioning as-code) | дашборд aw-drift (доли веток base vs post, PSI-stat) + alert rule `PSI > 0.2` | состояние алерта (Normal/Pending/Firing) |
| `scripts/drift_verify.py` (`make drift-verify`) | verify the store: серии из Prometheus API, состояние алерта из Grafana API | stdout (✅/❌ + exit-код) |

Честные оговорки. Это **batch-по-требованию**, а не real-time-стриминг: доли пересчитываются и
пушатся после прогона пачки, gauge — снапшот последнего сравнения. Это **мониторинг, а не ворота**:
CI-гейта на дрейф нет намеренно (сдвиг трафика — не регрессия кода, мёрдж блокировать не за что).
Post-пачка **не размечается golden-путями** — это «трафик», а не эталон, квота singleton к ней не
применяется. И в отличие от SLO-алерта iter 4 (ужатый демо-порог, помеченный `# aw-lite:`) здесь
порог честный: сдвиг post-пачки настоящий, PSI = 0.583 превышает отраслевые 0.2 без поддавков.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; надёжнее искать по именам символов.

1. **Domain-функции дрейфа** — `app/domain/drift.py:26` (`branch_distribution`) и
   `app/domain/drift.py:35` (`psi`). Обе — чистые функции без I/O, как велит правило 6.
   `branch_distribution` строит доли по **фиксированным** терминалам контракта №2 — все три ключа
   присутствуют всегда, чтобы нулевой бин остался видимым, а не исчез из словаря; на пустой
   выборке она бросает `ValueError` (распределение не определено). `psi` сглаживает нулевые доли
   константой `_EPSILON = 1e-4` — стандартный приём PSI: появившаяся из ниоткуда ветка даёт
   большой, но конечный вклад. Порог `PSI_DRIFT_THRESHOLD = 0.2` (`app/domain/drift.py:21`)
   продублирован в Grafana-правиле — комментарий требует править синхронно.

   ```python
   def branch_distribution(branches: Iterable[Branch]) -> dict[Branch, float]:
       """Доли веток по фиксированным терминалам (все три ключа присутствуют всегда)."""
       counts = Counter(branches)
       total = counts.total()
       if total == 0:
           raise ValueError("распределение веток по пустой выборке не определено")
       return {branch: counts[branch] / total for branch in BRANCHES}


   def psi(reference: dict[Branch, float], primary: dict[Branch, float]) -> float:
       """PSI между двумя распределениями долей веток (ключи — BRANCHES, суммы ~1)."""
       value = 0.0
       for branch in BRANCHES:
           ref = max(reference[branch], _EPSILON)
           cur = max(primary[branch], _EPSILON)
           value += (cur - ref) * math.log(cur / ref)
       return value
   ```

2. **«Пострелизная» пачка и её кассеты** — `fixtures/requests-post.jsonl` (30 заявок,
   `meta.pack = "post"` по контракту №1) и `cassettes/post/` (79 record-кассет с `usage`;
   их больше 60, потому что retry-циклы policy-check пишут отдельные attempt-файлы по ключу
   `(request_id, node, attempt)` — контракт №4). Сюжет сдвига: волна weight-loss/GLP-1-заявок,
   которые план не покрывает (→ `escalate`), и наспех поданные заявки, где дозапрос документов не
   помогает (→ терминальный `request-info`). Фактическое распределение — approve 36.7% /
   request-info 26.7% / escalate 36.7% против базовых 73.3% / 13.3% / 13.3%.

3. **Пуш-транспорт** — `scripts/drift_push.py:27` (`main`). Тонкий скрипт по образцу
   `metrics_push` iter 4: хелпер `_distribution()` (`scripts/drift_push.py:17`) читает
   RunRecord-артефакт нужного сета через `records_path()` и внятно падает с подсказкой
   `make replay-<set>`, если артефакта нет. Дальше — две gauge-метрики в собственном
   `CollectorRegistry` и `push_to_gateway` с заменой всей группы `job=authwise-drift`
   (идемпотентность: повторный пуш замещает, а не плодит серии).

   ```python
   share = Gauge(
       "aw_branch_share",
       "доля терминальной ветки в батче пачки (role: reference — эталон, primary — текущая)",
       ["role", "set", "branch"],
       registry=registry,
   )
   psi_gauge = Gauge(
       "aw_path_drift_psi",
       "PSI распределения веток: primary против reference (одна серия сравнения)",
       registry=registry,
   )
   ...
   push_to_gateway(settings.pushgateway_url, job="authwise-drift", registry=registry)
   ```

   Лейбл `role` (reference/primary) несёт стабильную семантику — её пинят панели Grafana; лейбл
   `set` — информационное имя пачки, так что env-ручки `AW_DRIFT_REFERENCE_SET` /
   `AW_DRIFT_PRIMARY_SET` (`app/config.py:44-45`) крутятся без правки дашборда.

4. **`records_path()` научился читать чужой сет** — `app/workflow/runner.py:90`. Конвенция имени
   артефакта (`runs/<cassette_set>.jsonl`) осталась в одном месте, но drift-push сравнивает **два**
   сета за один запуск, поэтому у функции появился явный параметр вместо копий конвенции по
   транспортам:

   ```python
   def records_path(settings: Settings, *, cassette_set: str | None = None) -> Path:
       return settings.runs_dir / f"{cassette_set or settings.cassette_set}.jsonl"
   ```

5. **Grafana as-code** — дашборд `slo/grafana/dashboards/aw-drift.json` (uid `aw-drift`: два
   bargauge «Ветки — reference / primary» + stat-панель PSI) и alert rule
   `slo/grafana/provisioning/alerting/aw-drift.yml` (uid `aw-path-drift-psi`, титул
   `Path-distribution drift (PSI)`). Правило вычисляет `aw_path_drift_psi` раз в 10 секунд и при
   превышении 0.2 в течение 30 секунд уходит в Firing; `noDataState: OK` — до первого drift-push
   серий нет, и это не инцидент.

   ```yaml
   - refId: breach
     model:
       type: threshold
       expression: psi
       conditions:
         - evaluator:
             type: gt
             params: [0.2]
   for: 30s
   noDataState: OK
   ```

6. **Verify the store** — `scripts/drift_verify.py:27` (`main`). По правилу 9 доказательство —
   запросы к API, не скрин UI: инстант-запросом к Prometheus проверяется, что серии
   `aw_branch_share` несут все три ветки для **обеих** ролей, что `aw_path_drift_psi` существует и
   выше порога (иначе подсказка «пачки перепутаны?»), а через Grafana API — что alert rule
   существует и **Firing**. Общие HTTP-хелперы вынесены в `scripts/verify_http.py`
   (`prom_query:23`, `check_alert_firing:42`, `report:56`) — `slo_verify` iter 4 переведён на них
   же, вместо двух копий stdlib-обвязки.

7. **Make-таргеты** — `Makefile:52-62`: `record-post` (⚠️ деньги, только по явной просьбе —
   правило 4), `replay-post` ($0, печатает пути), `drift-push`, `drift-verify`. Тесты domain-слоя —
   `tests/test_drift.py` (7 штук): фиксированные терминалы и отказ на пустой выборке, PSI = 0 на
   идентичных распределениях, симметрия, ручной расчёт `0.5·ln 2`, конечность и значимость
   нулевого бина, малый сдвиг под порогом.
