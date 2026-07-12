# Telegram-бот детейлинг-студии

Production-oriented бот на Python 3.12 и aiogram 3: запись на бесплатный осмотр, автомобиль и услуги, фото, свободные слоты, контакты, админское подтверждение, напоминания, каталог, FAQ, диапазон стоимости и обращения менеджеру.

## Запуск

1. Скопируйте `.env.example` в `.env`, задайте реальный `BOT_TOKEN`, `ADMIN_IDS`, адрес и контакты.
2. Выполните `docker compose up --build`.
3. Миграция и seed запускаются контейнером автоматически. Откройте бота и отправьте `/start`; админка — `/admin`.

Проверки: `docker compose exec bot pytest`, `docker compose exec bot ruff check .`, `docker compose exec bot mypy app`. Миграции: `docker compose exec bot alembic upgrade head`. Остановка: `docker compose down`.

## Структура

`app/bot` — Telegram и FSM; `services` — бизнес-операции; `repositories` — запросы; `models` и `database` — данные; `scheduler` — напоминания; `config` — окружение; `alembic` — миграции; `tests` — автоматические проверки; `docs` — эксплуатация и архитектура.

Переменные подробно описаны в [docs/CONFIGURATION.md](docs/CONFIGURATION.md). Данные PostgreSQL и Redis сохраняются в Docker volumes. Цены и коэффициенты берутся из БД. Резервное копирование и production deployment описаны в документации.

