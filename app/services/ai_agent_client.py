# services/ai_agent_client.py
import os
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Union
from dotenv import load_dotenv
import logging

load_dotenv()
AI_AGENT_URL = os.getenv("AI_AGENT_URL")
logger = logging.getLogger(__name__)


async def _post_with_retries(
    url: str,
    json: Dict[str, Any],
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.0,
    retry_on_server_error: bool = True,
) -> httpx.Response:
    """POST wrapper with simple retries for transient network and server errors.

    Retries on transport-level errors (connect/read timeouts, connection errors)
    and optionally on server errors (HTTP 5xx). 4xx errors are raised immediately.
    """
    for attempt in range(1, retries + 1):
        try:
            # Log a short summary of the payload for debugging (avoid logging huge base64 blobs)
            try:
                payload_summary = {k: (v if not isinstance(v, (str, bytes)) or len(str(v)) < 200 else f"<{type(v).__name__} {len(str(v))} bytes>") for k, v in (json.items() if isinstance(json, dict) else [])}
            except Exception:
                payload_summary = "<unserializable-payload>"

            logger.debug(f"POST attempt {attempt}/{retries} to {url} payload-summary: {payload_summary}")

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(url, json=json)

                # If server returned 5xx and we should retry, treat it as transient
                status = getattr(resp, "status_code", None)
                if retry_on_server_error and isinstance(status, int) and 500 <= status < 600:
                    text = getattr(resp, "text", "")
                    if not isinstance(text, str):
                        text = repr(text)
                    logger.warning(
                        f"POST attempt {attempt}/{retries} to {url} returned {status}; response: {text[:200]}"
                    )
                    if attempt < retries:
                        await asyncio.sleep(backoff * attempt)
                        continue
                    # last attempt: raise to surface the HTTP error
                    resp.raise_for_status()

                # For 4xx and successful responses, let raise_for_status handle it
                resp.raise_for_status()
                return resp

        except (httpx.TransportError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            logger.warning(f"POST attempt {attempt}/{retries} to {url} failed with transient error: {e}")
            if attempt < retries:
                await asyncio.sleep(backoff * attempt)
                continue
            else:
                raise
        except httpx.HTTPStatusError as e:
            # Log response body for non-2xx responses to aid debugging (may include 4xx or 5xx)
            try:
                resp = e.response
                status = getattr(resp, "status_code", None)
                text = None
                try:
                    # Prefer text but fall back to repr for non-str
                    text = resp.text if isinstance(resp.text, str) else repr(resp.text)
                except Exception:
                    text = repr(resp)

                logger.error(
                    f"HTTPStatusError on POST to {url}: status={status}, response_snippet={text[:1000] if text else '<no-body>'}"
                )
            except Exception:
                logger.exception("Failed to extract response body from HTTPStatusError")
            # Re-raise so callers see the HTTP error
            raise


async def _get_with_retries(
    url: str,
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.0,
    retry_on_server_error: bool = True,
) -> httpx.Response:
    """GET wrapper with retries for transient and server errors.

    Mirrors behavior of _post_with_retries but for GET requests.
    """
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url)

                status = getattr(resp, "status_code", None)
                if retry_on_server_error and isinstance(status, int) and 500 <= status < 600:
                    text = getattr(resp, "text", "")
                    if not isinstance(text, str):
                        text = repr(text)
                    logger.warning(
                        f"GET attempt {attempt}/{retries} to {url} returned {status}; response: {text[:200]}"
                    )
                    if attempt < retries:
                        await asyncio.sleep(backoff * attempt)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp
        except (httpx.TransportError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            logger.warning(f"GET attempt {attempt}/{retries} to {url} failed with transient error: {e}")
            if attempt < retries:
                await asyncio.sleep(backoff * attempt)
                continue
            else:
                raise
        except httpx.HTTPStatusError as e:
            try:
                resp = e.response
                status = getattr(resp, "status_code", None)
                text = None
                try:
                    text = resp.text if isinstance(resp.text, str) else repr(resp.text)
                except Exception:
                    text = repr(resp)

                logger.error(
                    f"HTTPStatusError on GET to {url}: status={status}, response_snippet={text[:1000] if text else '<no-body>'}"
                )
            except Exception:
                logger.exception("Failed to extract response body from HTTPStatusError (GET)")
            raise


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
    url = f"{AI_AGENT_URL}/middleware/sessions"
    resp = await _post_with_retries(url, json=session_payload, timeout=120, retries=3, backoff=1.0)
    return resp.json()

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

# async def add_cvs_to_session_with_jd(session_id: str, jd_id: str, cvs_payload: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Legacy function - Add CVs to a specific JD within a session.
#     Consider using add_cvs_to_session for the new API format.
    
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
#     async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
#         r = await client.post(f"{AI_AGENT_URL}/middleware/sessions/{session_id}/jds/{jd_id}/add-cvs", json=cvs_payload)
#         r.raise_for_status()
#         return r.json()

async def fetch_report(session_id: str, jd_id: str) -> Dict[str, Any]:
    """
    Fetch match report from AI agent.
    Handles the new report format with match_report_id and multiple reports.
    """
    url = f"{AI_AGENT_URL}/api/match/sessions/{session_id}/jds/{jd_id}/reports"
    r = await _get_with_retries(url, timeout=60, retries=3, backoff=1.0)
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


async def add_cvs_to_session_with_jd(session_id: str, jd_id: str, cvs_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add CVs to a specific JD within an existing session on the AI agent.
    This is a thin wrapper kept for compatibility with older callers/tests.
    """
    url = f"{AI_AGENT_URL}/middleware/sessions/{session_id}/jds/{jd_id}/add-cvs"
    resp = await _post_with_retries(url, json=cvs_payload, timeout=600, retries=3, backoff=1.0)
    return resp.json()

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
        url = f"{AI_AGENT_URL}/middleware/sessions/{session_id}/jds/{jd_id}/complete"
        resp = await _post_with_retries(url, json=payload, timeout=30, retries=3, backoff=0.5)
        return resp.json()
            
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
