# Схема базы данных

Общие правила: PK — `uuid`; временные поля — `timestamptz` UTC; все сущности, кроме связующей таблицы, имеют `created_at`, а изменяемые — также `updated_at`. FK имеют явное `on delete`; бизнес-удаление каталога — soft delete.

| Сущность | Поля и статусы | Связи, индексы и ограничения |
| --- | --- | --- |
| `User` | `telegram_id bigint`, username, first/last name, phone E.164, role (`client/admin/manager`), is_active, timestamps | unique/index `telegram_id`; владелец Vehicle, Booking, ManagerRequest, Notification, AuditLog. |
| `VehicleBrand` | name, is_popular, is_active, timestamps | unique name; один ко многим VehicleModel. |
| `VehicleModel` | `brand_id`, name, is_active, timestamps | unique `(brand_id,name)`; FK cascade при удалении бренда. |
| `Vehicle` | `user_id`, brand_name, model_name, year, vehicle_class, timestamps | index user; check year 1980…текущий+1 логикой приложения; снимок марки/модели не ломается при изменении справочника. |
| `ServiceCategory` | name, sort_order, is_active, timestamps | unique name; один ко многим Service. |
| `Service` | `category_id`, name, short_description, includes, duration_minutes, price_from numeric, suitable_for, sort_order, is_active, deleted_at, timestamps | index active services; check неотрицательной цены и положительной длительности; FK restrict. |
| `PriceRule` | `service_id`, vehicle_class/size, base_price, class_coefficient, condition_coefficients JSON, options JSON, min_price, max_price, is_active, timestamps | FK cascade; unique `(service_id,vehicle_class)`; checks min≥0, max≥min, coefficient>0. |
| `StudioSchedule` | weekday, opens_at, closes_at, breaks JSON, effective_date nullable, is_closed, slot_minutes, booking_horizon, timestamps | unique `(weekday,effective_date)`; checks weekday 0…6, close>open, slot minutes>0. |
| `TimeSlot` | starts_at, ends_at, status (`available/held/booked/blocked`), held_by_user_id nullable, hold_expires_at, timestamps | unique/index starts_at; check end>start; FK held user set null. |
| `Booking` | user_id, vehicle_id, slot_id nullable, status, customer_name/phone, comment, estimated_min/max, cancellation_reason, idempotency_key, timestamps | indexes user/status; unique `slot_id` для active записи реализуется partial unique index PostgreSQL; unique idempotency key; Service many-to-many. |
| `BookingPhoto` | booking_id, file_id, unique_file_id, mime_type, size_bytes, sort_order, created_at | FK cascade; unique `(booking_id,unique_file_id)` и `(booking_id,sort_order)`; check size≥0. |
| `FAQItem` | category, question, answer, keywords, sort_order, is_active, deleted_at, timestamps | index `(is_active,category,sort_order)` и search index по question/keywords. |
| `ManagerRequest` | user_id, text, phone, photo_file_ids JSON, status (`open/answered/closed`), response, timestamps | index status/created_at; FK restrict User. |
| `Notification` | booking_id, user_id, type, scheduled_at, sent_at, status (`pending/sent/retry/cancelled/failed`), attempts, last_error, idempotency_key, timestamps | index `(status,scheduled_at)`; unique idempotency key; FK cascade. |
| `AuditLog` | actor_user_id nullable, action, entity_type, entity_id, details JSON, created_at | index `(entity_type,entity_id,created_at)` и actor/created_at; FK actor set null. |

Связующая `booking_services` содержит `booking_id`, `service_id` и составной PK; удаление Booking cascade, Service restrict. Миграции Alembic создают PostgreSQL enum-типы до таблиц и должны уметь `upgrade` и `downgrade`; production startup не вызывает `create_all`.

