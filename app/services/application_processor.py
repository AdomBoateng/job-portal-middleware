# services/application_processor.py
import logging
import uuid
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import select
from app.models.new_models import (
    NewSession, 
    NewReport, 
    AIJobDescription, 
    AICV, 
    AIAgentSessionPayload
)
from app.services import ai_agent_client
from app.utils import utils

logger = logging.getLogger(__name__)


async def process_job_application(db_session, application_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    
    
    NEW WORKFLOW - One CV per JD:
    1. Create new session and mark as "processing"
    2. Extract application details from payload
    3. Download resume from S3 URL and convert to base64
    4. Send to AI agent for matching with session_id and needed fields
    5. Receive results from AI agent
    6. Send results to job portal (REST)
    7. Mark session as "completed"
    
    Each new application for the same JD creates a new session.
    
    Args:
        db_session: Database session
        application_data: Application payload from job portal
        
    Returns:
        Dictionary with processing status and session_id
    """
    session_id = None
    try:
        application_id = application_data.get("application_id")
        application = application_data.get("application", {})
        
        # Extract required fields
        firstname = application.get("firstname", "")
        lastname = application.get("lastname", "")
        resume_url = application.get("resume")
        # Note: user_id and email available but not used in current workflow
        
        # Extract job details
        job = application.get("job", {})
        job_id = str(job.get("id"))
        job_title = job.get("title", "")
        job_description = job.get("description", "")
        
        # Extract skills and responsibilities
        job_skills = application.get("job_skills", [])
        job_responsibilities = application.get("job_responsibilities", [])
        
        logger.info(
            f"Processing application {application_id} for job {job_id} "
            f"from {firstname} {lastname}"
        )
        
        # Validate required fields
        if not resume_url:
            raise ValueError(f"Application {application_id} has no resume URL")
        
        if not job_id or not job_title:
            raise ValueError(f"Application {application_id} has invalid job information")
        
        # Prevent duplicate processing: if a session already exists for this application (cv_id), skip
        cv_id = str(application_id)  # Use application_id as cv_id
        # existing_stmt = select(NewSession).where(NewSession.cv_id == cv_id)
        # existing_res = await db_session.execute(existing_stmt)
        # existing_session = existing_res.scalar_one_or_none()
        # if existing_session:
        #     logger.info(f"Application {application_id} already has session {existing_session.session_id} with status {existing_session.status}; skipping processing")
        #     return {
        #         "status": "skipped",
        #         "reason": "already_processed_or_processing",
        #         "session_id": existing_session.session_id,
        #         "existing_status": existing_session.status,
        #         "application_id": application_id,
        #         "job_id": job_id
        #     }

        # Create new session immediately and mark as processing
        session_id = str(uuid.uuid4())
        new_session = NewSession(
            session_id=session_id,
            jd_id=job_id,
            cv_id=cv_id,  # Single CV per session in new workflow
            status="processing"  # Mark as processing immediately
        )
        db_session.add(new_session)
        await db_session.commit()
        logger.info(f"Created new session {session_id} for application {application_id} (job {job_id})")
        
        # Download resume and convert to base64
        logger.info(f"Downloading resume from {resume_url}")
        try:
            resume_base64 = await utils.download_and_base64(resume_url, timeout=60)
            logger.info(f"Successfully downloaded and encoded resume for application {application_id}")
        except Exception as e:
            logger.error(f"Failed to download resume from {resume_url}: {e}")
            # Update session to failed
            new_session.status = "failed"
            await db_session.commit()
            raise ValueError(f"Could not download resume: {e}")
        
        # Prepare AI agent payload
        cv_filename = f"{firstname}_{lastname}_resume.pdf"
        
        ai_jd = AIJobDescription(
            jd_id=job_id,
            title=job_title,
            description=job_description,
            skills=job_skills,
            responsibilities=job_responsibilities
        )
        
        ai_cv = AICV(
            cv_id=cv_id,
            jd_id=job_id,
            filename=cv_filename,
            base64_content=resume_base64
        )
        
        ai_payload = AIAgentSessionPayload(
            session_id=session_id,
            job_descriptions=[ai_jd],
            cvs=[ai_cv],
            status="active"
        )
        
        # Send to AI agent for matching
        logger.info(f"Sending session {session_id} to AI agent for matching")
        try:
            await ai_agent_client.start_session_on_ai(ai_payload.dict())
            logger.info(f"Session {session_id} sent to AI agent successfully")
            
            # Fetch results from AI agent
            logger.info(f"Fetching match results for session {session_id}")
            try:
                match_report = await ai_agent_client.fetch_report(session_id, job_id)
                
                # Store report in database
                await store_match_report(db_session, match_report, session_id, job_id)
                
                # Process and send results to job portal
                send_results_to_job_portal(
                    db_session, 
                    session_id, 
                    job_id, 
                    match_report
                )
                
                # Mark session as completed
                new_session.status = "completed"
                new_session.completed_at = datetime.utcnow()
                await db_session.commit()
                logger.info(f"Session {session_id} completed successfully")

                # Notify AI agent that the session is completed
                try:
                    await ai_agent_client.complete_session(session_id, job_id, status="completed")
                except Exception as e:
                    logger.warning(f"Failed to notify AI agent about session completion for {session_id}: {e}")
                
                return {
                    "status": "success",
                    "session_id": session_id,
                    "application_id": application_id,
                    "job_id": job_id,
                    "results_sent": True
                }
                
            except Exception as e:
                logger.error(f"Failed to fetch or send results for session {session_id}: {e}")
                # Keep status as processing - will be picked up by scheduler backup
                await db_session.commit()
                
                return {
                    "status": "success",
                    "session_id": session_id,
                    "application_id": application_id,
                    "job_id": job_id,
                    "results_sent": False,
                    "note": "AI matching started, results will be sent when ready"
                }
            
        except Exception as e:
            logger.error(f"Failed to send session {session_id} to AI agent: {e}")

            # Update session status to failed
            try:
                new_session.status = "failed"
                new_session.completed_at = datetime.utcnow()
                await db_session.commit()
            except Exception:
                logger.exception("Error updating session status to failed")

            # Notify AI agent that the session failed (best-effort)
            try:
                await ai_agent_client.complete_session(session_id, job_id, status="failed")
            except Exception:
                logger.exception("Failed to notify AI agent of failed session")

            raise
            
    except Exception as e:
        logger.error(f"Error processing application: {e}")
        # Try best-effort to mark session failed if it was created
        try:
            if session_id:
                # update DB record if exists
                existing_stmt = select(NewSession).where(NewSession.session_id == session_id)
                existing_res = await db_session.execute(existing_stmt)
                s = existing_res.scalar_one_or_none()
                if s:
                    s.status = "failed"
                    s.completed_at = datetime.utcnow()
                    await db_session.commit()
                    try:
                        await ai_agent_client.complete_session(session_id, job_id, status="failed")
                    except Exception:
                        logger.exception("Failed to notify AI agent of failed session during exception handling")
        except Exception:
            logger.exception("Error while attempting to mark session as failed during exception handling")

        return {
            "status": "error",
            "error": str(e),
            "application_id": application_data.get("application_id"),
            "session_id": session_id
        }


async def store_match_report(db_session, report_data: Dict[str, Any], session_id: str, jd_id: str):
    """Store match report in database."""
    try:
        # Extract match results from report data
        match_results = report_data.get("match_results", [])
        
        if not match_results:
            logger.warning(f"No match results in report data for session {session_id}")
            return
        
        # Check if report already exists for this session
        existing_report_stmt = select(NewReport).where(
            NewReport.session_id == session_id
        )
        existing_result = await db_session.execute(existing_report_stmt)
        existing_report = existing_result.scalar_one_or_none()
        
        if existing_report:
            logger.info(f"Report already exists for session {session_id}, skipping")
            return
        
        # Process each result (in new workflow, should be only 1 CV)
        for result in match_results:
            cv_id = result.get("cv_id", "unknown")
            
            # Create new report with structured fields
            new_report = NewReport(
                session_id=session_id,
                jd_id=jd_id,
                cv_id=cv_id,
                total_score=result.get("total_score", 0.0),
                category=result.get("category", ""),
                rationale=result.get("rationale", ""),
                sim_embed=str(result.get("sim_embed")) if result.get("sim_embed") is not None else None,
                skill_coverage=str(result.get("skill_coverage")) if result.get("skill_coverage") is not None else None,
                must_have_penalty=result.get("must_have_penalty"),
                llm_consistency=result.get("llm_consistency")
            )
            
            db_session.add(new_report)
        
        await db_session.commit()
        logger.info(f"Stored match report for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error storing match report: {e}")


def send_results_to_job_portal(
    db_session,
    session_id: str,
    job_id: str,
    match_report: Dict[str, Any]
):
    """Send match results to job portal via REST API."""
    try:
        # Import job portal client here to avoid circular imports
        from app.services import job_portal_client

        # Process match results
        match_results = match_report.get("match_results", [])
        if isinstance(match_results, dict):
            match_results = match_results.get("results", [])

        processed_results = process_match_results_for_job_portal(match_results)

        if not processed_results:
            logger.warning(f"No processed results for session {session_id}")
            return

        # Always use REST API fallback for delivering results in the new workflow
        logger.info(f"Sending results for session {session_id} via REST API")
        job_portal_client.update_application_match(processed_results)

        logger.info(f"Successfully sent results for session {session_id} to job portal")

    except Exception as e:
        logger.error(f"Error sending results to job portal: {e}")
        raise


def process_match_results_for_job_portal(match_results: List[Dict]) -> List[Dict]:
    """Process match results from AI agent format to job portal format."""
    processed_results = []
    
    for result in match_results:
        # # Map category from AI agent format to job portal format
        # category = result.get("category", "").upper()
        # if category == "REJECT":
        #     mapped_category = "weak"
        # elif category == "ACCEPT":
        #     mapped_category = "strong"
        # else:
        #     mapped_category = result.get("category", "moderate").lower()
        
        processed_result = {
            "application_id": result.get("cv_id"),
            "total_score": result.get("total_score", 0.0),
            "category": result.get("category", ""),
            "rationale": result.get("rationale", ""),
        }
        
        # Add optional fields if present
        if result.get("sim_embed") is not None:
            processed_result["sim_embed"] = result.get("sim_embed")
        if result.get("skill_coverage") is not None:
            processed_result["skill_coverage"] = result.get("skill_coverage")
        if result.get("must_have_penalty") is not None:
            processed_result["must_have_penalty"] = result.get("must_have_penalty")
        if result.get("llm_consistency") is not None:
            processed_result["llm_consistency"] = result.get("llm_consistency")
        
        processed_results.append(processed_result)
    
    return processed_results


async def process_multiple_applications(
    db_session, 
    applications: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Process multiple job applications in batch.
    
    Args:
        db_session: Database session
        applications: List of application payloads
        
    Returns:
        List of processing results
    """
    # Batch processing of multiple applications is intentionally removed in the
    # new workflow: each application must be processed as a separate session.
    # Keep this function minimal in case of accidental calls.
    raise NotImplementedError("Batch processing of multiple applications is not supported. Submit applications individually.")
