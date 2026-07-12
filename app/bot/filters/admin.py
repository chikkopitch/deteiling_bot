from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsAdmin(BaseFilter):
    def __init__(self, admin_ids: tuple[int, ...]) -> None:
        self.admin_ids = admin_ids

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in self.admin_ids)
