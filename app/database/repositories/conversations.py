"""PostgreSQL-backed conversation state repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.database.models import ConversationState
from app.database.repositories.base import BaseRepository


class ConversationStateRepository(BaseRepository[ConversationState]):
    model = ConversationState

    async def get_for_flow(self, user_id: UUID, flow: str) -> ConversationState | None:
        result = await self.session.execute(
            select(ConversationState).where(
                ConversationState.user_id == user_id,
                ConversationState.flow == flow,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_flow(
        self, user_id: UUID, flow: str, now: datetime
    ) -> ConversationState | None:
        result = await self.session.execute(
            select(ConversationState).where(
                ConversationState.user_id == user_id,
                ConversationState.flow == flow,
                ConversationState.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_active(
        self, user_id: UUID, now: datetime
    ) -> ConversationState | None:
        result = await self.session.execute(
            select(ConversationState)
            .where(
                ConversationState.user_id == user_id,
                ConversationState.expires_at > now,
            )
            .order_by(ConversationState.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: UUID,
        flow: str,
        step: str,
        payload: dict,
        expires_at: datetime,
    ) -> ConversationState:
        statement = (
            insert(ConversationState)
            .values(
                user_id=user_id,
                flow=flow,
                step=step,
                payload=payload,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                constraint="uq_conversation_states_user_flow",
                set_={
                    "step": step,
                    "payload": payload,
                    "expires_at": expires_at,
                    "updated_at": func.now(),
                },
            )
            .returning(ConversationState)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()
