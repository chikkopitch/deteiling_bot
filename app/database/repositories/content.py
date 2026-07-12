"""FAQ and editable content repositories."""

from sqlalchemy import select

from app.database.models import ContentSetting, FAQItem
from app.database.repositories.base import BaseRepository


class FAQRepository(BaseRepository[FAQItem]):
    model = FAQItem

    async def list_active(self, category: str | None = None) -> list[FAQItem]:
        statement = select(FAQItem).where(FAQItem.is_active.is_(True))
        if category is not None:
            statement = statement.where(FAQItem.category == category)
        result = await self.session.execute(
            statement.order_by(FAQItem.sort_order, FAQItem.question)
        )
        return list(result.scalars())


class ContentSettingRepository(BaseRepository[ContentSetting]):
    model = ContentSetting

    async def get_by_key(self, key: str) -> ContentSetting | None:
        result = await self.session.execute(
            select(ContentSetting).where(ContentSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: str) -> str:
        setting = await self.get_by_key(key)
        return setting.value if setting is not None else default
