# Техническая спецификация Telegram-бота детейлинг-студии

**Статус документа:** проект для последующей реализации  
**Дата актуализации источников:** 12 июля 2026 года  
**Целевая версия Python:** 3.12  
**Способ получения Telegram updates:** long polling  
**Ограничения:** без Docker, Redis и SQLite

## 1. Назначение и границы системы

Система автоматизирует первичную коммуникацию клиента с детейлинг-студией: знакомит с услугами, рассчитывает предварительную стоимость, собирает заявку на бесплатный осмотр, резервирует время, передаёт заявку сотруднику, уведомляет обе стороны и сопровождает подтверждённую запись напоминаниями. Сотрудники управляют данными и заявками через закрытый раздел того же Telegram-бота.

В первую версию входят все перечисленные в задании функции. В первую версию не входят онлайн-оплата, интеграция с CRM, телефонией, внешним календарём и отдельная веб-панель. Эти возможности могут быть добавлены через прикладные сервисы и адаптеры, не меняя доменную модель.

Термины документа:

- **заявка / appointment** — единый объект записи, начиная с черновика и заканчивая результатом визита;
- **слот / schedule slot** — конкретный интервал времени определённого ресурса студии;
- **резерв / slot reservation** — временное или подтверждённое право заявки занять слот;
- **предложение / reschedule proposal** — предложенное администратором альтернативное время;
- **ресурс** — пост, зона или условная единица пропускной способности студии;
- **проектное решение** — правило, выбранное этой спецификацией; оно не выдаётся за возможность или гарантию внешнего продукта.

## 2. Проверенные технические основания

Архитектурные решения ниже опираются на следующие официальные возможности стека:

1. Aiogram 3 предоставляет асинхронные `Router`, `Dispatcher`, middleware, FSM и long polling. Маршрутизаторы позволяют разделять обработчики по функциональным областям. Источники: [Aiogram: handling events](https://docs.aiogram.dev/en/latest/dispatcher/), [Aiogram: Router](https://docs.aiogram.dev/en/latest/dispatcher/router.html).
2. Встроенный `MemoryStorage` Aiogram теряет состояния при остановке процесса и не рекомендуется документацией для production. `BaseStorage` допускает собственную реализацию. Поэтому состояние диалога и черновик должны быть сохранены в PostgreSQL. Источник: [Aiogram: FSM storages](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html).
3. SQLAlchemy требует отдельный `AsyncSession` на каждую конкурентную asyncio-задачу; `async_sessionmaker` предназначен для создания таких сессий с общей конфигурацией. Источник: [SQLAlchemy 2.0: asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks).
4. PostgreSQL поддерживает блокировку строк, частичные уникальные индексы и `FOR UPDATE SKIP LOCKED`. Частичный уникальный индекс обеспечивает уникальность только для строк, подходящих под предикат; `SKIP LOCKED` документирован как подходящий механизм для нескольких обработчиков таблицы, используемой как очередь. Источники: [PostgreSQL: partial indexes](https://www.postgresql.org/docs/current/indexes-partial.html), [PostgreSQL: SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE).
5. Alembic не имеет самостоятельного async API, но официально поддерживает запуск миграций через async engine SQLAlchemy и шаблон `alembic init -t async`. Источник: [Alembic cookbook: Using Asyncio with Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
6. `pydantic-settings` загружает типизированную конфигурацию из переменных окружения и dotenv-файлов. Источник: [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
7. Telegram `file_id` можно использовать для повторной отправки или получения файла, а `file_unique_id` нельзя использовать для скачивания или повторной отправки. Поэтому необходимо хранить оба идентификатора с разными назначениями. Источник: [Telegram Bot API: File and PhotoSize](https://core.telegram.org/bots/api#available-types).
8. Python 3.12 предоставляет `asyncio.TaskGroup` для управления группой фоновых задач и корректного ожидания их завершения. Источник: [Python 3.12: coroutines and tasks](https://docs.python.org/3.12/library/asyncio-task.html#task-groups).
9. `pytest-asyncio` поддерживает асинхронные тесты, режимы asyncio и настраиваемую область event loop. Источник: [pytest-asyncio: configuration](https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html).

## 3. Требования к окружению и зависимостям

### 3.1. Обязательный стек

- Python `3.12.x`;
- Aiogram `>=3,<4`;
- PostgreSQL — поддерживаемая поставщиком хостинга версия;
- SQLAlchemy `>=2,<3`, только 2.x-style API;
- `asyncpg` как runtime-драйвер SQLAlchemy;
- Alembic;
- `pydantic-settings`;
- собственный asyncio-планировщик с очередью в PostgreSQL;
- `pytest` и `pytest-asyncio`.

Проектное решение: в репозитории фиксируется полностью проверенный набор точных версий в lock-файле. Диапазоны выше задают архитектурную совместимость, но не заменяют фиксацию версий. Обновление зависимости выполняется отдельной задачей с прогоном тестов и проверкой миграций.

### 3.2. Почему собственный scheduler

Выбран собственный async scheduler, а не APScheduler. Его состояние находится в таблицах `reminders` и `notification_outbox`; после рестарта процесс продолжает обработку незавершённых строк. Это не требует Redis и не зависит от внутрипроцессной памяти.

Scheduler не является отдельным микросервисом в первой версии: он запускается фоновой задачей рядом с polling внутри `python start.py`. Доменная логика scheduler изолирована, поэтому позднее её можно запустить отдельным процессом без изменения схемы данных.

### 3.3. Конфигурация

`pydantic-settings` загружает и валидирует:

- `BOT_TOKEN` — секретный токен Telegram-бота;
- `DATABASE_URL` — `postgresql+asyncpg://...` для приложения;
- `ALEMBIC_DATABASE_URL` — необязательный отдельный URL для миграций;
- `BOOTSTRAP_OWNER_TELEGRAM_ID` — Telegram ID первого владельца;
- `ADMIN_CHAT_ID` — необязательная группа для оперативных уведомлений;
- `APP_TIMEZONE` — IANA timezone студии, обязательна;
- `LOG_LEVEL`, `LOG_DIR`;
- `SLOT_HOLD_MINUTES`;
- `PROPOSAL_HOLD_MINUTES`;
- `DRAFT_TTL_DAYS`;
- `REMINDER_OFFSETS_MINUTES`;
- `SCHEDULER_POLL_SECONDS`;
- `OUTBOX_MAX_ATTEMPTS`;
- `OUTBOX_LEASE_SECONDS`;
- `MAX_PHOTOS`, `MAX_PHOTO_BYTES`;
- `MANAGER_CONTACT_TEXT`;
- `PRIVACY_NOTICE_TEXT`.

Проектные значения по умолчанию, которые владелец обязан подтвердить до запуска:

- временный резерв клиента — 15 минут;
- резерв альтернативного предложения — 24 часа = `24 × 60 = 1440` минут;
- срок восстановления черновика — 30 дней;
- напоминания — за 24 часа (`24 × 60 = 1440` минут) и за 2 часа (`2 × 60 = 120` минут);
- опрос очереди — каждые 5 секунд;
- lease фоновой задачи — 60 секунд;
- максимум фотографий — 10.

Это конфигурационные рекомендации проекта, а не внешние нормативы. Они должны меняться без миграции базы.

Секреты не коммитятся. В репозитории находится только `.env.example` с именами и описанием переменных. Production может использовать переменные окружения либо файл `.env` с правами чтения только у системного пользователя бота.

## 4. Общая архитектура

### 4.1. Стиль

Модульный монолит с разделением на четыре слоя:

1. **Presentation** — Aiogram routers, filters, middleware, keyboards и форматирование сообщений.
2. **Application** — use cases: создать резерв, подтвердить заявку, перенести запись, отправить напоминание.
3. **Domain** — статусы, правила переходов, объекты результатов, исключения и расчёт цены без зависимости от Telegram.
4. **Infrastructure** — SQLAlchemy repositories, PostgreSQL, Telegram gateway, scheduler, logging и конфигурация.

Обработчик Telegram не содержит SQL и бизнес-правил. Он валидирует входную форму, вызывает один use case и преобразует результат в сообщение/клавиатуру. Транзакционная граница находится в application service. Repository не выполняет `commit` самостоятельно: транзакцией управляет use case.

### 4.2. Компоненты во время исполнения

```text
Telegram Bot API
       │ updates / sendMessage / sendPhoto
       ▼
Aiogram Dispatcher ── Routers ── Application services
                                      │
                         Unit of Work / repositories
                                      │
                                      ▼
                                PostgreSQL
                                      ▲
                                      │ due jobs + outbox
                           Async scheduler worker
```

Long polling выбран как проектное решение для обычного Python-хостинга: не нужны публичный HTTPS endpoint и веб-сервер. Aiogram официально поддерживает и long polling, и webhook; это подтверждает возможность выбранного режима, но не является утверждением, что long polling всегда лучше. Источник: [Aiogram: handling events](https://docs.aiogram.dev/en/latest/dispatcher/).

### 4.3. Транзакции и сессии

- На один Telegram update создаётся один `AsyncSession` через middleware и закрывается после обработчика.
- Фоновая задача создаёт собственный `AsyncSession` на каждую единицу конкурентной работы.
- Одна `AsyncSession` не передаётся в параллельные задачи. Это соответствует требованиям SQLAlchemy к конкурентному использованию `AsyncSession`: [SQLAlchemy 2.0 asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks).
- Все изменения одного бизнес-действия — например, `appointment.status`, `reservation.status`, история статуса, audit log и строки outbox — фиксируются одной PostgreSQL-транзакцией.
- Вызов Telegram API выполняется после фиксации транзакции фоновой обработкой outbox. Поэтому ошибка сети не откатывает подтверждённую в базе заявку.

## 5. Структура директорий

```text
detailing_bot/
├── start.py
├── pyproject.toml
├── requirements.lock
├── .env.example
├── alembic.ini
├── README.md
├── src/
│   └── detailing_bot/
│       ├── __init__.py
│       ├── bootstrap.py
│       ├── config.py
│       ├── logging_config.py
│       ├── constants.py
│       ├── bot/
│       │   ├── dispatcher.py
│       │   ├── commands.py
│       │   ├── states.py
│       │   ├── callbacks.py
│       │   ├── filters/
│       │   │   ├── role.py
│       │   │   └── private_chat.py
│       │   ├── middlewares/
│       │   │   ├── db_session.py
│       │   │   ├── user_context.py
│       │   │   ├── throttling.py
│       │   │   ├── correlation.py
│       │   │   └── error_boundary.py
│       │   ├── routers/
│       │   │   ├── common.py
│       │   │   ├── booking.py
│       │   │   ├── services.py
│       │   │   ├── faq.py
│       │   │   ├── estimate.py
│       │   │   ├── manager.py
│       │   │   ├── my_appointments.py
│       │   │   └── admin/
│       │   │       ├── dashboard.py
│       │   │       ├── appointments.py
│       │   │       ├── schedule.py
│       │   │       ├── services.py
│       │   │       ├── prices.py
│       │   │       ├── faq.py
│       │   │       ├── managers.py
│       │   │       └── audit.py
│       │   ├── keyboards/
│       │   │   ├── common.py
│       │   │   ├── booking.py
│       │   │   └── admin.py
│       │   └── presenters/
│       │       ├── appointment.py
│       │       ├── estimate.py
│       │       └── errors.py
│       ├── application/
│       │   ├── dto/
│       │   ├── interfaces/
│       │   └── services/
│       │       ├── booking_service.py
│       │       ├── slot_service.py
│       │       ├── schedule_service.py
│       │       ├── pricing_service.py
│       │       ├── catalog_service.py
│       │       ├── admin_service.py
│       │       ├── manager_service.py
│       │       ├── reminder_service.py
│       │       └── notification_service.py
│       ├── domain/
│       │   ├── enums.py
│       │   ├── transitions.py
│       │   ├── value_objects.py
│       │   ├── pricing.py
│       │   ├── policies.py
│       │   └── exceptions.py
│       ├── infrastructure/
│       │   ├── db/
│       │   │   ├── base.py
│       │   │   ├── engine.py
│       │   │   ├── session.py
│       │   │   ├── models/
│       │   │   ├── repositories/
│       │   │   └── unit_of_work.py
│       │   ├── telegram/
│       │   │   ├── gateway.py
│       │   │   └── files.py
│       │   └── scheduler/
│       │       ├── runner.py
│       │       ├── leases.py
│       │       ├── reminders.py
│       │       ├── outbox.py
│       │       ├── reservation_expiry.py
│       │       └── slot_closer.py
│       └── utils/
│           ├── datetime.py
│           ├── phone.py
│           ├── pagination.py
│           └── text.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── handlers/
│   ├── concurrency/
│   ├── migrations/
│   ├── fixtures/
│   └── conftest.py
├── scripts/
│   ├── backup.ps1
│   ├── backup.sh
│   ├── restore_test.ps1
│   └── restore_test.sh
└── deploy/
    ├── detailing-bot.service.example
    └── update.md
```

### 5.1. Назначение основных модулей

| Модуль | Ответственность |
|---|---|
| `start.py` | Единственная публичная точка запуска `python start.py`; вызывает `bootstrap.main()` через `asyncio.run()` и возвращает ненулевой exit code при фатальной ошибке старта. |
| `bootstrap.py` | Собирает settings, logging, engine, repositories, Bot, Dispatcher и scheduler; запускает polling и фоновые workers; выполняет graceful shutdown. |
| `config.py` | Типизированная конфигурация `pydantic-settings`, проверка обязательных переменных и диапазонов. |
| `logging_config.py` | Настройка структурных логов, redaction секретов и correlation ID. |
| `constants.py` | Только стабильные технические константы; изменяемые бизнес-параметры остаются в settings/БД. |
| `bot/dispatcher.py` | Регистрация middleware и включение routers в фиксированном порядке. |
| `bot/commands.py` | Описание `/start`, `/help`, `/cancel`, `/admin` для Bot API и переиспользуемые command filters. |
| `bot/states.py` | Имена шагов диалога. Состояние хранится в PostgreSQL, а не в `MemoryStorage`. |
| `bot/callbacks.py` | Типизированные callback payloads; callback содержит короткое действие и ID, но не доверенные бизнес-данные. |
| `bot/filters/role.py` | Проверка активного сотрудника и разрешённой роли. |
| `bot/middlewares/db_session.py` | Создание отдельной `AsyncSession` на update, rollback при исключении и закрытие сессии. |
| `bot/middlewares/user_context.py` | Upsert пользователя Telegram и загрузка staff context. |
| `bot/middlewares/throttling.py` | In-memory ограничение частоты как защита UX; оно не участвует в корректности и может сброситься при рестарте. |
| `bot/middlewares/correlation.py` | Создание `correlation_id` для одного update и передача его во все логи/audit. |
| `bot/routers/booking.py` | Пошаговая заявка, возврат назад, восстановление, фото и подтверждение. |
| `bot/routers/common.py` | `/start`, главное меню, помощь, неизвестный ввод и единый выход из сценария. |
| `bot/routers/services.py` | Клиентский каталог услуг и карточки услуг. |
| `bot/routers/faq.py` | Категории FAQ, вопросы, пагинация и поиск/возврат. |
| `bot/routers/estimate.py` | Диалог предварительного расчёта и перенос quote в draft. |
| `bot/routers/manager.py` | Создание обращения и клиентские ответы менеджеру. |
| `bot/routers/my_appointments.py` | Просмотр клиентом активных записей, перенос и отмена. |
| `bot/routers/admin/*` | Telegram-панель сотрудников; каждый router ограничен ролью и отдельным permission. |
| `admin/dashboard.py` | Сводные счётчики, heartbeat и переходы в административные очереди. |
| `admin/appointments.py` | Фильтры, карточка и допустимые действия над заявками. |
| `admin/schedule.py` | Ресурсы, правила, исключения, генерация и блокировка слотов. |
| `admin/services.py` | Создание, редактирование, сортировка и деактивация услуг. |
| `admin/prices.py` | Price versions, preview и проверка покрытия классов. |
| `admin/faq.py` | Категории и элементы FAQ. |
| `admin/managers.py` | Очередь обращений, назначение, ответы и закрытие. |
| `admin/audit.py` | Read-only фильтрация административного журнала. |
| `bot/keyboards/common.py` | Главное меню, подтверждение/отмена и общая пагинация. |
| `bot/keyboards/booking.py` | Марки, модели, классы, услуги, календарь, время и итог заявки. |
| `bot/keyboards/admin.py` | Dashboard, фильтры и подтверждения административных действий. |
| `bot/presenters/appointment.py` | Безопасное форматирование клиентской и административной карточки заявки. |
| `bot/presenters/estimate.py` | Форматирование позиций, диапазона и оговорки предварительного расчёта. |
| `bot/presenters/errors.py` | Отображение доменных ошибок без утечки внутренних данных. |
| `application/services/*` | Транзакционные use cases; единственное место orchestration бизнес-операций. |
| `application/dto/` | Типизированные команды и результаты между presentation и application слоями. |
| `application/interfaces/` | Protocol/ABC для repositories, UoW, clock и Telegram gateway. |
| `booking_service.py` | Создание/изменение draft, отправка, подтверждение, отклонение, отмена и перенос. |
| `slot_service.py` | Захват, конвертация и освобождение reservation; список доступных слотов. |
| `schedule_service.py` | Правила, исключения, генерация и блокировка слотов. |
| `pricing_service.py` | Загрузка price versions, расчёт и сохранение quote snapshot. |
| `catalog_service.py` | Чтение/изменение услуг, марок, моделей, классов и FAQ с проверкой ссылок. |
| `admin_service.py` | RBAC, staff actions и создание audit rows. |
| `manager_service.py` | Жизненный цикл обращений, назначение и сообщения. |
| `reminder_service.py` | Планирование/отмена reminders при изменении записи. |
| `notification_service.py` | Создание идемпотентных outbox commands в текущей транзакции. |
| `domain/enums.py` | Все допустимые строковые статусы и роли. |
| `domain/transitions.py` | Белые списки переходов статусов и проверки actor/условий. |
| `domain/value_objects.py` | Phone, money range, time interval и безопасные идентификаторы. |
| `domain/pricing.py` | Чистый расчёт цены и округление `Decimal`, без доступа к БД. |
| `domain/policies.py` | Доступность переноса/отмены, TTL и permission matrix. |
| `domain/exceptions.py` | Доменные ошибки без зависимости от SQLAlchemy/Aiogram. |
| `infrastructure/db/models` | SQLAlchemy Declarative mappings, индексы и constraints. |
| `infrastructure/db/base.py` | Declarative Base, naming convention и общие mixins. |
| `infrastructure/db/engine.py` | Создание/закрытие AsyncEngine и безопасные pool settings. |
| `infrastructure/db/session.py` | Настроенный `async_sessionmaker`. |
| `infrastructure/db/repositories` | Запросы к данным; возвращают доменные/DTO объекты, не Telegram types. |
| `infrastructure/db/unit_of_work.py` | Транзакционная граница и единый commit/rollback. |
| `infrastructure/telegram/gateway.py` | Отправка уведомлений из outbox, классификация ошибок Telegram и сохранение `message_id`. |
| `infrastructure/telegram/files.py` | Выбор Telegram PhotoSize и построение метаданных без обязательного скачивания файла. |
| `infrastructure/scheduler/runner.py` | Цикл фоновых заданий, stop event, heartbeat и управляемое завершение. |
| `infrastructure/scheduler/leases.py` | Атомарный захват due rows через `FOR UPDATE SKIP LOCKED`, lease и возврат зависших задач. |
| `infrastructure/scheduler/reminders.py` | Выбор due reminders и передача их в notification outbox/gateway. |
| `infrastructure/scheduler/outbox.py` | Отправка, retry/backoff и terminal failure уведомлений. |
| `reservation_expiry.py` | Освобождение просроченных резервов и связанных предложений. |
| `slot_closer.py` | Пакетный перевод прошедших свободных слотов в `closed`. |
| `utils/datetime.py` | Явное преобразование UTC ↔ timezone студии и форматирование. |
| `utils/phone.py` | Нормализация телефона по утверждённой политике v1. |
| `utils/pagination.py` | Проверенные границы страниц и callback offsets. |
| `utils/text.py` | Trim, длины, удаление управляющих символов и Telegram HTML escaping. |
| `migrations/` | Единственный механизм изменения production-схемы. `create_all()` при старте запрещён. |

## 6. Модель данных PostgreSQL

### 6.1. Общие правила схемы

- Первичные ключи прикладных таблиц — UUID, генерируемые приложением; Telegram ID — `BIGINT` и отдельный уникальный бизнес-ключ.
- Все абсолютные моменты времени — `TIMESTAMPTZ` в UTC. Локальная дата студии вычисляется через `APP_TIMEZONE`; локальная дата слота дополнительно хранится как `slot_date` для навигации и индексации.
- Денежные значения — `NUMERIC(12,2)`, валюта — трёхсимвольная строка. `float` для денег не применяется.
- Статусы — `VARCHAR` плюс именованные `CHECK` constraints. Это проектное решение упрощает добавление нового статуса миграцией и сохраняет контроль БД.
- Все изменяемые сущности имеют `created_at`, `updated_at`; конкурентно редактируемые — `version` для optimistic locking.
- Пользовательские тексты хранятся как plain text. При выводе в HTML parse mode они экранируются.
- Удаление справочников с историческими ссылками заменяется `is_active=false`; физическое удаление разрешено только для никогда не использованных строк.

PostgreSQL документирует назначение `CHECK`, `UNIQUE`, foreign key и exclusion constraints; межстрочную уникальность следует выражать `UNIQUE`/индексом, а не `CHECK`: [PostgreSQL: constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).

### 6.2. Пользователи и роли

#### `users`

| Поле | Тип | Правило |
|---|---|---|
| `id` | UUID PK | внутренний ID |
| `telegram_user_id` | BIGINT UNIQUE NOT NULL | идентификатор Telegram |
| `telegram_chat_id` | BIGINT NULL | последний private chat для уведомлений |
| `username` | VARCHAR(64) NULL | snapshot, не используется для авторизации |
| `first_name`, `last_name` | VARCHAR(128) NULL | snapshot Telegram |
| `customer_name` | VARCHAR(120) NULL | подтверждённое имя клиента |
| `phone_raw` | VARCHAR(64) NULL | последний введённый вид |
| `phone_normalized` | VARCHAR(20) NULL | нормализованное значение |
| `is_blocked` | BOOLEAN NOT NULL DEFAULT false | запрет клиентских действий |
| `last_seen_at` | TIMESTAMPTZ | активность |
| timestamps | | |

#### `staff_members`

| Поле | Тип | Правило |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID UNIQUE FK → users | один staff profile на пользователя |
| `role` | VARCHAR(16) CHECK | `owner`, `admin`, `manager` |
| `is_active` | BOOLEAN | немедленное отключение доступа |
| `created_by_staff_id` | UUID NULL FK → staff_members | кто выдал доступ |
| `revoked_at`, `revoked_by_staff_id` | nullable | аудит отзыва |
| timestamps | | |

#### `admin_action_logs`

Append-only журнал: `id`, `actor_staff_id`, `actor_telegram_user_id_snapshot`, `action`, `entity_type`, `entity_id`, `before_data JSONB`, `after_data JSONB`, `reason`, `correlation_id`, `created_at`, `ip_address NULL`. Поле IP остаётся `NULL`, так как Telegram update не предоставляет IP пользователя боту. Изменение и удаление строк журнала прикладной ролью запрещено; очистка возможна только отдельной регламентной операцией владельца базы.

### 6.3. Автомобили

#### `car_brands`

`id`, `name`, `normalized_name`, `sort_order`, `is_active`, timestamps. Уникальность `normalized_name` среди активных строк.

#### `car_models`

`id`, `brand_id FK`, `name`, `normalized_name`, `default_vehicle_class_id NULL FK`, `sort_order`, `is_active`, timestamps. Уникальность `(brand_id, normalized_name)` среди активных.

#### `vehicle_classes`

`id`, `code UNIQUE`, `name`, `description`, `sort_order`, `is_active`, timestamps. Примеры классов не фиксируются спецификацией; владелец заполняет их через seed/admin panel.

Неизвестная модель не добавляется автоматически в справочник. Она сохраняется в заявке как `custom_model_text`; сотрудник позднее может отдельно создать справочную модель.

### 6.4. Каталог и цены

#### `services`

`id`, `code UNIQUE`, `name`, `short_description`, `full_description`, `duration_minutes NULL`, `is_inspection_available`, `sort_order`, `is_active`, timestamps.

#### `service_prices`

| Поле | Назначение |
|---|---|
| `id` | PK |
| `service_id` | FK → services |
| `vehicle_class_id` | FK → vehicle_classes |
| `price_kind` | `fixed`, `from`, `range`, `on_request`, `free` |
| `amount_min`, `amount_max` | `NUMERIC(12,2)`; constraints зависят от kind |
| `currency` | конфигурируемая валюта, единая для версии 1 |
| `valid_from`, `valid_to` | период действия |
| `is_active` | оперативное отключение |
| `version` | защита административного редактирования |

Constraints: суммы неотрицательны; для `fixed` `amount_min = amount_max`; для `range` `amount_max >= amount_min`; для `free` обе суммы равны нулю; периоды одной услуги/класса не должны пересекаться по бизнес-правилу, проверяемому транзакционно.

#### `estimate_quotes`

Snapshot предварительного расчёта: `id`, `user_id`, `appointment_id NULL`, `vehicle_class_id`, `total_kind`, `total_min`, `total_max`, `currency`, `calculation_version`, `created_at`, `expires_at NULL`.

#### `estimate_quote_items`

`id`, `quote_id`, `service_id`, `service_name_snapshot`, `price_kind_snapshot`, `amount_min`, `amount_max`, `currency`. Snapshot нужен, чтобы последующее изменение цены не переписало ранее показанный расчёт.

Алгоритм расчёта:

1. Для каждой выбранной услуги берётся одна активная цена нужного класса на текущий момент.
2. `total_min = Σ item.amount_min`; `total_max = Σ item.amount_max`.
3. Если хотя бы одна позиция `on_request`, итог помечается `partial` и явно перечисляет позиции без цены.
4. Если все `min == max`, показывается одна сумма; иначе диапазон.
5. Итог всегда помечается как предварительный и не меняет цену подтверждённой заявки. Финальная стоимость устанавливается сотрудником после осмотра вне рамок этой версии.

Каждая отображаемая сумма проверяема по сохранённым `estimate_quote_items`; в административном просмотре показывается формула суммы.

### 6.5. FAQ

#### `faq_categories`

`id`, `name`, `sort_order`, `is_active`, timestamps.

#### `faq_items`

`id`, `category_id NULL FK`, `question`, `answer`, `sort_order`, `is_active`, `version`, timestamps.

### 6.6. Расписание

#### `schedule_resources`

`id`, `code`, `name`, `capacity_units` (в v1 равно 1 для каждого ресурса), `is_active`. Если студия принимает две машины одновременно, создаются два ресурса, а не слот с capacity=2. Это упрощает однозначную блокировку.

#### `weekly_schedule_rules`

`id`, `resource_id`, `weekday` (`0..6`), `local_start_time`, `local_end_time`, `slot_duration_minutes`, `valid_from`, `valid_to NULL`, `is_active`, timestamps. Правило описывает шаблон, но само по себе не является доступным временем.

#### `schedule_exceptions`

`id`, `resource_id NULL` (NULL = вся студия), `local_date`, `kind` (`closed`, `custom_hours`, `extra_hours`), `local_start_time NULL`, `local_end_time NULL`, `reason`, timestamps.

#### `schedule_slots`

| Поле | Тип/правило |
|---|---|
| `id` | UUID PK |
| `resource_id` | FK → schedule_resources |
| `start_at`, `end_at` | TIMESTAMPTZ, `end_at > start_at` |
| `slot_date` | DATE в timezone студии |
| `status` | `available`, `held`, `booked`, `blocked`, `closed` |
| `source` | `generated`, `manual` |
| `blocked_reason` | NULL либо причина |
| `version` | optimistic locking |
| timestamps | | 

Уникальность `(resource_id, start_at)`. Генератор не создаёт пересекающиеся интервалы одного ресурса; это проверяется интеграционным тестом и транзакционной проверкой при ручном добавлении. Слоты генерируются на конфигурируемый горизонт, например на 60 дней. Число 60 — проектная настройка, а не внешнее ограничение.

### 6.7. Заявки, фото, резервы и переносы

#### `appointments`

| Группа | Поля |
|---|---|
| Identity | `id`, короткий публичный `number` UNIQUE |
| Клиент | `user_id FK`, `customer_name`, `phone_raw`, `phone_normalized` |
| Автомобиль | `brand_id`, `brand_name_snapshot`, `model_id NULL`, `model_name_snapshot NULL`, `custom_model_text NULL`, `vehicle_class_id`, `vehicle_class_name_snapshot` |
| Запись | `status`, `current_slot_id NULL FK`, `confirmed_at`, `completed_at`, `cancelled_at`, `cancellation_reason` |
| Черновик | `draft_step`, `draft_data JSONB`, `last_activity_at`, `draft_expires_at`, `draft_expired_at NULL`, `is_active_draft` |
| Цена | `estimate_quote_id NULL FK` |
| Связи | `rebooked_from_appointment_id NULL FK → appointments` для новой записи по терминальной заявке |
| Операционный флаг | `slot_expired BOOLEAN DEFAULT false` — ожидание администратора без действующего резерва |
| Конкурентность | `version` |
| Системные | timestamps |

`draft_data` содержит только ещё не материализованные промежуточные ответы интерфейса. После подтверждения формы канонические поля находятся в типизированных колонках и дочерних таблицах.

#### `appointment_services`

`appointment_id`, `service_id`, `service_name_snapshot`, `sort_order`; составной PK `(appointment_id, service_id)`.

#### `appointment_photos`

`id`, `appointment_id`, `telegram_file_id`, `telegram_file_unique_id`, `telegram_chat_id`, `telegram_message_id`, `file_size NULL`, `width NULL`, `height NULL`, `sort_order`, `created_at`.

Хранится `file_id` самого большого объекта `PhotoSize`, полученного в update, и `file_unique_id` для дедупликации внутри одной заявки. Бинарный файл по умолчанию не скачивается. Возможность повторно использовать `file_id` и невозможность использовать `file_unique_id` для скачивания/отправки описаны в [Telegram Bot API](https://core.telegram.org/bots/api#photosize).

#### `slot_reservations`

| Поле | Назначение |
|---|---|
| `id` | PK |
| `slot_id` | FK → schedule_slots |
| `appointment_id` | FK → appointments |
| `purpose` | `customer_checkout`, `admin_proposal`, `confirmed_booking` |
| `status` | `active`, `converted`, `expired`, `released`, `cancelled` |
| `expires_at` | обязательно для `active`, NULL для `converted` |
| `converted_at`, `released_at` | аудит |
| `release_reason` | причина |
| timestamps | | 

Критический constraint: частичный уникальный индекс по `slot_id` с предикатом `status IN ('active', 'converted')`. Он запрещает второй активный/подтверждённый резерв одного слота даже при гонке двух процессов. Возможность частичного уникального индекса подтверждена документацией PostgreSQL: [Partial indexes, Example 11.3](https://www.postgresql.org/docs/current/indexes-partial.html).

Дополнительные индексы по заявке учитывают сценарий предложения переноса: одна заявка может временно иметь старый `converted` reservation и новый `active` reservation purpose=`admin_proposal`. Поэтому устанавливаются отдельно: уникальный `appointment_id WHERE status='converted'`; уникальный `appointment_id WHERE status='active' AND purpose='customer_checkout'`; а единственность активного предложения обеспечивается индексом `reschedule_proposals` ниже. Во время принятия переноса старый converted reservation освобождается и новый reservation конвертируется в одной транзакции.

#### `appointment_status_history`

`id`, `appointment_id`, `from_status NULL`, `to_status`, `actor_type` (`user`, `staff`, `system`), `actor_user_id NULL`, `actor_staff_id NULL`, `reason`, `metadata JSONB`, `created_at`. Таблица append-only.

#### `reschedule_proposals`

`id`, `appointment_id`, `old_slot_id NULL`, `proposed_slot_id`, `reservation_id`, `status` (`pending`, `accepted`, `declined`, `expired`, `withdrawn`), `message_to_customer`, `expires_at`, `responded_at`, `created_by_staff_id`, timestamps.

Только одно `pending` предложение на заявку — частичный уникальный индекс по `appointment_id WHERE status='pending'`.

### 6.8. Напоминания, уведомления и обращения

#### `reminders`

`id`, `appointment_id`, `kind` (`before_visit`, `proposal_expiry`, `manager_followup`), `scheduled_for`, `status`, `attempt_count`, `next_attempt_at`, `processing_started_at`, `lease_until`, `sent_at`, `telegram_message_id NULL`, `last_error_code NULL`, `last_error_safe NULL`, `created_at`, `updated_at`.

Уникальность `(appointment_id, kind, scheduled_for)` предотвращает повторное планирование одинакового напоминания.

#### `notification_outbox`

Надёжная очередь всех уведомлений: `id`, `event_type`, `recipient_chat_id`, `appointment_id NULL`, `manager_request_id NULL`, `payload JSONB`, `idempotency_key UNIQUE`, `status` (`pending`, `processing`, `sent`, `retry`, `failed`, `cancelled`), `attempt_count`, `next_attempt_at`, `lease_until`, `sent_at`, `telegram_message_id NULL`, `last_error_code`, `last_error_safe`, timestamps.

Outbox создаётся в той же транзакции, что и доменное изменение. Например, подтверждение заявки и задания уведомить клиента не могут разойтись между двумя commits.

#### `manager_requests`

`id`, `number UNIQUE`, `user_id`, `appointment_id NULL`, `previous_request_id NULL FK → manager_requests`, `subject`, `initial_message`, `status`, `assigned_staff_id NULL`, `customer_last_message_at`, `staff_last_message_at`, `resolved_at`, `closed_at`, timestamps.

#### `manager_request_messages`

`id`, `manager_request_id`, `sender_type`, `sender_user_id NULL`, `sender_staff_id NULL`, `text NULL`, `telegram_file_id NULL`, `created_at`. V1 поддерживает обязательный текст; файл оставлен как расширение.

### 6.9. Связи между таблицами

```text
users 1 ── 0..1 staff_members
users 1 ── * appointments
users 1 ── * manager_requests

car_brands 1 ── * car_models
vehicle_classes 1 ── * car_models
vehicle_classes 1 ── * service_prices
services 1 ── * service_prices

appointments * ── * services          через appointment_services
appointments 1 ── * appointment_photos
appointments 1 ── * appointment_status_history
appointments 1 ── * slot_reservations
appointments 1 ── * reschedule_proposals
appointments 1 ── * reminders

schedule_resources 1 ── * schedule_slots
schedule_slots 1 ── * slot_reservations
schedule_slots 1 ── * reschedule_proposals

estimate_quotes 1 ── * estimate_quote_items
appointments 0..1 ── 0..1 estimate_quotes

manager_requests 1 ── * manager_request_messages
staff_members 1 ── * admin_action_logs
```

Foreign key delete policy:

- справочники, упомянутые историей, — `RESTRICT`;
- дочерние фотографии/строки черновика — `CASCADE` только при санкционированном физическом удалении заявки;
- сотрудник в исторических действиях — `SET NULL` не применяется: staff profile деактивируется, но сохраняется;
- пользовательские данные физически удаляются только отдельной процедурой retention/anonymization, требования к которой владелец определяет с учётом применимого права. Эта спецификация не утверждает конкретный юридический срок хранения.

## 7. Статусные модели

### 7.1. Роли

| Роль | Права |
|---|---|
| `owner` | Полный доступ; выдача/отзыв ролей; настройки; журнал; все действия admin и manager. Нельзя удалить или деактивировать последнего активного owner. |
| `admin` | Заявки, подтверждение/отклонение/перенос, расписание, услуги, FAQ и цены; просмотр журнала; без управления owner и без очистки журнала. |
| `manager` | Просмотр заявок и клиентских контактов, работа с обращениями, предложение времени; без изменения ролей, каталога, цен и расписания. |

RBAC реализуется дважды: router-level filter скрывает/не допускает раздел, application service повторно проверяет permission. Callback не является доказательством права.

### 7.2. Статусы заявки

Обязательный набор:

- `draft` — пользователь начал, но не отправил заявку;
- `waiting_admin` — клиент подтвердил итог, заявка отправлена сотрудникам;
- `confirmed` — сотрудник подтвердил дату и время;
- `rejected` — сотрудник окончательно отклонил заявку с причиной;
- `cancelled_by_user` — клиент отменил ожидающую/подтверждённую запись;
- `cancelled_by_admin` — сотрудник отменил запись после принятия или по операционной причине;
- `completed` — визит состоялся и завершён;
- `no_show` — клиент не явился.

Разрешённые переходы:

```text
draft → waiting_admin
draft → cancelled_by_user

waiting_admin → confirmed
waiting_admin → rejected
waiting_admin → cancelled_by_user
waiting_admin → cancelled_by_admin

confirmed → completed
confirmed → no_show
confirmed → cancelled_by_user
confirmed → cancelled_by_admin

rejected / cancelled_* / completed / no_show → терминальные
```

Предложение другого времени не создаёт отдельный статус заявки: заявка остаётся `waiting_admin` либо `confirmed`, а состояние переговоров хранится в `reschedule_proposals`. Это не перегружает обязательный статусный набор и позволяет отличать состояние заявки от состояния предложения.

Повторное открытие терминальной заявки запрещено. Для новой даты после терминального состояния создаётся новая заявка с `rebooked_from_appointment_id` (поле можно добавить первой миграцией, если владелец подтверждает требование связи).

### 7.3. Статусы временного слота

- `available` — может быть захвачен;
- `held` — существует `active` reservation;
- `booked` — существует `converted` reservation;
- `blocked` — сотрудник закрыл интервал; резервов быть не должно;
- `closed` — незанятый интервал уже прошёл или свободный слот выведен из продажи системой; резервов быть не должно. Прошедший занятый слот сохраняет `booked` для согласованности с reservation/history.

Инварианты:

- `held` ↔ ровно один `active` reservation;
- `booked` ↔ ровно один `converted` reservation;
- `available`, `blocked`, `closed` ↔ нет `active/converted` reservation;
- прошедший `start_at` не показывается клиенту независимо от задержки фонового перевода в `closed`.

### 7.4. Статусы резервирования

- `active` — временный резерв до `expires_at`;
- `converted` — резерв превращён в подтверждённое занятие слота;
- `expired` — срок истёк до подтверждения;
- `released` — освобождён нормальным workflow: смена выбора, отклонение предложения, перенос;
- `cancelled` — освобождён из-за отмены заявки.

`expired`, `released`, `cancelled` терминальны. `active → converted|expired|released|cancelled`; `converted → released|cancelled` при переносе/отмене. История строки не перезаписывается новой попыткой: для нового слота создаётся новая reservation.

### 7.5. Статусы напоминания

- `scheduled` — ожидает срока;
- `processing` — захвачено worker и имеет lease;
- `sent` — Telegram подтвердил успешный вызов, сохранён message ID;
- `retry` — временная ошибка, назначена следующая попытка;
- `failed` — исчерпаны попытки или ошибка признана постоянной;
- `cancelled` — запись больше не требует напоминания.

Переходы: `scheduled|retry → processing → sent|retry|failed`; `scheduled|retry → cancelled`; зависшее `processing` после `lease_until` возвращается в `retry`.

### 7.6. Статусы обращения к менеджеру

- `open` — обращение создано, не назначено;
- `assigned` — назначен ответственный;
- `waiting_customer` — менеджер ответил, ожидается клиент;
- `waiting_manager` — клиент ответил, ожидается менеджер;
- `resolved` — вопрос решён, допускается повторное открытие новым сообщением клиента в пределах конфигурируемого окна;
- `closed` — окончательно закрыто;
- `cancelled` — клиент отменил до начала работы.

`closed` и `cancelled` терминальны. Повторное сообщение после терминального статуса создаёт новое обращение и ссылку `previous_request_id` при необходимости.

## 8. Пользовательские сценарии

### 8.1. Главное меню

`/start` выполняет upsert пользователя, проверяет незавершённый черновик и показывает:

- «Записаться на бесплатный осмотр»;
- «Услуги»;
- «Рассчитать стоимость»;
- «Мои записи»;
- «FAQ»;
- «Связаться с менеджером».

Если есть незавершённый черновик, перед меню предлагаются «Продолжить», «Начать заново», «Удалить черновик». Начать заново отменяет старый draft и освобождает его `active` reservation одной транзакцией.

### 8.2. Запись на бесплатный осмотр

Последовательность:

1. Создать/получить единственный активный `draft` пользователя.
2. Показать активные марки с пагинацией и поиском при большом справочнике.
3. Показать активные модели выбранной марки и кнопку «Моей модели нет».
4. При неизвестной модели принять ручной текст, но не изменять справочник.
5. Предложить класс автомобиля; автоподсказка модели не подтверждает выбор вместо пользователя.
6. Выбрать одну или несколько интересующих услуг.
7. Принять фотографии по одной; после каждой показать счётчик `n / MAX_PHOTOS`; кнопки «Готово» и «Пропустить». Фото необязательны, если владелец не установил обратное.
8. Показать доступные локальные даты на горизонте расписания.
9. Показать доступное время выбранной даты.
10. При выборе времени атомарно создать временный резерв. Если слот уже занят, сообщить и перерисовать доступное время.
11. Запросить имя с возможностью подтвердить имя Telegram.
12. Запросить телефон: кнопка Telegram `request_contact` либо ручной ввод.
13. Показать итог: авто, класс, услуги, число фото, дата/время/timezone, имя, телефон, предварительную цену при наличии; дать редактировать каждый блок.
14. При «Подтвердить» повторно проверить полноту, срок резерва и актуальность слота; перевести draft в `waiting_admin`; резерв пока остаётся `active` до решения администратора либо имеет отдельный административный TTL.
15. Записать историю и outbox-уведомления сотрудникам в одной транзакции.
16. Клиенту показать номер заявки и состояние «Ожидает подтверждения».

Проектное решение для ожидания администратора: после отправки клиентом reservation продлевается до `ADMIN_REVIEW_HOLD_MINUTES` (например, 24 часа). Если срок истёк без решения, scheduler освобождает слот, а заявка остаётся `waiting_admin` с флагом `slot_expired`; администратор обязан предложить новое время. Автоматически отклонять заявку нельзя, потому что отсутствие ответа сотрудника не доказывает невозможность записи.

### 8.3. Назад и редактирование

- Кнопка «Назад» возвращает на предыдущий логический шаг.
- Смена марки очищает model/custom model, но не удаляет остальные совместимые ответы.
- Смена даты/времени в одной транзакции помечает старый временный резерв `released` и пытается вставить новый. Если вставка нового резерва не удалась, вся транзакция откатывается, поэтому старый резерв фактически сохраняется.
- Смена класса пересчитывает estimate snapshot.
- Любое изменение обновляет `last_activity_at`, `draft_step` и `version`.

### 8.4. Подтверждение/отклонение сотрудником

- При подтверждении reservation `active → converted`, slot `held → booked`, application `waiting_admin → confirmed`; создаются напоминания и уведомление клиента.
- При отклонении reservation освобождается, slot становится `available`, application → `rejected`; причина обязательна и отправляется клиенту в безопасной формулировке.
- Повторное нажатие старой inline-кнопки возвращает текущий статус без повторного действия; use case идемпотентен относительно целевого состояния.

### 8.5. Альтернативное время

1. Сотрудник выбирает свободный слот.
2. Система создаёт `active` reservation purpose=`admin_proposal` и `pending` proposal с TTL.
3. Клиент получает «Принять» / «Отклонить».
4. Принятие атомарно освобождает прежний reservation, конвертирует новый, обновляет `current_slot_id`; заявка становится/остаётся `confirmed` в зависимости от исходного workflow.
5. Отклонение или expiry освобождает новый слот; предыдущая подтверждённая запись при переносе остаётся без изменений.

Главный инвариант: при предложении переноса уже подтверждённой записи старый слот не освобождается до принятия нового клиентом.

### 8.6. Перенос клиентом

В «Мои записи» перенос доступен только для `confirmed` и до конфигурируемого cut-off. Если бизнес не определил cut-off, бот не блокирует перенос по времени и передаёт запрос сотруднику. Варианты реализации:

- **v1 по умолчанию:** клиент выбирает альтернативный свободный слот, создаётся `pending` proposal/request, старый слот сохраняется до подтверждения сотрудником;
- сотрудник принимает — атомарная замена reservation;
- сотрудник отклоняет — старая запись остаётся.

Автоматический перенос без сотрудника включается отдельной настройкой только после письменного подтверждения владельца.

### 8.7. Отмена клиентом

- Доступна для `waiting_admin` и `confirmed`.
- Бот показывает точную запись и просит отдельное подтверждение.
- Транзакция меняет статус на `cancelled_by_user`, отменяет reminders/proposals, переводит reservation в `cancelled`, освобождает слот и создаёт outbox сотрудникам.
- Повторный callback не меняет состояние и показывает «Запись уже отменена».

### 8.8. Услуги, FAQ и расчёт

- «Услуги» показывает только активные услуги, карточку, описание и цену/диапазон для выбранного класса.
- FAQ имеет категории, пагинацию и кнопку возврата.
- Расчёт запрашивает класс и услуги, создаёт quote snapshot и показывает формулу по позициям.
- Quote можно перенести в новый draft без повторного выбора класса/услуг.

### 8.9. Связь с менеджером

1. Клиент выбирает тему или «Другое» и вводит сообщение.
2. Создаётся `open` manager request и outbox менеджерам.
3. Ответ сотрудника через admin panel пересылается клиенту от имени студии.
4. Клиентский ответ присоединяется к активному обращению.
5. Статусы `waiting_customer`/`waiting_manager` отражают сторону, от которой ожидается действие.
6. Номер телефона менеджера или внешний username показывается только если задан `MANAGER_CONTACT_TEXT`; бот не выдумывает контакт.

## 9. Административные сценарии

### 9.1. Вход и dashboard

`/admin` доступен только активным `staff_members`. Авторизация основана на числовом `telegram_user_id`, а не username. Dashboard показывает счётчики:

- новые `waiting_admin`;
- подтверждённые сегодня/завтра по timezone студии;
- просроченные заявки без действующего резерва;
- открытые обращения;
- failed notifications/reminders.

Каждый счётчик строится прямым запросом и ведёт к списку с пагинацией.

### 9.2. Заявки

- Фильтры по статусу, дате, номеру, телефону и клиенту.
- Карточка: snapshot авто, услуги, фото, quote, история, reservation и сообщения.
- Действия по permission: подтвердить, отклонить, предложить время, отменить, отметить completed/no_show, связаться.
- Для рискованных действий обязательны preview и повторное подтверждение.
- Причина обязательна для `rejected` и `cancelled_by_admin`; для `no_show` — необязательный комментарий.

### 9.3. Расписание

- Управление ресурсами, недельными правилами, выходными/исключениями.
- Генерация/перегенерация будущих слотов не меняет `held` и `booked`.
- Заблокировать можно только свободный слот; попытка блокировки занятого требует сначала отдельной отмены/переноса заявки.
- Разблокировка `blocked → available` допустима только для будущего времени.
- Ручное создание проверяет отсутствие пересечения с существующим интервалом того же ресурса.
- Все изменения записываются в admin audit с before/after.

### 9.4. Услуги и цены

- Создать, изменить, активировать/деактивировать услугу.
- Изменить описание и сортировку.
- Создать новую price version с периодом действия; исторические snapshots не изменяются.
- Preview показывает цены по каждому классу и предупреждает об отсутствующих комбинациях.
- Удаление используемой услуги запрещено; применяется деактивация.

### 9.5. FAQ

- CRUD категорий и вопросов, изменение порядка, preview сообщения.
- Удаление заменяется деактивацией, если запись использовалась; audit обязателен.

### 9.6. Обращения менеджеру

- Очередь `open`/`waiting_manager`.
- Взять в работу, назначить другому, ответить, отметить resolved/closed.
- Manager видит контактные данные только в контексте доступной ему заявки/обращения.

### 9.7. Роли и журнал

- Только owner выдаёт/отзывает роли.
- Нельзя отозвать роль последнего активного owner.
- Журнал фильтруется по actor, action, entity, периоду; detail показывает before/after и correlation ID.
- Журнал не редактируется через Telegram.

## 10. Восстановление незавершённой заявки

Aiogram `MemoryStorage` для этого не используется, потому что официальная документация предупреждает о потере данных при shutdown: [Aiogram FSM storages](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html).

Проектный механизм:

1. После каждого принятого ответа application service валидирует данные и в одной транзакции обновляет `appointments.draft_step`, каноническое поле/`draft_data`, `last_activity_at`, `draft_expires_at` и `version`.
2. Клавиатуры строятся из текущих данных БД, а не из памяти процесса.
3. На `/start` и на любое неизвестное сообщение bot ищет последний неистёкший `draft` пользователя.
4. Если draft полный и резерв ещё активен, продолжается текущий шаг.
5. Если резерв истёк, дата/время очищаются, пользователь возвращается к выбору даты с понятным объяснением; остальные ответы сохраняются.
6. Если справочник деактивирован после выбора, snapshot остаётся видимым, но перед отправкой заявка просит выбрать активную замену там, где это влияет на обслуживание/цену.
7. Истёкший черновик остаётся `draft`, получает `draft_expired_at`, перестаёт считаться активным и может быть очищен retention job. Новый draft создаётся отдельно. Система не ставит `cancelled_by_user`, потому что пользователь не совершал отмену.

Для одного пользователя разрешён только один неистёкший активный draft: частичный уникальный индекс по `user_id WHERE status='draft' AND draft_expired_at IS NULL` невозможен с условием `now()` в предикате, поэтому активность задаётся отдельным `is_active_draft BOOLEAN`; уникальный индекс действует по `user_id WHERE status='draft' AND is_active_draft=true`. Scheduler атомарно снимает этот флаг при expiry.

## 11. Защита от двойного бронирования

### 11.1. Гарантия уровня базы

Защита не полагается на предварительный `SELECT available` и не полагается на Python-lock: они не дают общей гарантии для нескольких процессов.

Алгоритм захвата:

1. Начать транзакцию.
2. Выбрать `schedule_slots` по ID `FOR UPDATE`.
3. Проверить: slot будущий, `status='available'`, ресурс активен, нет блокирующего исключения.
4. Вставить `slot_reservations(status='active')`.
5. Изменить slot на `held`.
6. Commit.

Два конкурента блокируются на строке slot; дополнительно частичный уникальный индекс `slot_reservations(slot_id) WHERE status IN ('active','converted')` не позволит сохранить две занятости даже при ошибке application logic. PostgreSQL удерживает конфликтующие row-level locks до конца транзакции: [PostgreSQL: explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

При нарушении уникального индекса use case ловит конкретный `IntegrityError`, делает rollback и возвращает доменный результат `SlotAlreadyTaken`; пользователю не показываются SQL-текст и stack trace.

### 11.2. Идемпотентность callback

- Callback несёт appointment ID, slot ID и action token/version.
- До действия сервер заново загружает заявку и проверяет владельца/роль.
- Если желаемое конечное состояние уже достигнуто тем же actor/action, возвращается текущий результат.
- Старый callback с несовпадающей `version` не выполняет мутацию и предлагает обновить карточку.
- Все административные действия имеют уникальный `action_request_id`; повторная доставка update не создаёт вторую историю/outbox.

## 12. Временный резерв и освобождение

### 12.1. TTL

При выборе времени `expires_at = database_current_timestamp + hold_interval`. Время вычисляется PostgreSQL, чтобы процессы с разными системными часами не расходились. Показываемый клиенту остаток является информационным; окончательное решение принимает транзакционная проверка БД.

При отправке в `waiting_admin` TTL меняется на административный. При подтверждении `expires_at=NULL`, reservation → `converted`.

### 12.2. Освобождение просроченных резервов

Worker каждые `SCHEDULER_POLL_SECONDS`:

1. Начинает короткую транзакцию.
2. Выбирает ограниченную batch-порцию `active` reservations с `expires_at <= now()` через `FOR UPDATE SKIP LOCKED`, упорядочивая по `expires_at, id`.
3. Для каждой ещё актуальной строки ставит `expired`; slot `held → available`; pending proposal → `expired`; создаёт историю/outbox, если клиенту нужно объяснение.
4. Commit.
5. Повторяет batch, пока строк нет, затем ждёт следующий poll.

`SKIP LOCKED` пропускает уже захваченные строки и официально описан PostgreSQL как применимый к queue-like таблицам с несколькими consumers: [PostgreSQL: SELECT](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE).

Запрос доступных слотов дополнительно исключает `active` reservation с `expires_at > now()` и никогда не показывает прошедший слот. Поэтому задержка worker не делает просроченный reserve доступным двум пользователям: новый захват сначала под row lock переводит просроченный reserve в `expired`, затем занимает слот.

## 13. Фоновые напоминания и outbox без Redis

### 13.1. Создание reminders

При `confirmed` создаются строки на `slot.start_at - offset`. Если рассчитанное время уже прошло, политика задаётся явно:

- ближайшее релевантное напоминание ставится `scheduled_for=now()`;
- остальные прошедшие offsets не создаются;
- одно оперативное подтверждение записи всё равно отправляется через outbox.

При переносе все несработавшие reminders старого времени становятся `cancelled`, затем создаётся новый набор. При отмене несработавшие reminders отменяются в той же транзакции.

### 13.2. Worker и lease

1. Выбрать due reminders/outbox со статусом `scheduled|retry`/`pending|retry`, `next_attempt_at <= now()` через `FOR UPDATE SKIP LOCKED`.
2. Пометить `processing`, увеличить attempt, поставить `lease_until` и commit.
3. Вне транзакции вызвать Telegram API, чтобы не держать lock во время сети.
4. В новой транзакции сохранить `sent` и `telegram_message_id` либо `retry/failed`.
5. Reaper возвращает `processing` с истёкшим lease в `retry`.

Backoff — проектное решение: `min(base × 2^(attempt-1), max_delay)` плюс небольшой random jitter. Например, при base=5 секунд первые задержки без jitter: 5, 10, 20, 40, 80 секунд; каждая величина получена умножением предыдущей на 2. `RetryAfter` Telegram имеет приоритет над локальной формулой.

### 13.3. Гарантия доставки

Система обеспечивает **at-least-once attempt** для незавершённых outbox rows, пока задача не стала `failed`/`cancelled`. Она не может честно гарантировать exactly-once отображение сообщения клиенту: процесс может успешно отправить сообщение в Telegram и завершиться до записи `sent`. После lease сообщение будет повторено. Telegram `sendMessage` не предоставляет приложению идемпотентный ключ в рамках этой архитектуры. Поэтому:

- сообщения формулируются так, чтобы редкий дубль не создавал второе бизнес-действие;
- callback-действия идемпотентны;
- сохраняются `telegram_message_id`, attempt и correlation ID;
- `failed` видны на административном dashboard;
- owner может безопасно повторить failed notification вручную, создав новую outbox row с новым idempotency key.

### 13.4. Остановка

`bootstrap` запускает polling, scheduler и служебный heartbeat внутри управляемых задач. При SIGTERM/SIGINT прекращается приём новых updates, выставляется stop event, даётся ограниченное время завершить текущие транзакции, затем закрываются Bot session и SQLAlchemy engine. `asyncio.TaskGroup` в Python 3.12 предоставляет управляемое ожидание группы задач: [Python 3.12 TaskGroup](https://docs.python.org/3.12/library/asyncio-task.html#task-groups).

## 14. Валидация и безопасность входных данных

### 14.1. Общие правила

- Callback data не доверяется: ID, actor, ownership, version и статус повторно проверяются в БД.
- SQL строится SQLAlchemy expressions с bind parameters; пользовательская строка не конкатенируется с SQL.
- Тексты экранируются перед HTML-разметкой Telegram.
- Все строки очищаются от leading/trailing whitespace, NUL и управляющих символов; повторные пробелы нормализуются только там, где это не меняет смысл.
- Длины ограничиваются одновременно Pydantic/DTO и PostgreSQL column/check.
- Пагинация ограничивает объём одного ответа и SQL result.
- Бот работает с клиентскими сценариями только в private chat; административная группа может получать уведомления, но действия всё равно проверяют личный staff identity.

### 14.2. Поля

| Поле | Политика v1 |
|---|---|
| Имя | 2–120 Unicode-символов после trim; цифры сами по себе не запрещаются для международных имён, но строка только из пунктуации отклоняется. |
| Ручная модель | 1–120 символов; plain text. |
| Причина/сообщение | 1–1000 символов; длинный текст просит сократить. |
| Телефон | При contact проверяется, что `contact.user_id` отсутствует либо равен отправителю; сохраняется raw. Ручной ввод удаляет пробелы, скобки и дефисы, допускает leading `+`, затем требует 7–15 цифр. Это проектная политика, а не заявление о полной валидации номера любой страны. |
| Дата/слот | Только ID существующего будущего slot; клиентская строка даты не принимается как authority. |
| Услуга/марка/класс | Только активный ID из БД; snapshot создаётся сервером. |
| Фото | Только `message.photo`; сохраняется последний (обычно наибольший) `PhotoSize`; проверяются число и `file_size`, если Telegram его сообщил. |

Если `file_size` отсутствует, нельзя утверждать размер; фото можно принять по числовому лимиту либо скачать для проверки, если владелец требует жёсткий byte-limit. По умолчанию бинарное скачивание отключено.

### 14.3. Персональные данные

Токен, DSN и телефон не попадают в обычные логи. В audit телефон маскируется, если полное значение не требуется расследованию. Доступ выдаётся по наименьшей роли. Политика согласия, срок хранения и процедура удаления должны быть утверждены владельцем с учётом места деятельности и применимого законодательства; из исходных данных нельзя подтвердить конкретную юрисдикцию, поэтому эта спецификация не назначает юридические сроки.

## 15. Обработка ошибок

### 15.1. Категории

| Категория | Реакция |
|---|---|
| Ошибка валидации | Понятное сообщение у конкретного шага; данные не меняются. |
| Бизнес-конфликт | Например, слот занят или переход запрещён: rollback, обновлённая карточка/варианты. |
| `IntegrityError` ожидаемого constraint | Преобразовать по имени constraint в доменную ошибку; не раскрывать SQL. |
| Временная ошибка PostgreSQL | Ограниченный retry только для явно идемпотентного use case; иначе безопасная ошибка и повтор пользователем. |
| Постоянная ошибка PostgreSQL | Correlation ID пользователю, exception log и alert owner. |
| Временная Telegram API | outbox → retry с backoff/RetryAfter. |
| Bot blocked/chat not found | notification → failed с безопасным кодом; заявка не отменяется автоматически. |
| Необработанное исключение handler | Глобальный error boundary, rollback, exception log; пользователю нейтральное сообщение с correlation ID. |
| Ошибка scheduler job | Не завершает polling; job остаётся retry/failed, dashboard показывает проблему. |

`asyncio.CancelledError` после cleanup не поглощается. Python рекомендует `try/finally` для cleanup и повторное распространение cancellation: [Python 3.12: Task cancellation](https://docs.python.org/3.12/library/asyncio-task.html#task-cancellation).

### 15.2. Пользовательское сообщение

Нельзя показывать stack trace, SQL, DSN, токен, внутренние IDs и полный exception. Формат: «Не удалось выполнить действие. Данные не потеряны. Попробуйте ещё раз. Код: `<correlation_id>`». Фраза «данные не потеряны» используется только когда commit не произошёл либо состояние после ошибки прочитано и подтверждено; иначе: «Проверьте текущий статус заявки».

## 16. Логирование и аудит

### 16.1. Технические логи

Структурный JSON либо стабильный key-value формат:

- UTC timestamp, level, logger, event;
- correlation_id, update_id, telegram_user_id;
- appointment_id/number, slot_id, job_id при наличии;
- duration_ms, attempt, result;
- exception type и stack trace только на ERROR.

Не логируются `BOT_TOKEN`, password/DSN, полный телефон, содержимое фото и полный текст личного обращения. Redaction filter маскирует известные secret fields. Логи пишутся в stdout для process manager и опционально в rotating files. Python предоставляет иерархическую logging facility; конкретная ротация является проектной конфигурацией: [Python 3.12 logging](https://docs.python.org/3.12/library/logging.html).

### 16.2. Уровни

- `DEBUG` — только development, SQL echo выключен в production;
- `INFO` — lifecycle, успешные бизнес-события без PII;
- `WARNING` — ожидаемые retries, stale callbacks, invalid admin action;
- `ERROR` — failed job, DB/API failure;
- `CRITICAL` — невозможность старта, повреждённая конфигурация, недоступная БД при startup.

### 16.3. Административный audit

Audit создаётся в той же транзакции, что изменение. Минимальные actions: role grant/revoke, service/price/FAQ CRUD, schedule change, confirm/reject/cancel/reschedule/status completion, manager assignment, manual retry notification. Автоматический scheduler пишет системную историю в соответствующие history tables; не притворяется staff actor.

## 17. Стратегия тестирования

Тесты используют отдельную PostgreSQL test database. SQLite запрещён и также не подходит для проверки PostgreSQL partial indexes, row locks и `SKIP LOCKED`.

### 17.1. Unit tests

Без сети и БД:

- матрица переходов каждого статуса;
- валидация имени, модели, телефона;
- расчёт `total_min/total_max` и `Decimal`;
- timezone/DST conversion;
- backoff;
- permission matrix;
- presenter escaping и pagination.

### 17.2. Integration tests с PostgreSQL

- repositories и foreign keys/check constraints;
- partial unique reservation indexes;
- транзакции confirm/reject/cancel/reschedule;
- expiry worker;
- outbox lease и возврат зависшей задачи;
- восстановление draft после пересоздания application services;
- price snapshots после изменения прайса;
- Alembic upgrade с пустой схемы до head.

Каждый тест изолируется транзакцией/очисткой схемы. Async fixtures используют явный loop scope; доступные настройки документированы pytest-asyncio: [configuration](https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html).

### 17.3. Handler tests

Fake Telegram gateway и реальные application services/тестовая БД:

- `/start`, resume/new draft;
- полный happy path;
- ручная модель;
- пропуск/лимит фото;
- назад и редактирование;
- неверный/старый callback;
- пользователь пытается открыть admin;
- сообщение Telegram не отправилось после commit.

### 17.4. Concurrency tests

Обязательный тест двойного бронирования:

1. Создать один available slot и две draft заявки.
2. Синхронизировать две независимые `AsyncSession`, чтобы они одновременно попытались создать active reservation.
3. Убедиться: ровно один успех, один `SlotAlreadyTaken`, одна active reservation, slot=`held`.

Также:

- confirm против expiry;
- cancel против reminder acquisition;
- два scheduler workers захватывают разные outbox rows;
- два admin callbacks подтверждают одну заявку;
- перенос не освобождает старый слот при неудачном захвате нового.

### 17.5. Migration tests

- `alembic upgrade head` на пустой БД;
- `alembic current --check-heads` после upgrade; команда проверки head документирована Alembic cookbook: [Test current database revision](https://alembic.sqlalchemy.org/en/latest/cookbook.html#test-current-database-revision-is-at-head-s).
- Upgrade с snapshot предыдущего релиза;
- downgrade проверяется только для обратимых development-миграций; production rollback предпочитает restore backup + старый код, если миграция необратима.

### 17.6. Приёмочные критерии

Релиз допускается, если:

- все обязательные сценарии имеют automated happy path и ключевые negative tests;
- concurrency suite стабильно подтверждает уникальность слота;
- schema at Alembic head;
- нет секретов в git и test logs;
- резервная копия тестово восстанавливается;
- smoke test test-бота проходит: `/start`, draft, admin confirm, client notification.

## 18. Запуск через `python start.py`

Последовательность startup:

1. `asyncio.run(main())`.
2. Загрузить Settings; при ошибке вывести только безопасное имя поля и завершиться.
3. Настроить logging.
4. Создать async engine и session factory.
5. Выполнить `SELECT 1` и проверить, что Alembic revision совпадает с head. Миграции автоматически не применяются.
6. Получить PostgreSQL advisory lock приложения, чтобы на одной БД работал только один polling-процесс v1. Если lock занят — завершиться с понятной ошибкой.
7. Проверить/создать bootstrap owner по configured Telegram ID идемпотентным use case.
8. Создать Bot/Dispatcher, зарегистрировать middleware/routers.
9. Снять webhook перед polling только если это явно предусмотрено deployment-процедурой; pending updates по умолчанию не удалять.
10. Запустить polling и scheduler workers.
11. На shutdown корректно закрыть все ресурсы и освободить advisory lock с соединением.

Aiogram 3 запускает polling непосредственно через Dispatcher и не использует удалённый из 3.x `Executor`: [Aiogram migration FAQ](https://docs.aiogram.dev/en/latest/migration_2_to_3.html).

## 19. Alembic

### 19.1. Правила

- Инициализация `alembic init -t async migrations`, что прямо предусмотрено Alembic cookbook: [Using Asyncio with Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
- `target_metadata` указывает на единую SQLAlchemy `Base.metadata`.
- URL берётся из settings/environment, не хранится в `alembic.ini`.
- Каждая ревизия имеет осмысленное имя и явно именованные constraints/indexes.
- Autogenerate — черновик: разработчик вручную проверяет типы, server defaults, partial indexes, data migrations и downgrade.
- Production schema меняется только миграциями; приложение не вызывает `metadata.create_all()`.

### 19.2. Применение

Перед новым кодом:

```text
1. Остановить процесс бота.
2. Создать и проверить backup.
3. Активировать venv нового релиза.
4. Выполнить: python -m alembic upgrade head
5. Выполнить: python -m alembic current --check-heads
6. Запустить: python start.py
7. Выполнить smoke test и проверить логи/dashboard.
```

В первой версии миграция применяется при остановленном приложении. Это исключает необходимость проектировать совместимость старого процесса с новой схемой. Для обновления без downtime позднее потребуется expand/migrate/contract, но оно не заявлено этой спецификацией.

## 20. Развёртывание без Docker

### 20.1. Требования хостинга

- возможность непрерывно запускать Python 3.12 process;
- исходящее HTTPS-соединение к Telegram Bot API;
- доступ к PostgreSQL;
- persistent directory для логов/backup scripts;
- process manager с автоперезапуском (например, systemd на Linux либо эквивалент хостинга);
- возможность передавать secrets через environment/защищённый файл.

Если тариф допускает только краткоживущие cron-задачи и не допускает постоянный процесс, long polling бот на нём не соответствует этой архитектуре. Это нужно проверить у конкретного поставщика; из задания поставщик неизвестен, поэтому совместимость конкретного хостинга подтвердить нельзя.

### 20.2. Первичная установка

```text
1. Создать отдельного системного пользователя и каталог приложения.
2. Установить Python 3.12 и PostgreSQL client tools.
3. Создать venv: python -m venv .venv
4. Активировать venv и установить строго зафиксированные зависимости.
5. Создать PostgreSQL database/user с минимально необходимыми правами.
6. Заполнить production environment.
7. Применить Alembic upgrade head.
8. Запустить python start.py вручную для smoke test.
9. Подключить process manager с WorkingDirectory и Restart-on-failure.
```

Process manager вызывает ровно `path/to/.venv/bin/python start.py` из корня проекта. Автоматический restart имеет задержку и лимит burst, чтобы неверная конфигурация не создала бесконечный tight loop.

### 20.3. Обновление проекта без Docker

Рекомендуется release-directory схема:

```text
/opt/detailing-bot/
├── releases/2026-07-12_001/
├── releases/2026-07-20_001/
├── shared/.env
├── shared/logs/
└── current -> releases/2026-07-20_001/
```

Процедура:

1. Получить новую версию в новый release directory.
2. Создать новый venv и установить lock-файл.
3. Прогнать tests/build checks до переключения.
4. Остановить bot service.
5. Сделать backup БД и записать имя файла/checksum.
6. Применить миграции новым release.
7. Атомарно переключить `current`.
8. Запустить service и smoke test.
9. Если код не стартует и схема совместима — вернуть symlink на прошлый release.
10. Если применена несовместимая миграция — остановить service, восстановить проверенный backup в соответствии с runbook и вернуть старый release.

`git pull` прямо в рабочем production-каталоге не рекомендуется проектом: он смешивает версии и усложняет откат. Это операционное решение спецификации, не ограничение Git.

## 21. Резервное копирование PostgreSQL

`pg_dump` — официальная утилита PostgreSQL для выгрузки одной базы; документация описывает custom archive и восстановление через `pg_restore`: [PostgreSQL: pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [PostgreSQL: pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).

### 21.1. Политика проекта

- Ежедневный logical backup в custom format (`pg_dump -Fc`).
- Дополнительный backup непосредственно перед каждой migration.
- Файлы именуются UTC timestamp + database + Alembic revision.
- Для каждого файла вычисляется SHA-256 checksum.
- Backup шифруется/хранится вне основного сервера согласно возможностям хостинга.
- Retention — конфигурируемая политика владельца; конкретный срок из задания подтвердить нельзя.
- Пароль не указывается в командной строке и имени файла; используется защищённый `.pgpass` либо механизм secrets поставщика.

### 21.2. Проверка восстановления

Backup считается проверенным только после периодического restore в отдельную пустую PostgreSQL database:

1. Создать пустую test-restore DB.
2. `pg_restore` custom archive.
3. Проверить exit code и отсутствие ошибок.
4. Выполнить Alembic `current --check-heads`.
5. Выполнить integrity queries: число active/converted reservations на slot не больше 1; booked slots согласованы с converted reservations; confirmed appointments имеют current slot.
6. Запустить read-only smoke tests.
7. Удалить test-restore DB регламентной процедурой.

Одного факта создания файла недостаточно для подтверждения восстанавливаемости; поэтому дата последнего успешного restore test заносится в операционный журнал.

## 22. Наблюдаемость и эксплуатационные проверки

Поскольку отдельного HTTP health endpoint в long-polling v1 нет, применяются:

- process manager status;
- периодическая запись scheduler heartbeat в таблицу `system_heartbeats(worker_name, instance_id, last_seen_at, metadata)`;
- `/admin` dashboard с возрастом heartbeat, очередями retry/failed, просроченными reservations и Alembic revision;
- startup `SELECT 1`;
- alert в `ADMIN_CHAT_ID` при восстановлении после сбоя, если канал доступен.

Сам бот не может надёжно сообщить через Telegram о полной потере сети/падении процесса. Для такого мониторинга нужен внешний наблюдатель хостинга; конкретный сервис не выбран, потому что его нет в требованиях.

## 23. Индексы

Минимальный набор помимо PK/FK:

- `users(telegram_user_id)` UNIQUE;
- `staff_members(user_id)` UNIQUE;
- `appointments(number)` UNIQUE;
- `appointments(user_id, status, created_at DESC)`;
- `appointments(status, created_at)`;
- unique active draft по `user_id` с partial predicate;
- `schedule_slots(resource_id, slot_date, status, start_at)`;
- `schedule_slots(resource_id, start_at)` UNIQUE;
- unique blocking reservation по `slot_id` partial;
- unique converted reservation по `appointment_id` partial;
- unique active `customer_checkout` reservation по `appointment_id` partial;
- `slot_reservations(status, expires_at)`;
- unique pending proposal по `appointment_id` partial;
- `reminders(status, next_attempt_at)`;
- `notification_outbox(status, next_attempt_at)`;
- `manager_requests(status, created_at)`;
- `admin_action_logs(actor_staff_id, created_at DESC)`;
- `admin_action_logs(entity_type, entity_id, created_at DESC)`.

Индексы подтверждаются `EXPLAIN` на реалистичном объёме перед production. Спецификация не обещает конкретное время ответа без измерения данных и хостинга.

## 24. Нефункциональные требования

- **Корректность:** занятость слота гарантируется PostgreSQL constraint, а не только UI.
- **Восстановление:** restart не теряет drafts, reservations, reminders и outbox.
- **Идемпотентность:** повторный Telegram update/callback не повторяет бизнес-переход.
- **Безопасность:** server-side RBAC, secrets вне репозитория, redaction PII.
- **Сопровождаемость:** модульный монолит, use cases независимо тестируются, migration-only schema.
- **Локализация времени:** в сообщении всегда выводятся локальная дата, время и понятное название timezone студии; в БД хранится UTC.
- **Доступность:** при кратком перезапуске процесс продолжает persistent jobs. Конкретный SLA не заявляется: исходные требования не задают инфраструктуру, резервирование БД или внешний мониторинг.
- **Масштаб:** v1 запускает один polling instance; queue locks допускают последующее выделение scheduler workers. Поддерживаемая нагрузка должна быть измерена load test, и без измерений числовое значение RPS подтвердить нельзя.

## 25. Решения, требующие подтверждения владельца до реализации

Эти значения нельзя достоверно вывести из задания:

1. IANA timezone и адрес студии.
2. Реальные классы автомобилей и правила их определения.
3. Каталог услуг и поддерживает ли заявка одну или несколько услуг.
4. Прайс, валюта, вид цены и срок актуальности quote.
5. Рабочие ресурсы/посты и длительность бесплатного осмотра.
6. TTL клиентского резерва, административного ожидания и предложения времени.
7. Горизонт расписания и максимальное число фото.
8. Напоминания и cut-off переноса/отмены.
9. Разрешён ли автоматический перенос или всегда нужен сотрудник.
10. Тексты согласия/уведомления о данных и политика retention.
11. Telegram ID первоначального owner и admin notification chat.
12. Конкретный hosting/process manager и backup storage.

До подтверждения используются явно помеченные конфигурационные defaults из раздела 3.3; они не зашиваются в доменную логику.

## 26. Порядок последующей реализации

1. Утвердить пункты раздела 25 и тексты интерфейса.
2. Создать skeleton, settings, logging и Alembic async environment.
3. Реализовать schema первой миграцией, constraints и seed owner.
4. Реализовать domain transitions и unit tests.
5. Реализовать repositories/UoW и concurrency tests reservations.
6. Реализовать PostgreSQL-backed draft state и booking flow.
7. Реализовать admin appointment workflow и audit.
8. Реализовать schedule/catalog/price/FAQ admin modules.
9. Реализовать outbox, scheduler, reminders и expiry.
10. Реализовать manager requests, estimate и client self-service.
11. Выполнить integration, handler, migration, restore и smoke tests.
12. Подготовить production environment, runbook, backup schedule и controlled release.

## 27. Критерий готовности проекта к разработке

Спецификация готова стать основой backlog после подтверждения раздела 25. Схема разделяет заявку, слот и резерв; обязательные статусы и роли заданы; конкурентная уникальность обеспечивается PostgreSQL; незавершённые процессы восстанавливаются без Redis; запуск, миграции, обновление и backup имеют проверяемую процедуру. Не подтверждённые бизнес-параметры явно перечислены и не представлены как факты.
