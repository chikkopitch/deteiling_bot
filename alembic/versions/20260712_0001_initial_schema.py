"""Create initial detailing bot schema.

Revision ID: 20260712_0001
Revises: None
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260712_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


admin_role = postgresql.ENUM("owner", "admin", "manager", name="admin_role", create_type=False)
appointment_status = postgresql.ENUM(
    "draft", "waiting_admin", "confirmed", "rejected", "cancelled_by_user",
    "cancelled_by_admin", "completed", "no_show",
    name="appointment_status", create_type=False,
)
media_type = postgresql.ENUM("photo", "document", name="media_type", create_type=False)
reservation_status = postgresql.ENUM(
    "active", "confirmed", "expired", "cancelled",
    name="reservation_status", create_type=False,
)
reminder_status = postgresql.ENUM(
    "pending", "processing", "sent", "failed", "cancelled",
    name="reminder_status", create_type=False,
)
manager_request_status = postgresql.ENUM(
    "open", "assigned", "waiting_customer", "waiting_manager", "resolved", "closed", "cancelled",
    name="manager_request_status", create_type=False,
)
sender_type = postgresql.ENUM("user", "admin", "system", name="sender_type", create_type=False)


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        admin_role, appointment_status, media_type, reservation_status,
        reminder_status, manager_request_status, sender_type,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        _id(),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128)),
        sa.Column("last_name", sa.String(128)),
        sa.Column("phone", sa.String(32)),
        sa.Column("is_blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_is_blocked", "users", ["is_blocked"])

    op.create_table(
        "admins",
        _id(),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("role", admin_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_admins"),
    )
    op.create_index("ix_admins_telegram_id", "admins", ["telegram_id"], unique=True)
    op.create_index("ix_admins_role_is_active", "admins", ["role", "is_active"])

    op.create_table(
        "vehicle_classes",
        _id(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("price_coefficient", sa.Numeric(8, 4), server_default=sa.text("1.0000"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("price_coefficient > 0", name="price_coefficient_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_vehicle_classes"),
        sa.UniqueConstraint("name", name="uq_vehicle_classes_name"),
    )
    op.create_index("ix_vehicle_classes_active_sort", "vehicle_classes", ["is_active", "sort_order"])

    op.create_table(
        "vehicle_brands",
        _id(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_vehicle_brands"),
        sa.UniqueConstraint("name", name="uq_vehicle_brands_name"),
    )
    op.create_index("ix_vehicle_brands_active_sort", "vehicle_brands", ["is_active", "sort_order"])

    op.create_table(
        "services",
        _id(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("short_description", sa.String(500)),
        sa.Column("full_description", sa.Text()),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_free_inspection", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("base_price >= 0", name="base_price_non_negative"),
        sa.CheckConstraint("duration_minutes > 0", name="duration_minutes_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )
    op.create_index("ix_services_active_sort", "services", ["is_active", "sort_order"])

    op.create_table(
        "available_slots",
        _id(),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("blocked_reason", sa.Text()),
        *_timestamps(),
        sa.CheckConstraint("ends_at > starts_at", name="time_range_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_available_slots"),
        sa.UniqueConstraint("starts_at", "ends_at", name="uq_available_slots_time_range"),
    )
    op.create_index("ix_available_slots_available_starts", "available_slots", ["is_available", "starts_at"])

    op.create_table(
        "faq_items",
        _id(),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_faq_items"),
    )
    op.create_index("ix_faq_items_active_category_sort", "faq_items", ["is_active", "category", "sort_order"])

    op.create_table(
        "content_settings",
        _id(),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_content_settings"),
        sa.UniqueConstraint("key", name="uq_content_settings_key"),
    )

    op.create_table(
        "vehicle_models",
        _id(),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["brand_id"], ["vehicle_brands.id"], name="fk_vehicle_models_brand_id_vehicle_brands", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_class_id"], ["vehicle_classes.id"], name="fk_vehicle_models_vehicle_class_id_vehicle_classes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_vehicle_models"),
        sa.UniqueConstraint("brand_id", "name", name="uq_vehicle_models_brand_name"),
    )
    op.create_index("ix_vehicle_models_brand_active_sort", "vehicle_models", ["brand_id", "is_active", "sort_order"])
    op.create_index("ix_vehicle_models_vehicle_class_id", "vehicle_models", ["vehicle_class_id"])

    op.create_table(
        "service_prices",
        _id(),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("min_price", sa.Numeric(12, 2)),
        sa.Column("max_price", sa.Numeric(12, 2)),
        *_timestamps(),
        sa.CheckConstraint("price >= 0", name="price_non_negative"),
        sa.CheckConstraint("min_price IS NULL OR min_price >= 0", name="min_price_non_negative"),
        sa.CheckConstraint("max_price IS NULL OR max_price >= 0", name="max_price_non_negative"),
        sa.CheckConstraint("min_price IS NULL OR max_price IS NULL OR min_price <= max_price", name="price_range_valid"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="fk_service_prices_service_id_services", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_class_id"], ["vehicle_classes.id"], name="fk_service_prices_vehicle_class_id_vehicle_classes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_service_prices"),
        sa.UniqueConstraint("service_id", "vehicle_class_id", name="uq_service_prices_service_class"),
    )
    op.create_index("ix_service_prices_vehicle_class_id", "service_prices", ["vehicle_class_id"])

    op.create_table(
        "conversation_states",
        _id(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flow", sa.String(64), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_conversation_states_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_states"),
        sa.UniqueConstraint("user_id", "flow", name="uq_conversation_states_user_flow"),
    )
    op.create_index("ix_conversation_states_expires_at", "conversation_states", ["expires_at"])

    op.create_table(
        "admin_audit_log",
        _id(),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], name="fk_admin_audit_log_admin_id_admins", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_admin_audit_log"),
    )
    op.create_index("ix_admin_audit_log_admin_created", "admin_audit_log", ["admin_id", "created_at"])
    op.create_index("ix_admin_audit_log_entity_created", "admin_audit_log", ["entity_type", "entity_id", "created_at"])

    op.create_table(
        "appointments",
        _id(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True)),
        sa.Column("vehicle_brand_id", postgresql.UUID(as_uuid=True)),
        sa.Column("vehicle_model_id", postgresql.UUID(as_uuid=True)),
        sa.Column("vehicle_class_id", postgresql.UUID(as_uuid=True)),
        sa.Column("custom_vehicle_brand", sa.String(120)),
        sa.Column("custom_vehicle_model", sa.String(120)),
        sa.Column("vehicle_year", sa.Integer()),
        sa.Column("vehicle_comment", sa.Text()),
        sa.Column("customer_name", sa.String(120)),
        sa.Column("customer_phone", sa.String(32)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("estimated_price_from", sa.Numeric(12, 2)),
        sa.Column("estimated_price_to", sa.Numeric(12, 2)),
        sa.Column("status", appointment_status, server_default="draft", nullable=False),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("confirmed_by_admin_id", postgresql.UUID(as_uuid=True)),
        *_timestamps(),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("vehicle_year IS NULL OR (vehicle_year > 0 AND vehicle_year <= 9999)", name="vehicle_year_valid"),
        sa.CheckConstraint("estimated_price_from IS NULL OR estimated_price_from >= 0", name="estimated_price_from_non_negative"),
        sa.CheckConstraint("estimated_price_to IS NULL OR estimated_price_to >= 0", name="estimated_price_to_non_negative"),
        sa.CheckConstraint("estimated_price_from IS NULL OR estimated_price_to IS NULL OR estimated_price_from <= estimated_price_to", name="estimated_price_range_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_appointments_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="fk_appointments_service_id_services", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_brand_id"], ["vehicle_brands.id"], name="fk_appointments_vehicle_brand_id_vehicle_brands", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_model_id"], ["vehicle_models.id"], name="fk_appointments_vehicle_model_id_vehicle_models", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_class_id"], ["vehicle_classes.id"], name="fk_appointments_vehicle_class_id_vehicle_classes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by_admin_id"], ["admins.id"], name="fk_appointments_confirmed_by_admin_id_admins", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
    )
    op.create_index("ix_appointments_user_status", "appointments", ["user_id", "status"])
    op.create_index("ix_appointments_status_scheduled_at", "appointments", ["status", "scheduled_at"])
    op.create_index("ix_appointments_service_id", "appointments", ["service_id"])
    op.create_index("ix_appointments_vehicle_brand_id", "appointments", ["vehicle_brand_id"])
    op.create_index("ix_appointments_vehicle_model_id", "appointments", ["vehicle_model_id"])
    op.create_index("ix_appointments_vehicle_class_id", "appointments", ["vehicle_class_id"])

    op.create_table(
        "appointment_photos",
        _id(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_file_id", sa.String(512), nullable=False),
        sa.Column("telegram_file_unique_id", sa.String(256), nullable=False),
        sa.Column("media_type", media_type, server_default="photo", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], name="fk_appointment_photos_appointment_id_appointments", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_photos"),
        sa.UniqueConstraint("appointment_id", "telegram_file_unique_id", name="uq_appointment_photos_appointment_file"),
    )
    op.create_index("ix_appointment_photos_appointment_id", "appointment_photos", ["appointment_id"])

    op.create_table(
        "appointment_slot_reservations",
        _id(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True)),
        sa.Column("status", reservation_status, server_default="active", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], name="fk_appointment_slot_reservations_appointment_id_appointments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["slot_id"], ["available_slots.id"], name="fk_appointment_slot_reservations_slot_id_available_slots", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_slot_reservations"),
        sa.UniqueConstraint("appointment_id", "slot_id", name="uq_reservations_appointment_slot"),
    )
    op.create_index("ix_reservations_status_reserved_until", "appointment_slot_reservations", ["status", "reserved_until"])
    op.create_index(
        "uq_reservations_blocking_slot", "appointment_slot_reservations", ["slot_id"],
        unique=True, postgresql_where=sa.text("status IN ('active', 'confirmed')"),
    )
    op.create_index(
        "uq_reservations_blocking_appointment", "appointment_slot_reservations", ["appointment_id"],
        unique=True, postgresql_where=sa.text("status IN ('active', 'confirmed')"),
    )

    op.create_table(
        "reminders",
        _id(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reminder_type", sa.String(64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", reminder_status, server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], name="fk_reminders_appointment_id_appointments", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_reminders"),
        sa.UniqueConstraint("appointment_id", "reminder_type", "scheduled_for", name="uq_reminders_appointment_type_time"),
    )
    op.create_index("ix_reminders_status_scheduled", "reminders", ["status", "scheduled_for"])

    op.create_table(
        "appointment_history",
        _id(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("changed_by_admin_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], name="fk_appointment_history_appointment_id_appointments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], name="fk_appointment_history_changed_by_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by_admin_id"], ["admins.id"], name="fk_appointment_history_changed_by_admin_id_admins", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_history"),
    )
    op.create_index("ix_appointment_history_appointment_created", "appointment_history", ["appointment_id", "created_at"])
    op.create_index("ix_appointment_history_changed_by_admin", "appointment_history", ["changed_by_admin_id"])

    op.create_table(
        "manager_requests",
        _id(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", manager_request_status, server_default="open", nullable=False),
        sa.Column("assigned_admin_id", postgresql.UUID(as_uuid=True)),
        *_timestamps(),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_manager_requests_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], name="fk_manager_requests_appointment_id_appointments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["admins.id"], name="fk_manager_requests_assigned_admin_id_admins", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_manager_requests"),
    )
    op.create_index("ix_manager_requests_status_created", "manager_requests", ["status", "created_at"])
    op.create_index("ix_manager_requests_user_id", "manager_requests", ["user_id"])
    op.create_index("ix_manager_requests_appointment_id", "manager_requests", ["appointment_id"])
    op.create_index("ix_manager_requests_assigned_admin_id", "manager_requests", ["assigned_admin_id"])

    op.create_table(
        "manager_request_messages",
        _id(),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_type", sender_type, nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("sender_admin_id", postgresql.UUID(as_uuid=True)),
        sa.Column("text", sa.Text()),
        sa.Column("telegram_file_id", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["manager_requests.id"], name="fk_manager_request_messages_request_id_manager_requests", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], name="fk_manager_request_messages_sender_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sender_admin_id"], ["admins.id"], name="fk_manager_request_messages_sender_admin_id_admins", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_manager_request_messages"),
    )
    op.create_index("ix_manager_request_messages_request_created", "manager_request_messages", ["request_id", "created_at"])


def downgrade() -> None:
    # History and dependent records are removed first only for an explicit full downgrade.
    for table_name in (
        "manager_request_messages",
        "manager_requests",
        "appointment_history",
        "reminders",
        "appointment_slot_reservations",
        "appointment_photos",
        "appointments",
        "admin_audit_log",
        "conversation_states",
        "service_prices",
        "vehicle_models",
        "content_settings",
        "faq_items",
        "available_slots",
        "services",
        "vehicle_brands",
        "vehicle_classes",
        "admins",
        "users",
    ):
        op.drop_table(table_name)

    bind = op.get_bind()
    for enum_type in (
        sender_type,
        manager_request_status,
        reminder_status,
        reservation_status,
        media_type,
        appointment_status,
        admin_role,
    ):
        enum_type.drop(bind, checkfirst=True)
