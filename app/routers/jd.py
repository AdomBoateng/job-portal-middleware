# routers/jd.py
from fastapi import APIRouter, HTTPException, Depends
from app.services.db import get_db
from app.services import job_portal_client, ai_agent_client
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

router = APIRouter(prefix="/jds", tags=["job-descriptions"])

@router.get("/", summary="Get all job IDs from job portal")
async def get_all_job_ids() -> List[int]:
    """Fetch all available job IDs from the job portal."""
    try:
        job_ids = await job_portal_client.fetch_all_job_ids()
        return job_ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching job IDs: {str(e)}")

@router.get("/{jd_id}", summary="Get job description details")
async def get_job_description(jd_id: int) -> Dict[str, Any]:
    """Fetch detailed job description from job portal."""
    try:
        jd_details = await job_portal_client.fetch_jd(jd_id)
        return jd_details
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job description not found: {str(e)}")

@router.get("/{jd_id}/applications", summary="Get applications for a job")
async def get_job_applications(jd_id: int) -> List[Dict[str, Any]]:
    """Fetch all applications/CVs for a specific job."""
    try:
        applications = await job_portal_client.fetch_cvs_for_jd(jd_id)
        return applications
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching applications: {str(e)}")

@router.post("/{jd_id}/match", summary="Trigger AI matching for a job")
async def trigger_job_matching(jd_id: int, session_id: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger AI matching for a specific job."""
    try:
        result = await ai_agent_client.match_jd(session_id, str(jd_id))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering AI matching: {str(e)}")

@router.post("/{jd_id}/results", summary="Push match results back to job portal")
async def push_match_results(jd_id: int, results: List[Dict[str, Any]]):
    """Push AI matching results back to the job portal."""
    try:
        response = await job_portal_client.update_application_match(str(jd_id), results)
        return {"message": "Results pushed successfully", "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error pushing results: {str(e)}")
