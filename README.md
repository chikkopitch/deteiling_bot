# Telegram-бот детейлинг-студии

Telegram-бот записи в детейлинг-студию на Python, Aiogram и PostgreSQL. Бот ведёт клиента от выбора автомобиля и услуги до временного резерва слота и отправки заявки, уведомляет сотрудников, поддерживает изменения записи, FAQ, калькулятор, обращения к менеджеру и административное управление контентом.

## Ограничения

Проект не использует Docker, Redis и SQLite. Для запуска требуется доступный PostgreSQL и постоянный Python-процесс.

## Требования

- Python 3.12;
- PostgreSQL;
- токен Telegram-бота;
- Windows PowerShell либо Linux/macOS shell.

## Структура

```text
app/
├── bot/                 # handlers, keyboards, middleware и states
├── core/                # конфигурация, logging и обработка ошибок
├── database/            # модели, репозитории, AsyncEngine/AsyncSession
├── scheduler/           # очистка резервов и отправка напоминаний
├── services/            # прикладные сценарии
└── main.py              # сборка приложения и lifecycle
alembic/
└── versions/            # последовательные миграции PostgreSQL
scripts/
├── check_database.py
├── cleanup_expired_reservations.py
├── create_owner.py
└── seed_initial_data.py
tests/
├── integration/         # тесты на отдельной PostgreSQL
└── test_*.py            # unit и handler/service tests
start.py                 # единая точка запуска
```

## Установка

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

После копирования заполните `.env` реальными значениями. Файл `.env` исключён из Git.

## Конфигурация

```dotenv
BOT_TOKEN=123456789:replace_with_real_token
DATABASE_URL=postgresql+asyncpg://detailing_bot:password@localhost:5432/detailing_bot
OWNER_TELEGRAM_ID=123456789
ADMIN_TELEGRAM_IDS=111111111,222222222
APP_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
```

Правила:

- `DATABASE_URL` должен начинаться с `postgresql+asyncpg://`;
- `OWNER_TELEGRAM_ID` — один положительный числовой Telegram ID;
- `ADMIN_TELEGRAM_IDS` — необязательный список положительных ID через запятую; пробелы допускаются, повторы удаляются;
- `APP_TIMEZONE` — имя IANA timezone;
- допустимые уровни логирования: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`.

Username Telegram не используется как ID или средство авторизации.

## Проверка PostgreSQL

Отдельная команда загружает `.env`, создаёт тот же async engine, выполняет `SELECT 1` и в любом случае закрывает pool:

```text
python scripts/check_database.py
```

Успех завершается exit code `0`; ошибка — exit code `1`.

## Alembic

Конфигурация Alembic получает `DATABASE_URL` из `.env`. Создание ORM-таблиц при запуске приложения не выполняется: схема изменяется только миграциями.

Проверить текущую ревизию:

```text
python -m alembic current
```

Создать ревизию после добавления моделей:

```text
python -m alembic revision --autogenerate -m "create initial schema"
```

Применить миграции:

```text
python -m alembic upgrade head
```

Первая миграция `20260712_0001` создаёт 19 таблиц, PostgreSQL Enum, внешние ключи, ограничения и индексы. Применить её можно командой `python -m alembic upgrade head`.

ORM-модели сгруппированы в `app/database/models`, Enum — в `app/database/enums.py`, репозитории — в `app/database/repositories`. Репозитории не выполняют скрытый `commit`: транзакцией управляет вызывающий application service.

## Запуск

```text
python start.py
```

Последовательность запуска:

1. конфигурация загружается и валидируется;
2. настраивается logging;
3. создаются SQLAlchemy AsyncEngine и AsyncSession factory;
4. PostgreSQL проверяется запросом `SELECT 1`;
5. startup hook повторно проверяет БД и вызывает Telegram `getMe`;
6. запускаются по одному worker очистки резервов и напоминаний;
7. начинается long polling.

SIGINT и SIGTERM останавливают polling, после чего закрываются HTTP-сессия Telegram и pool SQLAlchemy. Ошибка startup приводит к exit code `1`.

Пользовательский вход:

- middleware атомарно создаёт или обновляет пользователя по числовому Telegram ID;
- `/start` загружает `welcome_text` из `content_settings`, а при его отсутствии использует безопасный текст по умолчанию;
- незавершённый `draft` предлагает продолжить, начать заново или закрыть черновик;
- `/menu` открывает reply-меню, `/help` показывает справку;
- `/cancel` удаляет временное состояние, логически закрывает только черновик и освобождает активный временный резерв; подтверждённая запись не изменяется;
- заблокированный пользователь останавливается middleware до прикладного обработчика;
- вложенные разделы используют inline-кнопку «Назад»;
- необработанная ошибка получает короткий ID, записывается в лог и не раскрывает stack trace пользователю.

Выбор автомобиля для записи и расчёта стоимости:

- активные марки и модели показываются inline-страницами максимум по восемь элементов;
- поиск работает по части названия без учёта регистра;
- неизвестные марка и модель принимаются текстом после очистки управляющих символов;
- для справочной модели класс автомобиля подставляется автоматически, для ручной модели выбирается пользователем;
- допустимый год — от 1900 до следующего календарного года включительно, год можно пропустить;
- после каждого действия обновляется PostgreSQL `conversation_states`, а в booking-потоке также обновляется `appointments`;
- сохранённый шаг восстанавливается после повторного `/start` → «Продолжить»; незавершённый расчёт продолжается при повторном выборе «Рассчитать стоимость».

Услуги и фотографии:

- активные услуги читаются из PostgreSQL и показываются карточками с описанием, ориентировочной ценой и длительностью;
- `service_prices` для выбранного класса имеет приоритет, иначе используется `base_price × price_coefficient`;
- доступны бесплатный осмотр и вариант консультации; консультация сохраняется в комментарии, не стирая автомобиль;
- принимаются Telegram photo и документы с заявленным MIME `image/*`; файлы не скачиваются, сохраняются только `file_id` и `file_unique_id`;
- одна заявка принимает от 0 до 10 уникальных фотографий;
- можно завершить, пропустить, удалить последнее фото, вернуться назад или отменить сценарий;
- после завершения состояние переводится на `date_selection`.

Расписание и временные резервы:

- все интервалы хранятся в `available_slots`, занятость — в `appointment_slot_reservations`;
- календарь показывает только локальные даты с доступными слотами в `APP_TIMEZONE`;
- прошлые даты недоступны, переход между месяцами ограничен `BOOKING_DAYS_AHEAD`;
- выбор времени повторно проверяется под `SELECT FOR UPDATE` и защищён частичными уникальными индексами;
- временный резерв действует `SLOT_RESERVATION_MINUTES`, его `slot_id` и UTC-время сохраняются в заявке;
- при конфликте остальные данные черновика сохраняются, а пользователю показывается обновлённый список времени;
- встроенный async worker без Redis каждые `RESERVATION_CLEANUP_SECONDS` переводит просроченные резервы в `expired`, освобождает будущие слоты и возвращает черновик к календарю.

Контакты, отправка и административный вход:

- имя предлагается из Telegram-профиля либо вводится вручную, очищается и сразу сохраняется;
- российские номера `8XXXXXXXXXX`, `7XXXXXXXXXX` и `+7XXXXXXXXXX` нормализуются к `+7XXXXXXXXXX`;
- Telegram contact принимается только как собственный, когда Telegram передал `contact.user_id`;
- итоговая карточка повторно собирается из PostgreSQL и позволяет изменить автомобиль, услугу, время или контакты;
- отправка блокирует заявку, резерв и слот, подтверждает резерв, переводит заявку в `waiting_admin`, пишет историю и удаляет conversation state;
- истёкший резерв возвращает пользователя к календарю, сохраняя автомобиль, услугу и контакты;
- активные сотрудники получают сводку и связанные `file_id`; группы ограничены десятью элементами, подпись находится только у первого элемента;
- `/admin` и каждый administrative callback повторно проверяют числовой Telegram ID, `is_active`, роль и конкретное permission в PostgreSQL;
- callback data не содержит и не подтверждает роль пользователя.

Настройки по умолчанию:

```dotenv
BOOKING_DAYS_AHEAD=30
SLOT_RESERVATION_MINUTES=15
RESERVATION_CLEANUP_SECONDS=60
REMINDER_HOURS=24,2
REMINDER_CHECK_INTERVAL_SECONDS=60
REMINDER_MAX_ATTEMPTS=5
REMINDER_PROCESSING_TIMEOUT_MINUTES=10
APPOINTMENT_CHANGE_DEADLINE_HOURS=3
```

Раздел «Мои записи» делит записи на активные, завершённые и отменённые и
показывает услугу, автомобиль, статус и локальные дату и время. Самостоятельные
перенос и отмена запрещаются менее чем за
`APPOINTMENT_CHANGE_DEADLINE_HOURS` до визита.

При переносе новый слот сначала получает отдельный временный резерв, а старый
подтверждённый слот остаётся занятым. Только финальное подтверждение одной
транзакцией закрепляет новый резерв, освобождает старый слот, переносит время,
заменяет напоминания и пишет историю. Если новый резерв истёк или слот стал
недоступен, старая запись не изменяется. Администратор использует те же операции
с серверной проверкой разрешения и записью в аудит, но может обойти пользовательский
срок изменения.

## Каталог, FAQ и калькулятор

Раздел «Услуги» читает только активные записи `services`, показывает полное или
краткое описание, минимальную и максимальную цену из `service_prices`,
длительность и постраничные кнопки записи и расчёта.

FAQ сначала выводит категории, затем вопросы выбранной категории. Локальный
поиск нормализует регистр, `ё/е`, пунктуацию и пробелы, после чего ранжирует
совпадения в вопросе, `keywords` и ответе. Внешние API и нейросети для поиска не
используются.

Правила предварительного расчёта находятся в PostgreSQL:

- `calculation_factors` — загрязнение, шерсть, пятна, кузов и дополнительные услуги;
- `calculation_factor_values` — варианты, коэффициенты и фиксированные доплаты;
- `service_factor_compatibility` — применимость факторов к услугам;
- `price_calculations` — сохранённые входные данные и результат расчёта.

Формула диапазона: `базовая цена × произведение коэффициентов + сумма доплат`.
Обе границы рассчитываются независимо через Python `Decimal` и округляются до
двух знаков по `ROUND_HALF_UP`. Дополнительные услуги настраиваются как фактор с
`input_type=multiple`; остальные параметры обычно используют `single`.

Миграция калькулятора:

```text
python -m alembic upgrade head
```

## Обращения к менеджеру и управление контентом

Пользователь выбирает тему обращения, вводит сообщение и может приложить до
пяти Telegram-фотографий. После проверки создаются `manager_requests` и первое
сообщение в `manager_request_messages`; файлы не скачиваются, сохраняются их
`file_id`. Активные менеджеры получают уведомление и могут открыть обращение,
назначить его себе, ответить текстом или фотографией, закрыть, переоткрыть либо
передать командой `/transfer TELEGRAM_ID`.

Для каждого ответа сохраняются `delivery_status`, `delivery_error` и
`delivered_at`. Telegram Forbidden помечает доставку как `blocked` и пользователя
как заблокировавшего бота; остальные ошибки Bot API сохраняются как `failed`.

В `/admin` доступны подтверждаемые изменения контентных настроек, услуг, цен,
FAQ и параметров калькулятора. Перед сохранением бот показывает старое и новое
значения. Сохранение создаёт `admin_audit_log`; отмена или предпросмотр базовые
данные и аудит не изменяют. Интервалы напоминаний из `content_settings` с ключом
`reminder_hours` имеют приоритет над `.env`, если значение корректно.

Миграция `20260713_0004` добавляет поля результата доставки сообщений менеджера.

Подтверждение и отклонение заявки выполняются транзакционно после блокировки
строки заявки. Подтверждение проверяет закреплённый слот и резерв, записывает
администратора и время подтверждения, создаёт историю, аудит и уникальные
напоминания. Отклонение сохраняет причину, освобождает слот, отменяет резерв и
будущие напоминания, после чего уведомляет клиента.

Очередь напоминаний хранится только в PostgreSQL. Встроенный scheduler выбирает
наступившие задачи через `FOR UPDATE SKIP LOCKED`, переводит их в `processing` и
отправляет после фиксации транзакции. Ошибка отправки увеличивает `attempts` и
возвращает задачу в `pending`; после `REMINDER_MAX_ATTEMPTS` задача получает
`failed`. Зависшие `processing` старше
`REMINDER_PROCESSING_TIMEOUT_MINUTES` возвращаются в очередь тем же механизмом.
Redis для этого процесса не требуется.

## Тесты

```text
python -m pytest
```

Тесты без внешней БД проверяют parsing нескольких `ADMIN_TELEGRAM_IDS`, timezone по умолчанию, запрет не-PostgreSQL URL и сборку дерева роутеров. PostgreSQL-тесты проверяют подключение в UTC, создание основной связанной модели данных, `NUMERIC` и чтение через репозиторий.

Интеграционные тесты используют только `TEST_DATABASE_URL`. В целях защиты имя базы обязательно должно оканчиваться на `_test`; схема этой базы очищается и создаётся заново во время теста. Если переменная не задана, PostgreSQL-тесты отмечаются как пропущенные, SQLite не используется.

## Эксплуатация без Docker

На обычном Python-хостинге запускайте `python start.py` через process manager, поддерживающий постоянный процесс и передачу SIGTERM. Перед обновлением остановите приложение, создайте backup PostgreSQL, примените `python -m alembic upgrade head`, затем снова запустите процесс.

Не запускайте одновременно несколько polling-процессов с одним токеном. В одном процессе каждый scheduler создаётся ровно один раз в `app/main.py`.

## Первоначальная настройка и служебные команды

После создания базы и заполнения `.env` выполните команды в указанном порядке:

```text
python scripts/check_database.py
python -m alembic upgrade head
python scripts/seed_initial_data.py
python scripts/create_owner.py 123456789
python start.py
```

`seed_initial_data.py` идемпотентно добавляет четыре класса автомобилей, бесплатный осмотр, три примера услуг и базовые редактируемые тексты. Существующие строки с теми же уникальными ключами или названиями не изменяются. `create_owner.py` создаёт owner, активирует или повышает уже существующего сотрудника и не создаёт дубль. Если аргумент не указан, ID читается из `OWNER_TELEGRAM_ID`.

Ручная очистка просроченных временных резервов:

```text
python scripts/cleanup_expired_reservations.py
```

## Обновление и перезапуск на Python-хостинге

1. Остановите текущий процесс бота.
2. Создайте резервную копию PostgreSQL.
3. Замените файлы приложения, не перезаписывая рабочий `.env`.
4. Активируйте виртуальное окружение и выполните `python -m pip install -r requirements.txt`.
5. Выполните `python scripts/check_database.py` и `python -m alembic upgrade head`.
6. Запустите процесс командой `python start.py`.

На панели Python-хостинга команда запуска должна быть `python start.py`, рабочий каталог — корень проекта, а значения из `.env.example` должны быть заданы как переменные окружения или в локальном `.env`. Логи выводятся в stdout/stderr.

## systemd на VPS

Пример `/etc/systemd/system/detailing-bot.service` (пути и пользователя замените своими):

```ini
[Unit]
Description=Detailing Telegram bot
After=network-online.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/detailing-bot
EnvironmentFile=/opt/detailing-bot/.env
ExecStart=/opt/detailing-bot/.venv/bin/python /opt/detailing-bot/start.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Применение и просмотр логов:

```text
sudo systemctl daemon-reload
sudo systemctl enable --now detailing-bot
sudo systemctl restart detailing-bot
sudo journalctl -u detailing-bot -f
```

## Резервное копирование и восстановление PostgreSQL

Создать архив в custom-формате:

```text
pg_dump --format=custom --file=detailing_bot.dump --dbname="postgresql://USER@HOST:5432/detailing_bot"
```

Восстанавливайте сначала в пустую базу и проверяйте результат до переключения приложения:

```text
createdb --host=HOST --username=USER detailing_bot_restore
pg_restore --exit-on-error --clean --if-exists --no-owner --dbname="postgresql://USER@HOST:5432/detailing_bot_restore" detailing_bot.dump
```

Пароль не помещайте в команду или репозиторий: используйте защищённый `.pgpass` либо запрос пароля клиентом PostgreSQL.

## Типовые ошибки и диагностика

- `DATABASE_URL must start ...` — используйте схему `postgresql+asyncpg://` в приложении и Alembic.
- `PostgreSQL connection failed` — проверьте адрес, порт, имя базы, пользователя, сетевой доступ и затем повторите `python scripts/check_database.py`.
- Ошибка Alembic — выполните `python -m alembic current`, `python -m alembic heads` и убедитесь, что используется нужная база; не редактируйте уже применённые ревизии.
- `Unauthorized` или `Conflict` Telegram API — проверьте токен и отсутствие второго polling-процесса с тем же ботом.
- Команда `/admin` не открывается — проверьте числовой Telegram ID, активность строки в `admins` и роль, затем повторите `python scripts/create_owner.py ID` для владельца.
- Напоминания не приходят — проверьте статус заявки, `scheduled_at`, строки `reminders`, часовой пояс, stdout процесса и значения `REMINDER_*`.
