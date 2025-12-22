# services/result_scheduler.py
import logging
from typing import Dict, List
from datetime import datetime
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.db import AsyncSessionLocal
# from app.services.websocket_manager import ws_manager
# from app.services import job_portal_client
from app.models.new_models import NewSession, NewReport
from app.services import job_portal_client

# This module serves as a backup mechanism for result delivery.
# The WebSocket workflow now processes one CV per JD, creating a new session for each application.
# Scheduler is used only as a fallback for missed or delayed results.

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler = None


def process_match_results_for_job_portal(match_results: List[Dict]) -> List[Dict]:
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


async def send_results_to_job_portal():
    """
    Scheduled job to send completed match results to job portal.
    
    NOTE: With the new one-CV-per-JD workflow, results are typically sent
    immediately after AI processing completes. This scheduler serves as a
    backup mechanism for cases where immediate sending failed or was interrupted.
    
    This runs periodically to:
    1. Find completed sessions with reports
    2. Send results to job portal via WebSocket (or REST API fallback)
    3. Mark sessions as sent
    """
    logger.info("Running scheduled job to send results to job portal (backup mechanism)")
    
    try:
        async with AsyncSessionLocal() as db:
            # Find completed sessions that haven't been sent yet
            query = select(NewSession).where(
                NewSession.status == "completed"
            )
            result = await db.execute(query)
            completed_sessions = result.scalars().all()
            
            if not completed_sessions:
                logger.debug("No completed sessions to process")
                return
            
            logger.info(f"Found {len(completed_sessions)} completed session(s) to process")
            
            for session in completed_sessions:
                try:
                    # Get reports for this session
                    report_query = select(NewReport).where(
                        NewReport.session_id == session.session_id,
                        NewReport.jd_id == session.jd_id
                    )
                    report_result = await db.execute(report_query)
                    reports = report_result.scalars().all()
                    
                    if not reports:
                        logger.warning(
                            f"Session {session.session_id} is completed but has no reports"
                        )
                        continue
                    
                    # Use the latest report
                    report = reports[-1] if reports else None
                    if not report:
                        logger.warning(
                            f"Session {session.session_id} has no valid report"
                        )
                        continue
                    
                    # Prepare match results
                    match_results = []
                    match_results.append({
                        "cv_id": report.cv_id,
                        "total_score": report.total_score,
                        "category": report.category,
                        "rationale": report.rationale,
                        "sim_embed": report.sim_embed,
                        "skill_coverage": report.skill_coverage,
                        "must_have_penalty": report.must_have_penalty,
                        "llm_consistency": report.llm_consistency
                    })
                    
                    processed_results = process_match_results_for_job_portal(match_results)

                    if not processed_results:
                        logger.warning(f"No processed results for session {session.session_id}")
                        continue

                    # Deliver results via REST API to the job portal (new workflow)
                    try:
                        resp = await job_portal_client.update_application_match(session.jd_id, processed_results)
                        # If job_portal_client returns an error dict, log and continue
                        if isinstance(resp, dict) and resp.get("error"):
                            logger.error(
                                "Failed to push results for session %s: %s",
                                session.session_id, resp.get("error")
                            )
                            continue

                        # Mark session as results_sent to avoid re-sending
                        session.status = "completed"
                        session.completed_at = datetime.utcnow()
                        await db.commit()
                        logger.info("Successfully pushed %d match results for job %s (session %s)",
                                    len(processed_results), session.jd_id, session.session_id)
                    except Exception as e:
                        logger.error("Error sending results for session %s: %s", session.session_id, str(e), exc_info=True)
                        continue
                except Exception as e:
                    logger.error(f"Error processing session {session.session_id}: {e}", exc_info=True)
                    continue
        
    except Exception as e:
        logger.error(f"Error in scheduled result sender: {e}", exc_info=True)
                    
                    # Try WebSocket first
                    # ws_sent = await ws_manager.send_to_job_portal(payload)
                    
                    
    #                 if not ws_sent:
    #                     # Fallback to REST API
    #                     logger.info(
    #                         f"WebSocket not available for session {session.session_id}, "
    #                         "using REST API fallback"
    #                     )
    #                     rest_sent = await job_portal_client.send_match_results(payload)
                        
    #                     if rest_sent:
    #                         logger.info(
    #                             f"Successfully sent results via REST for session {session.session_id}"
    #                         )
    #                     else:
    #                         logger.error(
    #                             f"Failed to send results via REST for session {session.session_id}"
    #                         )
    #                         continue
    #                 else:
    #                     logger.info(
    #                         f"Successfully sent results via WebSocket for session {session.session_id}"
    #                     )
                    
    #                 # Mark session as sent (update status or add a sent flag)
    #                 # For now, we can update completed_at or add a custom flag
    #                 session.completed_at = datetime.utcnow()
    #                 await db.commit()
                    
    #             except Exception as session_error:
    #                 logger.error(
    #                     f"Error processing session {session.session_id}: {session_error}",
    #                     exc_info=True
    #                 )
    #                 continue
                    
    # except Exception as e:
    #     logger.error(f"Error in scheduled result sender: {e}", exc_info=True)


def start_scheduler(interval_seconds: int = 30):
    """
    Start the APScheduler to run periodic tasks.
    Runs send_results_to_job_portal every 30 seconds as a backup mechanism.
    """
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already running")
        return
    
    scheduler = AsyncIOScheduler()
    
    # Add job to send results periodically (backup mechanism)
    scheduler.add_job(
        send_results_to_job_portal,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="send_results_backup",
        name="Send match results to job portal (backup)",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Result scheduler started (backup mechanism for result delivery)")


def stop_scheduler():
    """Stop the APScheduler"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Result scheduler stopped")
