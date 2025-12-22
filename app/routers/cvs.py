# routers/cvs.py
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/cvs", tags=["cvs"])


@router.get("/{session_id}/jds/{jd_id}/cvs")
async def get_session_cvs(session_id: str, jd_id: str):
    """Get all CVs for a specific session and job description. Incremental add-cvs removed."""
    try:
        # This would typically fetch from database or AI agent
        return {"message": "Endpoint not implemented or removed (incremental add-cvs disallowed)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
