# routers/report.py
from fastapi import APIRouter, HTTPException, Depends
from app.services.ai_agent_client import fetch_report
from app.services.job_portal_client import update_application_match
from app.services.db import get_db
from app.models.models import MiddlewareReport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List
import json

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/{session_id}/jds/{jd_id}")
async def get_report(
    session_id: str, 
    jd_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get AI processing report for a session and job description.
    Also pushes results back to job portal.
    Handles the new match report format with match_report_id and multiple reports.
    """
    try:
        report = await fetch_report(session_id, jd_id)

        # Push results back to job portal if report is complete
        if report and report.get("status") == "completed":
            match_results = report.get("match_results", [])
            if match_results:
                # Process results for job portal format
                from app.services.monitor import process_match_results_for_job_portal
                processed_results = process_match_results_for_job_portal(match_results)
                await update_application_match(jd_id, processed_results)

        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/stored-reports")
async def get_stored_reports_for_session(
    session_id: str,
    jd_id: str = None,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get all stored match reports for a session, optionally filtered by jd_id.
    """
    try:
        from app.services.monitor import get_stored_reports
        reports = await get_stored_reports(db, session_id, jd_id)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/jds/{jd_id}/stored-reports")
async def get_stored_reports_for_session_and_jd(
    session_id: str,
    jd_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get stored match reports for a specific session and jd_id combination.
    """
    try:
        from app.services.monitor import get_stored_reports
        reports = await get_stored_reports(db, session_id, jd_id)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/status")
async def get_session_status(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the current status of a session."""
    try:
        # This would fetch session status from database
        return {"message": "Endpoint not implemented yet", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/stored-reports")
async def get_stored_reports(
    session_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get all stored match reports for a session."""
    try:
        stmt = select(MiddlewareReport).where(MiddlewareReport.session_id == session_id)
        result = await db.execute(stmt)
        reports = result.scalars().all()
        
        stored_reports = []
        for report in reports:
            report_data = {
                "id": report.id,
                "match_report_id": report.match_report_id,
                "session_id": report.session_id,
                "jd_id": report.jd_id,
                "summary": report.summary,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "ai_created_at": report.ai_created_at
            }
            
            # Parse match results from JSON
            if report.match_results:
                try:
                    report_data["match_results"] = json.loads(report.match_results)
                except json.JSONDecodeError:
                    report_data["match_results"] = []
            else:
                report_data["match_results"] = []
                
            stored_reports.append(report_data)
            
        return stored_reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
