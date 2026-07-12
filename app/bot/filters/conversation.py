"""Filter messages by persistent conversation step."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories import ConversationStateRepository
from app.services.vehicle_selection import FLOW_NAMES_TO_CODES


class ConversationStepFilter(BaseFilter):
    def __init__(self, *steps: str) -> None:
        self.steps = frozenset(steps)

    async def __call__(
        self,
        message: Message,
        app_user: User,
        session: AsyncSession,
    ) -> bool | dict[str, Any]:
        state = await ConversationStateRepository(session).get_latest_active(
            app_user.id, datetime.now(UTC)
        )
        if state is None or state.step not in self.steps:
            return False
        flow_code = FLOW_NAMES_TO_CODES.get(state.flow)
        if flow_code is None:
            return False
        return {"conversation_state": state, "vehicle_flow_code": flow_code}
