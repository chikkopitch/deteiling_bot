# Установка

Требуются Docker Engine с Compose v2 и токен Telegram-бота от BotFather. Скопируйте `.env.example` в `.env`, заполните обязательные значения и выполните `docker compose up --build`. Compose дождётся healthcheck PostgreSQL/Redis, применит `alembic upgrade head`, один раз заполнит справочники и запустит polling. Для локальной разработки нужен Python 3.12: `python -m venv .venv`, активация, `pip install -e ".[dev]"`.

