# Конфигурация

Обязательны: `BOT_TOKEN`, список числовых `ADMIN_IDS` через запятую, `MANAGER_USERNAME`, async `DATABASE_URL`, `REDIS_URL`, `STUDIO_NAME`, `STUDIO_ADDRESS`, `SUPPORT_PHONE`. `STUDIO_TIMEZONE` — IANA timezone; `REMINDER_HOURS_BEFORE` — часы через запятую; `MAX_PHOTOS_PER_BOOKING` — 0…20; `MAX_PHOTO_SIZE_MB` — 1…20; `SLOT_HOLD_MINUTES` — 1…60; `BOOKING_HORIZON_DAYS` — 1…365; `LOG_LEVEL` — DEBUG/INFO/WARNING/ERROR/CRITICAL; `MAP_URL` необязателен. Невалидная конфигурация останавливает запуск с ошибкой Pydantic.

