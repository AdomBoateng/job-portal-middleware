# routers/cvs.py
from fastapi import APIRouter, HTTPException, Depends
from app.services.ai_agent_client import add_cvs_to_session_with_jd
from app.services.db import get_db
from app.helpers.validation import AddCVsRequest, SuccessResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/cvs", tags=["cvs"])

@router.post("/{session_id}/jds/{jd_id}/add-cvs", response_model=SuccessResponse)
async def add_cvs_incremental(
    session_id: str, 
    jd_id: str, 
    payload: AddCVsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Middleware receives CVs from job portal (or other) and forwards incremental CVs to AI Agent.
    Returns only the new CV results from AI Agent.
    """
    try:
        res = await add_cvs_to_session_with_jd(session_id, jd_id, payload.dict())
        return SuccessResponse(
            message="CVs added successfully",
            data=res
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/jds/{jd_id}/cvs")
async def get_session_cvs(session_id: str, jd_id: str):
    """Get all CVs for a specific session and job description."""
    try:
        # This would typically fetch from database or AI agent
        return {"message": "Endpoint not implemented yet"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
