# Резервное копирование и восстановление

Backup: `docker compose exec -T postgres pg_dump -U detailing -Fc detailing > detailing.dump`. Redis содержит временные состояния и не заменяет PostgreSQL backup. Восстановление выполняйте при остановленном bot: создайте чистую БД и запустите `pg_restore --clean --if-exists -U detailing -d detailing`. Затем примените `alembic upgrade head`, запустите bot и проверьте количество записей и ближайшие уведомления. Регулярно тестируйте восстановление на отдельной среде.

