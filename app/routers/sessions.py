# routers/sessions.py
from fastapi import APIRouter, HTTPException, Depends
from app.services.db import get_db
from app.services.orchestrator import create_middleware_session, process_session
from app.models.models import CreateSessionRequest, MiddlewareSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("/", summary="Create middleware session")
async def create_session(payload: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    res = await create_middleware_session(db, payload.jd_id, payload.cv_ids)
    return res

@router.post("/{session_id}/process", summary="Process (orchestrate) a session")
async def process(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        r = await process_session(session_id, db)
        return r
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}", summary="Get session info")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    q = select(MiddlewareSession).where(MiddlewareSession.session_id == session_id)
    res = await db.execute(q)
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": s.session_id,
        "jd_id": s.jd_id,
        "cv_ids": s.cv_ids,
        "ai_session_id": s.ai_session_id,
        "status": s.status,
        "last_checked": s.last_checked
    }

# Incremental "add CVs" functionality removed to enforce one-application-per-session policy.
# Any new application should create its own session via the `/applications/process` endpoint.
