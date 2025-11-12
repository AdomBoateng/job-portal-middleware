# services/monitor.py
import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from sqlalchemy import select, update
from app.services import job_portal_client, ai_agent_client
from app.services.db import AsyncSessionLocal
from app.services.orchestrator import create_middleware_session, process_session, add_cvs_to_existing_session
from app.models.models import MiddlewareSession, MiddlewareReport

load_dotenv()
INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", 300))
RETRY_FAILED_AFTER_MINUTES = int(os.getenv("RETRY_FAILED_AFTER_MINUTES", 60))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_match_results_for_job_portal(match_results):
    """
    Process match results from AI agent format to job portal format.
    Handles category mapping and field transformation.
    """
    processed_results = []
    
    for result in match_results:
        # Map category from new format to job portal format
        category = result.get("category", "").upper()
        if category == "REJECT":
            mapped_category = "weak"
        elif category == "ACCEPT":
            mapped_category = "strong"
        else:
            # Keep original or default to moderate
            mapped_category = result.get("category", "moderate").lower()
        
        processed_result = {
            "cv_id": result.get("cv_id"),
            "total_score": result.get("total_score", 0.0),
            "category": mapped_category,
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

async def store_match_report(db, report_data, session_id, jd_id=None):
    """
    Store match report in the database for audit and tracking purposes.
    Reports are stored based on session_id and jd_id combination.
    """
    try:
        if not report_data.get("match_report_id"):
            logger.warning("No match_report_id in report data, skipping storage")
            return
        
        # Use provided jd_id or extract from report data
        if not jd_id:
            jd_id = report_data.get("jd_id", "")
        if not jd_id:
            logger.warning("No jd_id provided or found in report data, skipping storage")
            return
        
        # Verify that the session exists in middleware_sessions table
        session_query = select(MiddlewareSession).where(
            MiddlewareSession.session_id == session_id
        )
        session_result = await db.execute(session_query)
        existing_session = session_result.scalar_one_or_none()
        
        if not existing_session:
            logger.warning("Session %s not found in middleware_sessions, skipping report storage", session_id)
            return
            
        # Check if report already exists for this session_id + match_report_id combination
        existing_report_stmt = select(MiddlewareReport).where(
            MiddlewareReport.session_id == session_id,
            MiddlewareReport.match_report_id == report_data.get("match_report_id")
        )
        existing_result = await db.execute(existing_report_stmt)
        existing_report = existing_result.scalar_one_or_none()
        
        if existing_report:
            logger.info("Report %s already stored for session %s and jd %s, skipping", 
                       report_data.get("match_report_id"), session_id, jd_id)
            return
            
        # Store new report
        import json
        match_results = report_data.get("match_results", [])
        
        match_report = MiddlewareReport(
            session_id=session_id,
            match_report_id=report_data.get("match_report_id"),
            jd_id=jd_id,
            summary=report_data.get("summary", ""),
            match_results=json.dumps(match_results) if match_results else "[]",  # Store as JSON string for JSONB
            ai_created_at=report_data.get("created_at")
        )
        
        db.add(match_report)
        await db.commit()
        logger.info("Stored match report: %s for session %s and jd %s", 
                   report_data.get("match_report_id"), session_id, jd_id)
        
    except Exception as e:
        logger.error("Failed to store match report: %s", str(e))
        await db.rollback()

async def get_stored_reports(db, session_id, jd_id=None):
    """
    Retrieve stored match reports for a session and optionally a specific jd_id.
    """
    try:
        if jd_id:
            # Get reports for specific session_id and jd_id
            stmt = select(MiddlewareReport).where(
                MiddlewareReport.session_id == session_id,
                MiddlewareReport.jd_id == jd_id
            ).order_by(MiddlewareReport.created_at.desc())
        else:
            # Get all reports for session_id
            stmt = select(MiddlewareReport).where(
                MiddlewareReport.session_id == session_id
            ).order_by(MiddlewareReport.created_at.desc())
            
        result = await db.execute(stmt)
        reports = result.scalars().all()
        
        # Convert to dict format and parse JSON
        report_list = []
        for report in reports:
            report_dict = {
                "id": report.id,
                "session_id": report.session_id,
                "match_report_id": report.match_report_id,
                "jd_id": report.jd_id,
                "summary": report.summary,
                "match_results": json.loads(report.match_results) if report.match_results else [],
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "ai_created_at": report.ai_created_at
            }
            report_list.append(report_dict)
            
        logger.info("Retrieved %d stored reports for session %s%s", 
                   len(report_list), session_id, f" and jd {jd_id}" if jd_id else "")
        return report_list
        
    except Exception as e:
        logger.error("Failed to retrieve stored reports: %s", str(e))
        return []

async def monitor_loop():
    """Main monitoring loop that handles job discovery, session management, and result processing."""
    logger.info("Starting monitor loop with interval: %d seconds", INTERVAL)
    
    while True:
        try:
            await discover_and_process_jobs()
            await check_processing_sessions()
            await retry_failed_sessions()
            await check_expired_jobs()  # New function to check for expired jobs
        except Exception as e:
            logger.error("Error in monitor loop: %s", str(e), exc_info=True)
        
        await asyncio.sleep(INTERVAL)

async def check_expired_jobs():
    """Check for jobs that have expired and complete their active sessions."""
    try:
        logger.debug("Checking for expired jobs...")
        jobs = await job_portal_client.fetch_all_jobs_with_status()
        
        if not jobs:
            return
            
        expired_jobs = [job for job in jobs if job.get("status") == "expired"]
        
        if expired_jobs:
            logger.info("Found %d expired jobs", len(expired_jobs))
            
            async with AsyncSessionLocal() as db:
                for job in expired_jobs:
                    await handle_expired_job(db, str(job.get("id")))
        
    except Exception as e:
        logger.error("Error checking for expired jobs: %s", str(e))

async def discover_and_process_jobs():
    """Discover new jobs and create/process middleware sessions."""
    try:
        logger.info("Discovering jobs from job portal...")
        jobs = await job_portal_client.fetch_all_jobs_with_status()
        
        if not jobs:
            logger.info("No jobs found or job portal unavailable")
            return
            
        logger.info("Found %d jobs to check", len(jobs))
        
        async with AsyncSessionLocal() as db:
            for job in jobs:
                try:
                    await process_job_applications(db, job)
                except Exception as e:
                    logger.error("Error processing job %s: %s", job.get("id"), str(e))
                    
    except Exception as e:
        logger.error("Error in job discovery: %s", str(e), exc_info=True)

async def process_job_applications(db, job: Dict[str, Any]):
    """Process applications for a specific job."""
    job_id = job.get("id")
    job_status = job.get("status", "unknown")
    
    # Check job status first
    if job_status == "expired":
        logger.info("Job with ID %d is expired - checking for active sessions to complete", job_id)
        await handle_expired_job(db, str(job_id))
        return
    elif job_status != "published":
        logger.debug("Job with ID %d has status '%s' - skipping (only published jobs are processed)", job_id, job_status)
        return
        
    # Fetch applications for this job
    apps = await job_portal_client.fetch_cvs_for_jd(job_id)
    
    if not apps:
        logger.debug("No applications found for job %d", job_id)
        return
        
    logger.info("Found %d applications for job %d (status: %s)", len(apps), job_id, job_status)
    
    # Check if we already have an active session for this job
    existing_session = await get_active_session_for_job(db, str(job_id))
    
    cv_ids = [str(app["id"]) for app in apps]
    
    if existing_session:
        # Check if there are new CVs to add to existing session
        existing_cv_ids = set(existing_session.cv_ids or [])
        new_cv_ids = [cv_id for cv_id in cv_ids if cv_id not in existing_cv_ids]
        
        if new_cv_ids:
            logger.info("Adding %d new CVs to existing session %s for job %d (status: %s)", 
                       len(new_cv_ids), existing_session.session_id, job_id, job_status)
            try:
                result = await add_cvs_to_existing_session(existing_session.session_id, new_cv_ids, db)
                if result.get("status") == "job_expired":
                    logger.info("Job expired so match is completed for session %s", existing_session.session_id)
                    return  # Move to next process as requested
                else:
                    logger.info("Successfully added new CVs to active session %s", existing_session.session_id)
            except ValueError as e:
                logger.error("Error adding CVs to session %s: %s", existing_session.session_id, str(e))
        else:
            logger.debug("No new CVs for job %d", job_id)
    else:
        # Create new session and process it
        logger.info("Creating new session for job %d with %d CVs", job_id, len(cv_ids))
        try:
            result = await create_middleware_session(db, str(job_id), [])  # Start with empty CV list
            session_id = result["session_id"]
            
            # Process the session immediately
            try:
                await process_session(session_id, db)
                logger.info("Successfully started processing session %s", session_id)
            except Exception as e:
                logger.error("Error processing session %s: %s", session_id, str(e))
                await update_session_status(db, session_id, "failed")
        except ValueError as e:
            if "expired" in str(e):
                logger.info("Job with ID %d is expired - skipped", job_id)

async def handle_expired_job(db, job_id: str):
    """Handle jobs that have expired by completing their active sessions."""
    try:
        # Find active sessions for this job
        active_sessions_query = select(MiddlewareSession).where(
            MiddlewareSession.jd_id == job_id,
            MiddlewareSession.status.in_(["pending", "active", "processing"])
        )
        result = await db.execute(active_sessions_query)
        active_sessions = result.scalars().all()
        
        if active_sessions:
            logger.info("Found %d active sessions for expired job %s", len(active_sessions), job_id)
            for session in active_sessions:
                logger.info("Job expired so match is completed for session %s", session.session_id)
                
                # Notify AI agent about session completion before updating local status
                if session.ai_session_id:
                    try:
                        completion_result = await ai_agent_client.complete_session(
                            session.ai_session_id, 
                            session.jd_id, 
                            "completed"
                        )
                        logger.info("Notified AI agent about session %s completion: %s", 
                                   session.session_id, completion_result.get("status", "unknown"))
                    except Exception as e:
                        logger.warning("Failed to notify AI agent about session %s completion: %s", 
                                      session.session_id, str(e))
                
                # Update local session status
                await update_session_status(db, session.session_id, "completed")
        else:
            logger.debug("No active sessions found for expired job %s", job_id)
            
    except Exception as e:
        logger.error("Error handling expired job %s: %s", job_id, str(e))

async def get_active_session_for_job(db, job_id: str):
    """Get the most recent active middleware session for a job."""
    query = select(MiddlewareSession).where(
        MiddlewareSession.jd_id == job_id,
        MiddlewareSession.status.in_(["pending", "active", "processing"])
    ).order_by(MiddlewareSession.created_at.desc())
    result = await db.execute(query)
    return result.scalars().first()  # Get the first (most recent) session or None



async def check_processing_sessions():
    """Check sessions that are in processing state and poll for completion."""
    try:
        async with AsyncSessionLocal() as db:
            # Get all active/processing sessions
            query = select(MiddlewareSession).where(
                MiddlewareSession.status.in_(["active", "processing"]),  # Check both active and processing sessions
                MiddlewareSession.ai_session_id.isnot(None)
            )
            result = await db.execute(query)
            processing_sessions = result.scalars().all()
            
            logger.info("Checking %d active/processing sessions", len(processing_sessions))
            
            for session in processing_sessions:
                try:
                    await check_session_completion(db, session)
                except Exception as e:
                    logger.error("Error checking session %s: %s", session.session_id, str(e))
                    
    except Exception as e:
        if "Name or service not known" in str(e):
            logger.warning("Database connection failed - database service may not be available")
        else:
            logger.error("Error checking processing sessions: %s", str(e))

async def check_session_completion(db, session: MiddlewareSession):
    """Check if a processing session is complete and handle results."""
    try:
        # Try to fetch report from AI agent
        report = await ai_agent_client.fetch_report(session.ai_session_id, session.jd_id)
        
        if report and report.get("status") == "completed":
            logger.info("Session %s completed, pushing results back to job portal", session.session_id)
            
            # Store individual reports if available
            if report.get("reports"):
                for individual_report in report.get("reports"):
                    await store_match_report(db, individual_report, session.session_id, session.jd_id)
            elif report.get("match_report_id"):
                # Single report format
                await store_match_report(db, report, session.session_id, session.jd_id)
            
            # Handle new report format
            match_results = report.get("match_results", [])
            if match_results:
                # Convert match results to format expected by job portal
                processed_results = process_match_results_for_job_portal(match_results)
                await job_portal_client.update_application_match(session.jd_id, processed_results)
                logger.info("Successfully pushed %d match results for job %s", len(processed_results), session.jd_id)
                
                # Log additional info from new format
                if report.get("match_report_id"):
                    logger.info("Match report ID: %s", report.get("match_report_id"))
                if report.get("summary"):
                    logger.info("Match summary: %s", report.get("summary"))
            
            # Check job status before updating session status
            job_status = await job_portal_client.get_job_status(int(session.jd_id))
            if job_status == "expired":
                logger.info("Job %s is expired, marking session %s as completed", session.jd_id, session.session_id)
                # Notify AI agent that session is being completed due to job expiration
                await ai_agent_client.complete_session(session.ai_session_id, session.jd_id, "completed")
                await update_session_status(db, session.session_id, "completed")
            else:
                logger.info("Job %s is still active (status: %s), keeping session %s as active", session.jd_id, job_status, session.session_id)
                await update_session_status(db, session.session_id, "active")
            
        elif report and report.get("status") == "failed":
            logger.error("AI processing failed for session %s", session.session_id)
            await update_session_status(db, session.session_id, "failed")
            
        else:
            # Still processing, update last_checked
            update_stmt = update(MiddlewareSession).where(
                MiddlewareSession.session_id == session.session_id
            ).values(
                last_checked=datetime.utcnow()
            )
            await db.execute(update_stmt)
            await db.commit()
            
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            # Report not ready yet
            logger.debug("Report not ready for session %s", session.session_id)
        else:
            logger.error("Error fetching report for session %s: %s", session.session_id, str(e))

async def retry_failed_sessions():
    """
    Retry failed sessions that are ready for another attempt.
    Checks next_retry_at timestamp and excludes superseded sessions.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get failed sessions that are ready for retry (next_retry_at has passed)
            query = select(MiddlewareSession).where(
                MiddlewareSession.status == "failed",
                MiddlewareSession.next_retry_at.isnot(None),
                MiddlewareSession.next_retry_at <= datetime.utcnow()
            )
            result = await db.execute(query)
            failed_sessions = result.scalars().all()
            
            if failed_sessions:
                logger.info("Found %d failed sessions ready for retry", len(failed_sessions))
                
                for session in failed_sessions:
                    try:
                        logger.info(
                            "Retrying session %s (retry %d, last failure: %s)", 
                            session.session_id, 
                            session.retry_count or 0,
                            session.last_failure_reason or "unknown"
                        )
                        # Attempt to process the session again
                        # The process_session will handle failure and update retry logic if needed
                        await process_session(session.session_id, db)
                        
                    except Exception as e:
                        logger.error("Error retrying session %s: %s", session.session_id, str(e))
                        # Handle the failure with retry logic
                        from app.services.orchestrator import handle_session_failure
                        await handle_session_failure(db, session, e)
                        
    except Exception as e:
        if "Name or service not known" in str(e):
            logger.warning("Database connection failed during retry - database service may not be available")
        else:
            logger.error("Error in retry failed sessions: %s", str(e))

async def update_session_status(db, session_id: str, status: str):
    """Update session status."""
    update_stmt = update(MiddlewareSession).where(
        MiddlewareSession.session_id == session_id
    ).values(
        status=status,
        updated_at=datetime.utcnow()
    )
    await db.execute(update_stmt)
    await db.commit()
    logger.info("Updated session %s status to %s", session_id, status)
