from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagSourceRead
from app.services.rag_service import retrieve


router = APIRouter()


@router.post("/query", response_model=RagQueryResponse)
async def query_rag(
    payload: RagQueryRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> RagQueryResponse:
    result = await retrieve(
        session,
        query=payload.query,
        tenant_id=ctx.tenant_id,
        top_k=payload.top_k,
        document_type_filter=payload.document_type_filter,
        actor_user_id=ctx.user_id,
    )
    await session.commit()
    return RagQueryResponse(
        query=result.query,
        answer_supported=result.answer_supported,
        sources=[RagSourceRead(**source.to_dict()) for source in result.sources],
        refusal_reason=result.refusal_reason,
    )
