# ReSport AI — MVP

Telegram-бот первичной сортировки спортивных травм и трекер восстановления.
Бот не ставит диагнозы и не заменяет очный осмотр.

## Ключевые решения

**Бот — транспорт, а не приложение.** Логика в `core`, aiogram только рисует клавиатуры.
Mini App добавляется вторым адаптером поверх того же ядра.

**Сценарий — это данные.** Декларативный YAML: вопросы, red flags, ветвления, этапы плана.
Новый вид спорта или сценарий = новый YAML + ревью врача. Деплой кода не нужен.

**LLM не принимает решений.** Маршрутизация детерминирована (`core/scenarios/engine.py`).
Модель отвечает за три задачи, у каждой — валидируемый выход и фоллбэк:

| Задача | Выход | При сбое |
|---|---|---|
| `classify_complaint` | `{scenario_id: enum, confidence, body_part}` | кнопочный выбор сценария |
| `normalize_answer` | `{option_id: enum}` | переспрос кнопками |
| `explain_step` | `{text}` | статичный текст из YAML |

`scenario_id` и `option_id` — `Literal`, собранный из загруженных YAML: выдуманное значение
не проходит валидацию pydantic и уходит в фоллбэк. Все вызовы пишутся в `llm_calls`.

## Структура

```
apps/
  bot/     aiogram 3: handlers, keyboards, renderers, middlewares, flow
  api/     FastAPI: вебхук, healthz, задел под Mini App
  worker/  APScheduler: напоминания о чек-инах
  di.py    композиционный корень (Dishka)
core/
  domain/     сущности и модель сценария, без I/O
  scenarios/  engine, loader, plan_engine, snapshot, schema.json, defs/*.yaml
  llm/        provider (Protocol), runner, tasks, schemas
  services/   TriageService, TrackerService, UserService, ExportService
infra/
  db/         модели, репозитории, alembic
  cache/      Redis: FSM, rate-limit, кэш LLM
  telemetry/  structlog
```

Зависимость строго внутрь: `apps → services → domain`. `core` не импортирует aiogram.

## Запуск

```bash
uv sync
cp .env.example .env   # заполнить BOT_TOKEN
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python -m apps.bot     # long polling, для разработки
```

Вебхук (прод):

```bash
uv run python -m apps.api     # FastAPI на APP_PORT
uv run python -m apps.worker  # напоминания
```

При `BOT_USE_POLLING=false` и заданном `BOT_WEBHOOK_BASE_URL` api сам ставит вебхук на старте.

### Проверки

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy core infra apps
```

## Данные

Схема — в `03_erd.puml`. Два принципиальных момента:

1. `recovery_plans.plan_snapshot` — копия плана на момент выдачи. Правка YAML не ломает
   пользователей в середине восстановления: они доходят по своей версии.
2. `session_answers.source` (`button | llm | manual`) — видно, кнопка это была или
   нормализация LLM. Решение «почему отправили к специалисту» воспроизводимо.

FSM-прогресс опроса живёт в Postgres (`sessions` + `session_answers`); Redis — только кэш,
rate-limit и FSM-состояние ожидания текста. Потеря Redis не теряет прогресс.

Аналитика: `events` + Metabase поверх той же Postgres (`docker compose --profile analytics up`).
Выгрузки: `/export_sessions`, `/export_checkins`, `/stats` для `BOT_ADMIN_TG_IDS`.

## Как добавить сценарий

1. Положить YAML в `core/scenarios/defs/<sport>/<key>.yaml`, `id` = `<sport>.<key>`.
2. Проверить: `uv run python -c "from core.config import get_settings; from core.scenarios.loader import load_registry; print(load_registry(get_settings().content.scenarios_dir).ids())"`.
3. Прогнать тесты: полный перебор ответов проверяет, что у каждой комбинации есть исход.

Валидация на старте: JSON Schema (`core/scenarios/schema.json`) + семантика (ссылки на
несуществующие вопросы и опции, отсутствие default-правила, пустой `advance_if`, план без
routing-правила). Битый сценарий роняет процесс при старте, а не пользователя в середине опроса.

Грамматика условий:

```yaml
when: {q_swelling: severe}              # ответ равен
when: {q_swelling: [none, moderate]}    # ответ входит в список
when: {all: [...]}  /  {any: [...]}  /  {not: {...}}
when: {equals: cannot}                  # в red_flags — про ответ на red_flag.question
```

Условия трекера (`advance_if` / `escalate_if`):

```yaml
advance_if: {feeling: [better, same], consecutive: 2, min_days: 3, tasks_done_ratio_gte: 0.6}
escalate_if: {feeling: worse, consecutive: 2}
```

Если `escalate_if` не задан, действует `DEFAULT_ESCALATION` — два «хуже» подряд.
Эскалация проверяется раньше перехода на следующий этап и считается по всей истории плана,
а не только по текущему этапу: трекер не должен удерживать человека от врача.

## Статус

Готово: каркас, движок сценариев, LLM-слой с фоллбэками, трекер с эскалацией, бот целиком,
напоминания, CSV-выгрузка, 77 тестов.

Требует заказчика (блокирует бету):

1. **Два сценария полным деревом, подписанные врачом.** Сейчас в `defs/` черновики,
   помеченные комментарием. Структура финальная, медицинское содержание — нет.
2. **Дисклеймер и текст согласия** — финальная формулировка (`apps/bot/texts.py:DISCLAIMER`,
   версия в `CONTENT_CONSENT_VERSION`).
3. **Куда ведёт кнопка «Обратиться к специалисту»** (`CONTENT_SPECIALIST_URL`).
4. **Тексты бота** — приветствие, ошибки, завершение плана, tone of voice (`apps/bot/texts.py`).
5. **Политика хранения данных и хостинг** — влияет на выбор LLM-провайдера
   (`LLM_PROVIDER`: `anthropic | openai | gigachat | null`).
6. **Критерий успеха беты** — какие метрики считаем по `events`.

Не входит в MVP: подбор специалистов, мультиязычность, фото/видео, оплата, роли.
