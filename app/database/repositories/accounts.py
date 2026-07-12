"""Customer and administrator repositories."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database.enums import AdminRole
from app.database.models import Admin, User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            return await self.add(user)

        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        await self.session.flush()
        return user

    async def upsert_telegram_profile(
        self,
        telegram_id: int,
        *,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        """Atomically create or refresh a Telegram profile by numeric ID."""
        statement = (
            insert(User)
            .values(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            .on_conflict_do_update(
                index_elements=[User.telegram_id],
                set_={
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
            .returning(User)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()


class AdminRepository(BaseRepository[Admin]):
    model = Admin

    async def get_by_telegram_id(self, telegram_id: int) -> Admin | None:
        result = await self.session.execute(
            select(Admin).where(Admin.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list_active(self, role: AdminRole | None = None) -> list[Admin]:
        statement = select(Admin).where(Admin.is_active.is_(True))
        if role is not None:
            statement = statement.where(Admin.role == role)
        result = await self.session.execute(statement.order_by(Admin.created_at))
        return list(result.scalars())
