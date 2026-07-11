# Демо итерации 05 — Path-distribution drift monitoring (PSI + Prometheus/Grafana)

Прогон доказывает **мониторинг дрейфа распределения маршрутов** (пункт 6 north-star): агент не
менялся и работает правильно, но состав трафика сдвинулся — и система это замечает сама. Ценность
за пределами демо: гейты (iter 2) ловят регрессию *кода*, SLO (iter 4) — просадку *ноды*, а дрейф
ловит третий класс проблем — **изменившийся мир вокруг агента** (доля эскалаций растёт при
зелёном CI). Демо показывает по очереди: (1) статика и тесты остаются офлайн; (2) обе пачки
оставляют RunRecord-артефакты, и путь каждой заявки виден глазами; (3) `drift-push` печатает
таблицу долей и **честный PSI = 0.583 > 0.2** (порог отраслевой, не ужат); (4) сам стор
подтверждает это по API (правило 9), а повторный пуш идемпотентен.

Все команды выполняются из корня репо: `/Users/dd/projects/pet/authwise-lite` (бинарь `uv` —
`/Users/dd/.local/bin/uv`). Всё демо — **replay, $0**; единственный платный шаг (перезапись
кассет post-пачки) вынесен в конец и помечен «⚠️ live».

## 1. Статический гейт (то, что гоняет CI) — стек не нужен

Зачем: `make check` — ровно то, что гоняет CI; drift-функции — чистый domain, поэтому их юнит-тесты
живут в обычном pytest без docker/сети.

```bash
make check
```

**Ожидаемо:** все шаги зелёные (ruff check, ruff format, mypy, pytest), последняя строка pytest —
`63 passed`.

## 2. Точечные тесты техники iter 5

Зачем: убедиться, что PSI посчитан правильно как формула, а не только «выдал какое-то число»: тест
`test_psi_known_value` сверяет с ручным расчётом `0.5·ln 2`, а `test_psi_zero_bin_is_finite_and_significant` —
что появившаяся из ниоткуда ветка не роняет метрику в бесконечность.

```bash
uv run pytest tests/test_drift.py -v
```

**Ожидаемо:** `7 passed`; в списке — `test_branch_distribution_has_all_terminals`,
`test_psi_known_value`, `test_psi_zero_bin_is_finite_and_significant` и другие.

## 3. Поднять SLO-стек

Зачем: дрейф едет по рельсам iter 4 — Pushgateway принимает батч-метрики, Prometheus их скрейпит,
Grafana вычисляет alert rule. Новых сервисов итерация не добавляет.

```bash
make slo-up
docker compose ps --format '{{.Name}} {{.Status}}' | grep -E 'prometheus|pushgateway|grafana'
```

**Ожидаемо:** три строки со статусом `Up`: `authwise-lite-prometheus-1`,
`authwise-lite-pushgateway-1`, `authwise-lite-grafana-1`.

## 4. Артефакты обеих пачек: replay base и post

Зачем: drift-push сравнивает **два** RunRecord-артефакта, не гоняя граф (контракт №3), — сначала
они должны существовать (`runs/` в `.gitignore`, на чистом клоне их нет). Заодно это единственный
шаг, где путь каждой заявки виден глазами — сам артефакт, а не его метаданные.

```bash
make replay-base
make replay-post
```

**Ожидаемо:** по строке на заявку с пройденным путём; у post-пачки заметно больше `escalate` и
терминальных `request-info`, например:

```
PA-post-019: classify → policy-check → request-info ↻2
PA-post-021: classify → policy-check → escalate
PA-post-027: classify → policy-check → request-info ↻1 → escalate
PA-post-028: classify → policy-check → request-info ↻1 → approve
```

Содержимое артефакта — распределение веток из самих RunRecord (это то, что будет сравнивать PSI):

```bash
jq -r '.path_trace.branch' runs/base.jsonl | sort | uniq -c
jq -r '.path_trace.branch' runs/post.jsonl | sort | uniq -c
```

**Ожидаемо:** base — `22 approve / 4 escalate / 4 request-info`; post —
`11 approve / 11 escalate / 8 request-info`.

## 5. drift-push: доли веток + PSI → Pushgateway

Зачем: это и есть новая техника — доли веток обеих пачек и PSI между ними считаются чистым
domain-слоем и уезжают в Prometheus; stdout-таблица — глазная страховка витрины.

```bash
make drift-push
```

**Ожидаемо:**

```
branch              base      post
approve            73.3%     36.7%
request-info       13.3%     26.7%
escalate           13.3%     36.7%
PSI(post vs base) = 0.583 — значимый (> порога) 0.2
→ pushed в http://localhost:9091 (job=authwise-drift)
```

## 6. drift-verify: сам стор подтверждает (правило 9)

Зачем: заставить **стор**, а не скрин UI, подтвердить: серии обеих ролей скрейпятся Prometheus,
PSI выше порога, alert rule в Grafana существует и Firing. Alert rule вычисляется раз в 10 секунд
и требует 30 секунд устойчивого превышения — после первого `drift-push` подожди ~1 минуту.

```bash
make drift-verify
```

**Ожидаемо:**

```
aw_branch_share (role=reference, set=base): ветки ['approve', 'escalate', 'request-info']
aw_branch_share (role=primary, set=post): ветки ['approve', 'escalate', 'request-info']
aw_path_drift_psi = 0.583 (порог 0.2)
alert rule 'Path-distribution drift (PSI)': state=firing
────────────────────────────────────────────────────────────
✅  VERIFY OK — доли веток обеих пачек скрейпятся Prometheus, PSI выше порога, alert rule 'Path-distribution drift (PSI)' Firing
```

Если алерт ещё `pending` — verify честно падает с подсказкой подождать evaluation+for и повторить.

## 7. Идемпотентность повторного пуша

Зачем: пуш замещает группу `job=authwise-drift` целиком (last-write), повторный прогон не должен
плодить серии — иначе дашборд и алерт со временем распухнут от дублей.

```bash
make drift-push
curl -s 'http://localhost:9090/api/v1/query?query=aw_branch_share' | jq '.data.result | length'
make drift-verify
```

**Ожидаемо:** тот же stdout-вывод, что в шаге 5; серий `aw_branch_share` ровно **6**
(2 роли × 3 ветки), не 12; `drift-verify` снова зелёный.

## 8. (Витрина, опционально) Дашборд глазами

Зачем: verify доказал всё по API; UI — только чтобы посмотреть кадр витрины (правило 8).

Открыть http://localhost:3002 (логин `admin` / `lite-password`, dev-сид из `docker-compose.yml`),
дашборд **authwise-lite — path-distribution drift**.

**Ожидаемо:** два bargauge — распределение веток reference (base) и primary (post) рядом, у primary
столбики `escalate`/`request-info` заметно выше; stat-панель PSI показывает 0.583 в красной зоне;
в Alerting → Alert rules правило `Path-distribution drift (PSI)` — Firing.

## 9. ⚠️ live, стоит денег — перезапись кассет post-пачки (НЕ гонять без явной просьбы)

Зачем существует: кассеты `cassettes/post/` уже записаны и закоммичены; перезапись нужна только
если изменится текст заявок или промпты. Расход ≈$0.01–0.02 (правило 4 — спросить перед прогоном).

```bash
make record-post
```

**Ожидаемо:** 30 заявок проходят через живой OpenAI, `cassettes/post/` перезаписывается
(включая attempt-файлы retry-циклов), `runs/post.jsonl` обновляется.
