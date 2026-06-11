from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suggested_reply import SuggestedReply


class SuggestedReplyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, reply_id: UUID) -> SuggestedReply | None:
        return await self.session.get(SuggestedReply, reply_id)

    async def list_for_conversation(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> list[SuggestedReply]:
        result = await self.session.execute(
            select(SuggestedReply)
            .where(
                SuggestedReply.tenant_id == tenant_id,
                SuggestedReply.conversation_id == conversation_id,
            )
            .order_by(SuggestedReply.created_at.desc(), SuggestedReply.id.desc())
        )
        return list(result.scalars().all())

    async def latest_for_conversation(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> SuggestedReply | None:
        result = await self.session.execute(
            select(SuggestedReply)
            .where(
                SuggestedReply.tenant_id == tenant_id,
                SuggestedReply.conversation_id == conversation_id,
            )
            .order_by(SuggestedReply.created_at.desc(), SuggestedReply.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def add(self, reply: SuggestedReply) -> SuggestedReply:
        self.session.add(reply)
        await self.session.flush()
        return reply
