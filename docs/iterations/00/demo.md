# Демо итерации 00 — граф с реальным ветвлением, путь как значение

Прогон доказывает фундамент всего проекта: многошаговый агент существует, его маршрут
**воспроизводим офлайн за $0** (replay-кассеты), и путь каждой заявки — ветка плюс число
retry-циклов — доступен как типизированное значение (`PathTrace`), а не как строчка в логах.
Без этого ни golden-сет (iter 1), ни CI path-gate (iter 2) собирать не на чем. Live-шагов в
демо нет — вся итерация бесплатная.

Все команды выполняются из корня репо: `/Users/dd/projects/pet/authwise-lite`.

## 1. Окружение

Зачем: остальные шаги гоняются через `uv run` из локального venv.

```bash
uv sync --extra dev
```

**Ожидаемо:** завершается без ошибок (venv `.venv/` создан/обновлён, зависимости из `uv.lock`).

## 2. Статический гейт

Зачем: это тот же гейт, который гоняет CI-скелет; в него входит и механический тест дисциплины
LiteLLM (правило 5 — красная линия).

```bash
make check
```

**Ожидаемо:** все четыре шага зелёные, последняя строка pytest — `27 passed`.

## 3. Все три терминала + retry-цикл (это и есть done-gate)

Зачем: одна команда показывает реальное ветвление — четыре заявки уходят четырьмя разными
путями, включая retry-цикл и терминальный `request-info`.

```bash
make smoke
```

**Ожидаемо (дословно эти четыре строки):**

```
PA-smoke-001: classify → policy-check → approve
PA-smoke-002: classify → policy-check → request-info ↻1 → approve
PA-smoke-003: classify → policy-check → escalate
PA-smoke-004: classify → policy-check → request-info ↻2
```

## 4. Одна заявка через продуктовую поверхность

Зачем: CLI — реальная поверхность продукта; прогоняем заявку с retry-циклом отдельно.

```bash
uv run python -m app.cli fixtures/requests-smoke.jsonl --id PA-smoke-002
```

**Ожидаемо:** одна строка — `PA-smoke-002: classify → policy-check → request-info ↻1 → approve`.

## 5. Артефакт: кассета хранит `usage`

Зачем: требование формата кассет (контракт №4/№5) — без `usage` в iter 3–4 нечем считать
per-node cost. Смотрим содержимое кассеты третьей попытки policy-check заявки PA-smoke-004.

```bash
jq '{model, usage: .response.usage, content: .response.content}' \
  cassettes/smoke/PA-smoke-004__policy-check__a3.json
```

**Ожидаемо:** JSON с запиннённой моделью `gpt-4.1-nano-2025-04-14`, полем `usage`
(`prompt_tokens: 309, completion_tokens: 44, total_tokens: 353`) и `content`, внутри которого
`"status": "missing_info"` — из-за него и случился терминальный `request-info`.

## 6. Идемпотентность генерации кассет

Зачем: единственный state-мутирующий шаг итерации; повторный прогон обязан быть no-op, иначе
done-gate держится на свежем дереве.

```bash
make author-cassettes && git status --short cassettes/
```

**Ожидаемо:** скрипт печатает 11 строк `wrote …`, а `git status` по каталогу кассет пуст
(после первого коммита; до него файлы стабильно-идентичны — повторный прогон не меняет ни байта).

## 7. Control-plane backend поднимается

Зачем: MLflow — стор будущего golden-сета (iter 1); проверяем, что slim-Compose живой.
Честная оговорка: реестр пока пуст, сущностей в нём нет — это не баг, а скоуп iter 1.

```bash
make up && sleep 5 && curl -s http://localhost:5051/health && echo " OK"
```

**Ожидаемо:** `OK` (HTTP 200 от MLflow v3.4.0 на порту 5051; 5050 занят сиблингом triagewise).

## 8. CI-скелет и remote

Зачем: existence-gate итерации включает GitHub remote и Actions-скелет.

```bash
git remote -v && ls .github/workflows/
```

**Ожидаемо:** origin — `git@github.com:DmitryDubovikov/authwise-lite.git`; в workflows лежит
`ci.yml` (гоняет `make check`). Зелёный бейдж появится после первого пуша — до него Actions
физически нечего гонять.
