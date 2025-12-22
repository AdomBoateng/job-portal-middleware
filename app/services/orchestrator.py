"""
Orchestrator (DEPRECATED/SLIMMED)

This module previously contained orchestration helpers for batch job processing
and incremental addition of CVs to sessions. The project has moved to a per-
application, one-session-per-application workflow. Most of the old functions
are intentionally deprecated to avoid accidental batch processing. The
important helper that remains is `handle_session_failure` which is used by
retry and monitoring logic to record failures and decide retry/supersede.

New workflow responsibilities:
- Application intake & per-application processing: `app.services.application_processor`
- Result delivery: `app.services.job_portal_client` / `app.services.result_scheduler`

If you are looking to process an application, call
`app.services.application_processor.process_job_application(db_session, application_data)`
instead of using the old batch/session helpers.
"""

import logging
from typing import Dict, Any
from app.services import ai_agent_client

logger = logging.getLogger(__name__)


async def handle_session_failure(db_session, session, error: Exception) -> Dict[str, Any]:
    """
    Handle a session failure in a best-effort way.

    Notes:
    - This function intentionally keeps behavior minimal: it logs the failure
      and, if possible, notifies the AI agent about a superseded session.
    - The previous retry/scheduling logic was moved or simplified elsewhere.
    """
    failure_reason = str(error)
    logger.error("Session %s failed: %s", getattr(session, "session_id", "<unknown>"), failure_reason)

    # Mark superseded if model contains that attribute (best-effort)
    try:
        # Try to set a status attribute if present and commit
        if hasattr(session, "status"):
            session.status = "failed"
            if hasattr(db_session, "commit"):
                await db_session.commit()
    except Exception:
        logger.debug("Failed to persist failure state for session %s", getattr(session, "session_id", "<unknown>"))

    # Notify AI agent if we have an ai session id
    ai_session_id = getattr(session, "ai_session_id", None)
    jd_id = getattr(session, "jd_id", None)
    if ai_session_id and jd_id:
        try:
            await ai_agent_client.complete_session(ai_session_id, jd_id, "failed")
        except Exception as e:
            logger.warning("Failed to notify AI agent about failed session %s: %s", ai_session_id, str(e))

    return {"status": "failed", "reason": failure_reason}


async def create_middleware_session(*args, **kwargs):
    raise NotImplementedError("create_middleware_session is deprecated. Use the per-application endpoint or application_processor.process_job_application")


async def process_session(*args, **kwargs):
    raise NotImplementedError("process_session is deprecated. Use the per-application endpoint or application_processor.process_job_application")

