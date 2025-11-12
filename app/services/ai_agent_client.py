# services/ai_agent_client.py
import os
import httpx
from datetime import datetime
from typing import Dict, Any, Union
from dotenv import load_dotenv

load_dotenv()
AI_AGENT_URL = os.getenv("AI_AGENT_URL", "https://241f3bc3767f.ngrok-free.app")

async def start_session_on_ai(session_payload: Union[Dict[str, Any], dict]) -> Dict[str, Any]:
    """
    Start a new session on the AI agent.
    The AI agent uses the same session_id sent from the middleware for compatibility.
    
    Expected payload format:
    {
        "session_id": "string",
        "job_descriptions": [{
            "jd_id": "string",
            "title": "string", 
            "description": "string",
            "skills": [],
            "responsibilities": []
        }],
        "cvs": [{
            "cv_id": "string",
            "jd_id": "string",
            "filename": "string",
            "base64_content": "string"
        }],
        "status": "string"  # Session status: pending, active, processing, completed, failed
    }
    """
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.post(f"{AI_AGENT_URL}/middleware/sessions", json=session_payload)
        r.raise_for_status()
        return r.json()

# async def match_jd(session_id: str, jd_id: str) -> Dict[str, Any]:
#     async with httpx.AsyncClient(timeout=600) as client:
#         r = await client.post(f"{AI_AGENT_URL}/sessions/{session_id}/jds/{jd_id}/match")
#         r.raise_for_status()
#         return r.json()

# async def add_cvs_to_session(session_id: str, cvs_payload: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Add CVs to an existing session on the AI agent.
    
#     Expected payload format:
#     {
#         "cvs": [{ 
#             "cv_id": "string",
#             "jd_id": "string", 
#             "filename": "string",
#             "base64_content": "string"
#         }],
#         "status": "string"  # Session status: pending, active, processing, completed, failed
#     }
#     """
#     async with httpx.AsyncClient(timeout=600) as client:
#         r = await client.post(f"{AI_AGENT_URL}/sessions/{session_id}/add-cvs", json=cvs_payload)
#         r.raise_for_status()
#         return r.json()

async def add_cvs_to_session_with_jd(session_id: str, jd_id: str, cvs_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy function - Add CVs to a specific JD within a session.
    Consider using add_cvs_to_session for the new API format.
    
    Expected payload format:
    {
        "cvs": [{ 
            "cv_id": "string",
            "jd_id": "string", 
            "filename": "string",
            "base64_content": "string"
        }],
        "status": "string"  # Session status: pending, active, processing, completed, failed
    }
    """
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        r = await client.post(f"{AI_AGENT_URL}/middleware/sessions/{session_id}/jds/{jd_id}/add-cvs", json=cvs_payload)
        r.raise_for_status()
        return r.json()

async def fetch_report(session_id: str, jd_id: str) -> Dict[str, Any]:
    """
    Fetch match report from AI agent.
    Handles the new report format with match_report_id and multiple reports.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(f"{AI_AGENT_URL}/api/match/sessions/{session_id}/jds/{jd_id}/reports")
        r.raise_for_status()
        response = r.json()
        
        # Handle both old and new format for backwards compatibility
        if isinstance(response, list) and len(response) > 0:
            # New format: array of reports
            # For now, take the latest report (last in array)
            latest_report = response[-1]
            return {
                "status": "completed",
                "match_results": latest_report.get("match_results", []),
                "match_report_id": latest_report.get("match_report_id"),
                "summary": latest_report.get("summary"),
                "created_at": latest_report.get("created_at"),
                "reports": response  # Include all reports for reference
            }
        elif isinstance(response, dict):
            # Old format or single report
            if "status" in response:
                return response
            else:
                # Single report without status wrapper
                return {
                    "status": "completed", 
                    "match_results": response.get("match_results", []),
                    "match_report_id": response.get("match_report_id"),
                    "summary": response.get("summary"),
                    "created_at": response.get("created_at")
                }
        else:
            # Empty or unexpected format
            return {"status": "processing", "match_results": []}

async def complete_session(session_id: str, jd_id: str, status: str = "completed") -> Dict[str, Any]:
    """
    Notify the AI agent that a session is completed and should be closed.
    This allows the AI agent to clean up resources and properly close the session.
    
    Args:
        session_id: The session ID to complete
        jd_id: The job description ID associated with the session
        status: Session status (e.g., "completed", "failed", "expired")
    """
    try:
        payload = {
            "session_id": session_id,
            "jd_id": jd_id,
            "status": status,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.post(
                f"{AI_AGENT_URL}/middleware/sessions/{session_id}/jds/{jd_id}/complete", 
                json=payload
            )
            r.raise_for_status()
            return r.json()
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Session not found on AI agent - it may have already been cleaned up
            return {"status": "not_found", "message": "Session not found on AI agent"}
        else:
            raise
    except Exception as e:
        # Log error but don't fail the middleware operation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to notify AI agent about session completion: {e}")
        return {"status": "error", "message": str(e)}
