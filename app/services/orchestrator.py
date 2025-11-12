import uuid
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select, update
from app.models.models import MiddlewareSession, AIJobDescription, AICV, AIAgentSessionPayload, MiddlewareReport
from app.services import job_portal_client, ai_agent_client
from app.utils import utils
from app.helpers.retry_config import (
    classify_error, 
    should_retry, 
    calculate_next_retry_time,
    get_retry_limit
)
import logging

logger = logging.getLogger(__name__)

# We will use SQLAlchemy ORM for sessions table (MiddlewareSession). For simplicity we use raw engine operations.

async def handle_session_failure(
    db_session, 
    session: MiddlewareSession, 
    error: Exception
) -> Dict[str, Any]:
    """
    Handle session failure with retry logic based on failure type.
    
    Args:
        db_session: Database session
        session: The middleware session that failed
        error: The exception that caused the failure
        
    Returns:
        Dict with status and retry information
    """
    # Classify the error
    failure_reason = classify_error(str(error))
    current_retry_count = session.retry_count or 0
    
    logger.error(
        f"Session {session.session_id} failed with {failure_reason}: {str(error)} "
        f"(retry {current_retry_count + 1}/{get_retry_limit(failure_reason)})"
    )
    
    # Check if we should retry or supersede
    if should_retry(current_retry_count, failure_reason):
        # Calculate next retry time
        retry_delay = calculate_next_retry_time(current_retry_count, failure_reason)
        next_retry_time = datetime.utcnow() + retry_delay
        
        # Update session for retry
        update_stmt = update(MiddlewareSession).where(
            MiddlewareSession.session_id == session.session_id
        ).values(
            status="failed",
            retry_count=current_retry_count + 1,
            last_failure_reason=failure_reason,
            last_retry_at=datetime.utcnow(),
            next_retry_at=next_retry_time,
            updated_at=datetime.utcnow()
        )
        await db_session.execute(update_stmt)
        await db_session.commit()
        
        logger.info(
            f"Session {session.session_id} will retry at {next_retry_time} "
            f"(retry {current_retry_count + 1}/{get_retry_limit(failure_reason)})"
        )
        
        return {
            "status": "failed",
            "will_retry": True,
            "retry_count": current_retry_count + 1,
            "next_retry_at": next_retry_time.isoformat(),
            "failure_reason": failure_reason
        }
    else:
        # Max retries reached - supersede the session
        update_stmt = update(MiddlewareSession).where(
            MiddlewareSession.session_id == session.session_id
        ).values(
            status="superseded",
            retry_count=current_retry_count + 1,
            last_failure_reason=failure_reason,
            superseded_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await db_session.execute(update_stmt)
        await db_session.commit()
        
        logger.warning(
            f"Session {session.session_id} superseded after {current_retry_count + 1} failed attempts "
            f"(failure type: {failure_reason})"
        )
        
        # Notify AI agent about superseded session
        if session.ai_session_id:
            try:
                await ai_agent_client.complete_session(
                    session.ai_session_id, 
                    session.jd_id, 
                    "superseded"
                )
            except Exception as e:
                logger.warning(f"Failed to notify AI agent about superseded session: {e}")
        
        return {
            "status": "superseded",
            "will_retry": False,
            "retry_count": current_retry_count + 1,
            "failure_reason": failure_reason,
            "superseded_at": datetime.utcnow().isoformat()
        }


async def check_cv_already_processed(db_session, jd_id: str, cv_id: str) -> bool:
    """
    Check if a CV has already been processed for a specific JD by looking at completed sessions
    and their associated reports.
    """
    try:
        # Look for completed sessions for this JD that have processed this CV
        completed_sessions_query = select(MiddlewareSession).where(
            MiddlewareSession.jd_id == jd_id,
            MiddlewareSession.status == "completed"
        )
        
        result = await db_session.execute(completed_sessions_query)
        completed_sessions = result.scalars().all()
        
        for session in completed_sessions:
            if cv_id in (session.cv_ids or []):
                # Check if there are reports for this session and JD
                report_query = select(MiddlewareReport).where(
                    MiddlewareReport.session_id == session.session_id,
                    MiddlewareReport.jd_id == jd_id
                )
                report_result = await db_session.execute(report_query)
                if report_result.scalars().first():
                    logger.info(f"CV {cv_id} already processed for JD {jd_id} in session {session.session_id}")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking if CV {cv_id} already processed for JD {jd_id}: {e}")
        return False

async def create_middleware_session(db_session, jd_id: str, cv_ids: List[str]) -> Dict[str, Any]:
    # Check job status first before creating session
    job_status = await job_portal_client.get_job_status(int(jd_id))
    
    if job_status == "expired":
        raise ValueError(f"Job with ID {jd_id} is expired - skipped")
    elif job_status != "published":
        raise ValueError(f"Job with ID {jd_id} has status '{job_status}' - only 'published' jobs are processed")
    
    # Check if an active session already exists for this JD
    existing_session_query = select(MiddlewareSession).where(
        MiddlewareSession.jd_id == jd_id,
        MiddlewareSession.status.in_(["pending", "active", "processing"])
    )
    result = await db_session.execute(existing_session_query)
    existing_session = result.scalar_one_or_none()
    
    if existing_session:
        logger.info(f"Active session {existing_session.session_id} already exists for JD {jd_id} - returning existing session")
        return {"session_id": existing_session.session_id}
    
    # Only create new session if no active session exists
    session_id = str(uuid.uuid4())
    stmt = MiddlewareSession.__table__.insert().values(
        session_id=session_id,
        jd_id=jd_id,
        cv_ids=cv_ids,
        status="pending",
        last_checked=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await db_session.execute(stmt)
    await db_session.commit()
    logger.info(f"Created new session {session_id} for JD {jd_id}")
    return {"session_id": session_id}

async def force_create_new_session(db_session, jd_id: str, cv_ids: List[str]) -> Dict[str, Any]:
    """
    Force create a new session by marking existing ones as superseded.
    This should only be used in special cases like application restart or recovery.
    """
    # Check job status first
    job_status = await job_portal_client.get_job_status(int(jd_id))
    
    if job_status == "expired":
        raise ValueError(f"Job with ID {jd_id} is expired - skipped")
    elif job_status != "published":
        raise ValueError(f"Job with ID {jd_id} has status '{job_status}' - only 'published' jobs are processed")
    
    # Mark any existing active sessions for this job as superseded
    update_stmt = update(MiddlewareSession).where(
        MiddlewareSession.jd_id == jd_id,
        MiddlewareSession.status.in_(["pending", "active", "processing"])
    ).values(
        status="superseded",
        updated_at=datetime.utcnow()
    )
    await db_session.execute(update_stmt)
    
    # Create new session
    session_id = str(uuid.uuid4())
    stmt = MiddlewareSession.__table__.insert().values(
        session_id=session_id,
        jd_id=jd_id,
        cv_ids=cv_ids,
        status="pending",
        last_checked=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await db_session.execute(stmt)
    await db_session.commit()
    logger.info(f"Force created new session {session_id} for JD {jd_id}, marked existing sessions as superseded")
    return {"session_id": session_id}

async def process_session(session_id: str, db_session) -> Dict[str, Any]:
    """
    Orchestrate: fetch JD, fetch CVs (download resumes → base64), forward to AI agent,
    wait/poll for report, store ai_session_id in middleware_sessions.
    Handles failures with retry logic.
    """
    # load session
    q = select(MiddlewareSession).where(MiddlewareSession.session_id == session_id)
    res = await db_session.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        raise ValueError("session not found")

    try:
        return await _process_session_internal(sess, db_session)
    except Exception as e:
        # Handle failure with retry logic
        logger.error(f"Session {session_id} processing failed: {str(e)}")
        await handle_session_failure(db_session, sess, e)
        # Re-raise the exception after handling
        raise


async def _process_session_internal(sess: MiddlewareSession, db_session) -> Dict[str, Any]:
    """
    Internal function that does the actual session processing.
    Separated for better error handling.
    """
    session_id = sess.session_id
    jd_id = sess.jd_id
    
    # Check job status before processing
    job_status = await job_portal_client.get_job_status(int(jd_id))
    
    if job_status == "expired":
        # Mark session as completed when job is expired
        upd = update(MiddlewareSession).where(MiddlewareSession.session_id == session_id).values(
            status="completed",
            updated_at=datetime.utcnow()
        )
        await db_session.execute(upd)
        await db_session.commit()
        raise ValueError(f"Job with ID {jd_id} is expired - session marked as completed")
    elif job_status != "published":
        raise ValueError(f"Job with ID {jd_id} has status '{job_status}' - only 'published' jobs are processed")
    
    # Fetch JD details from job portal API
    jd = await job_portal_client.fetch_jd(int(jd_id))

    # fetch cv applications for JD
    applications = await job_portal_client.fetch_cvs_for_jd(int(jd_id))

    # Prepare CVs to send to AI agent using proper models:
    cvs_payload = []
    cv_ids_sent = []
    for app in applications:
        resume_url = app.get("resume")
        if not resume_url:
            continue
        # If this cv is already in sess.cv_ids (processed) skip
        cv_identifier = str(app.get("id"))
        if cv_identifier in (sess.cv_ids or []):
            continue
        
        # Check if this CV has already been processed for this JD in a completed session
        already_processed = await check_cv_already_processed(db_session, jd_id, cv_identifier)
        if already_processed:
            logger.info(f"CV {cv_identifier} already processed for JD {jd_id} - skipping to avoid duplicate processing")
            continue
        
        # download resume contents and encode
        base64_content = await utils.download_and_base64(resume_url)
        
        # Create AICV model instance
        cv_payload = AICV(
            cv_id=cv_identifier,
            jd_id=jd_id,
            filename=app.get("firstname") + "_" + app.get("lastname") + ".pdf" if app.get("firstname") else f"cv_{cv_identifier}.pdf",
            base64_content=base64_content
        )
        cvs_payload.append(cv_payload)
        cv_ids_sent.append(cv_identifier)

    # If no new cvs, return
    if not cvs_payload:
        return {"status": "no_new_cvs"}

    # Create AI job description model
    job_description = AIJobDescription(
        jd_id=jd_id,
        title=jd["job"]["title"],
        description=jd["job"]["description"],
        skills=jd.get("skills", []),
        responsibilities=jd.get("responsibilities", [])
    )

    # Build AI session payload using the proper model
    ai_payload = AIAgentSessionPayload(
        session_id=session_id,
        job_descriptions=[job_description],
        cvs=cvs_payload,
        status=sess.status  # Include current session status
    )

    # start session on AI agent (ingest) - AI agent uses the same session_id
    ai_response = await ai_agent_client.start_session_on_ai(ai_payload.model_dump())
    # AI agent should use the same session_id we sent for compatibility
    ai_session_id = session_id

    # update middleware session with ai_session_id and cv ids, change status to "active" after AI processing starts
    upd = update(MiddlewareSession).where(MiddlewareSession.session_id == session_id).values(
        ai_session_id=ai_session_id,
        cv_ids=(sess.cv_ids or []) + cv_ids_sent,
        status="active",  # Changed from "processing" to "active" after AI agent receives the data
        updated_at=datetime.utcnow()
    )
    await db_session.execute(upd)
    await db_session.commit()

    # Optionally wait/poll for AI report (or AI may be async; here we just return ai_response)
    return {"ai_response": ai_response}

async def add_cvs_to_existing_session(session_id: str, new_cv_ids: List[str], db_session) -> Dict[str, Any]:
    """
    Add additional CVs to an existing session.
    This function can be used when new CVs are applied to a job after the initial session creation.
    """
    # load session
    q = select(MiddlewareSession).where(MiddlewareSession.session_id == session_id)
    res = await db_session.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        raise ValueError("session not found")

    jd_id = sess.jd_id
    
    # Check job status first
    job_status = await job_portal_client.get_job_status(int(jd_id))
    
    if job_status == "expired":
        # Mark session as completed when job is expired
        upd = update(MiddlewareSession).where(MiddlewareSession.session_id == session_id).values(
            status="completed",
            updated_at=datetime.utcnow()
        )
        await db_session.execute(upd)
        await db_session.commit()
        logger.info(f"Job expired so match is completed for session {session_id}")
        return {"status": "job_expired", "message": "Job expired so match is completed"}
    elif job_status != "published":
        raise ValueError(f"Job with ID {jd_id} has status '{job_status}' - only 'published' jobs are processed")
    
    # If job is published, ensure session is in "active" status (maintain active status)
    if sess.status != "active":
        upd = update(MiddlewareSession).where(MiddlewareSession.session_id == session_id).values(
            status="active",
            updated_at=datetime.utcnow()
        )
        await db_session.execute(upd)
        await db_session.commit()
        logger.info(f"Session {session_id} status updated to 'active' for published job {jd_id}")
    
    # fetch cv applications for JD
    applications = await job_portal_client.fetch_cvs_for_jd(int(jd_id))

    # Prepare new CVs to send to AI agent:
    cvs_payload = []
    cv_ids_sent = []
    for app in applications:
        cv_identifier = str(app.get("id"))
        
        # Only process CVs that are in new_cv_ids and not already processed
        if cv_identifier not in new_cv_ids:
            continue
        if cv_identifier in (sess.cv_ids or []):
            continue
            
        # Check if this CV has already been processed for this JD in a completed session
        already_processed = await check_cv_already_processed(db_session, jd_id, cv_identifier)
        if already_processed:
            logger.info(f"CV {cv_identifier} already processed for JD {jd_id} - skipping to avoid duplicate processing")
            continue
            
        resume_url = app.get("resume")
        if not resume_url:
            continue
            
        # download resume contents and encode
        base64_content = await utils.download_and_base64(resume_url)
        
        # Create AICV model instance
        cv_payload = AICV(
            cv_id=cv_identifier,
            jd_id=jd_id,
            filename=app.get("firstname") + "_" + app.get("lastname") + ".pdf" if app.get("firstname") else f"cv_{cv_identifier}.pdf",
            base64_content=base64_content
        )
        cvs_payload.append(cv_payload)
        cv_ids_sent.append(cv_identifier)

    # If no new cvs, return
    if not cvs_payload:
        return {"status": "no_new_cvs"}

    # Add CVs to existing session
    cvs_dict_payload = {
        "cvs": [cv.model_dump() for cv in cvs_payload],
        "status": sess.status  # Include current session status
    }
    ai_response = await ai_agent_client.add_cvs_to_session_with_jd(session_id, jd_id, cvs_dict_payload)

    # update middleware session with new cv ids
    upd = update(MiddlewareSession).where(MiddlewareSession.session_id == session_id).values(
        cv_ids=(sess.cv_ids or []) + cv_ids_sent,
        updated_at=datetime.utcnow()
    )
    await db_session.execute(upd)
    await db_session.commit()

    return {"ai_response": ai_response, "cvs_added": len(cv_ids_sent)}
