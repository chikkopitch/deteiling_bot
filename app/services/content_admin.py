from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Admin, AdminAuditLog, ContentSetting
from app.database.repositories import AdminAuditLogRepository, ContentSettingRepository
from app.services.vehicle_selection import clean_user_text

EDITABLE_CONTENT = {
    "welcome_text": "Приветствие",
    "studio_description": "Описание студии",
    "studio_address": "Адрес",
    "studio_phone": "Телефон",
    "manager_telegram": "Telegram менеджера",
    "working_hours": "Режим работы",
    "application_sent_message": "Сообщение после заявки",
    "confirmation_message": "Сообщение подтверждения",
    "cancellation_rules": "Правила отмены",
    "reminder_hours": "Интервалы напоминаний",
    "calculator_description": "Описание калькулятора",
}


@dataclass(frozen=True)
class ContentPreview:
    key: str
    old_value: str
    new_value: str


class ContentAdminService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.content = ContentSettingRepository(session)
        self.audit = AdminAuditLogRepository(session)

    async def preview(self, key, value):
        if key not in EDITABLE_CONTENT:
            raise ValueError("Настройка недоступна.")
        value = clean_user_text(value, min_length=1, max_length=10000)
        if key == "reminder_hours":
            try:
                hours = [int(item.strip()) for item in value.split(",") if item.strip()]
                if not hours or any(hour <= 0 or hour > 720 for hour in hours):
                    raise ValueError
            except ValueError as error:
                raise ValueError(
                    "Интервалы задаются положительными часами через запятую."
                ) from error
        setting = await self.content.get_by_key(key)
        return ContentPreview(key, setting.value if setting else "", value)

    async def save(self, admin: Admin, preview: ContentPreview):
        setting = await self.content.get_by_key(preview.key)
        if setting is None:
            setting = ContentSetting(key=preview.key, value=preview.new_value)
            self.session.add(setting)
            await self.session.flush()
        else:
            setting.value = preview.new_value
        await self.audit.add(
            AdminAuditLog(
                admin_id=admin.id,
                action="content_updated",
                entity_type="content_setting",
                entity_id=setting.id,
                old_value={"value": preview.old_value},
                new_value={"value": preview.new_value},
            )
        )
        await self.session.flush()
        return setting


async def effective_reminder_hours(
    session: AsyncSession, fallback: tuple[int, ...]
) -> tuple[int, ...]:
    setting = await ContentSettingRepository(session).get_by_key("reminder_hours")
    if setting is None:
        return fallback
    try:
        values = tuple(
            sorted(
                {
                    int(item.strip())
                    for item in setting.value.split(",")
                    if item.strip()
                },
                reverse=True,
            )
        )
        if not values or any(value <= 0 or value > 720 for value in values):
            raise ValueError
        return values
    except ValueError:
        return fallback
