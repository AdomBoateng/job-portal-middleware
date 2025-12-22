# services/monitor.py
import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, List
from dotenv import load_dotenv
from sqlalchemy import select, update
from app.services import ai_agent_client
from app.services.db import AsyncSessionLocal
from app.services.application_processor import store_match_report, send_results_to_job_portal
from app.models.new_models import NewSession, NewReport

load_dotenv()
INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", 30))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_match_results_for_job_portal(match_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map AI agent match results into the job-portal expected format."""
    processed_results = []

    for result in match_results:
        category = result.get("category", "").upper()
        if category == "REJECT":
            mapped_category = "weak"
        elif category == "ACCEPT":
            mapped_category = "strong"
        else:
            mapped_category = result.get("category", "moderate").lower()

        processed = {
            "cv_id": result.get("cv_id"),
            "total_score": result.get("total_score", 0.0),
            "category": mapped_category,
            "rationale": result.get("rationale", ""),
        }

        # optional fields
        if result.get("sim_embed") is not None:
            processed["sim_embed"] = result.get("sim_embed")
        if result.get("skill_coverage") is not None:
            processed["skill_coverage"] = result.get("skill_coverage")
        if result.get("must_have_penalty") is not None:
            processed["must_have_penalty"] = result.get("must_have_penalty")
        if result.get("llm_consistency") is not None:
            processed["llm_consistency"] = result.get("llm_consistency")

        processed_results.append(processed)

    return processed_results


async def monitor_loop():
    """Main loop: poll processing sessions and forward completed reports."""
    logger.info("Starting monitor loop (poll AI) with interval %d seconds", INTERVAL)
    while True:
        try:
            await check_processing_sessions()
        except Exception as e:
            logger.exception("Error in monitor loop: %s", e)
        await asyncio.sleep(INTERVAL)


async def check_processing_sessions():
    """Find NewSession records in 'processing' state and check AI reports."""
    async with AsyncSessionLocal() as db:
        try:
            stmt = select(NewSession).where(NewSession.status == "processing")
            res = await db.execute(stmt)
            sessions = res.scalars().all()

            logger.info("Monitor: checking %d processing sessions", len(sessions))
            for sess in sessions:
                try:
                    await check_session_completion(db, sess)
                except Exception as e:
                    logger.exception("Error checking session %s: %s", sess.session_id, e)
        except Exception as e:
            logger.exception("Error querying processing sessions: %s", e)


async def check_session_completion(db, session: NewSession):
    """Check single NewSession against AI agent; store and forward results if ready."""
    try:
        report = await ai_agent_client.fetch_report(session.session_id, session.jd_id)

        if not report:
            return

        status = report.get("status")
        if status != "completed":
            # still processing or failed
            if status == "failed":
                await update_session_status(db, session.session_id, "failed")
            return

        logger.info("Monitor: session %s completed - storing and forwarding results", session.session_id)

        # store reports using application_processor helper (handles NewReport model)
        if report.get("reports"):
            for r in report.get("reports"):
                await store_match_report(db, r, session.session_id, session.jd_id)
        else:
            # single report or new format
            await store_match_report(db, report, session.session_id, session.jd_id)

        # Convert and push results (use centralized sender in application_processor)
        try:
            await send_results_to_job_portal(db, session.session_id, session.jd_id, report)
            logger.info("Monitor: pushed results for job %s", session.jd_id)
        except Exception:
            logger.exception("Failed to push results for session %s to job portal", session.session_id)

        # mark completed
        await update_session_status(db, session.session_id, "completed")
        try:
            upd = update(NewSession).where(NewSession.session_id == session.session_id).values(completed_at=datetime.utcnow())
            await db.execute(upd)
            await db.commit()
        except Exception:
            logger.debug("Could not set completed_at for session %s", session.session_id)

    except Exception as e:
        logger.exception("Error while checking completion for session %s: %s", getattr(session, "session_id", "<unknown>"), e)


async def update_session_status(db, session_id: str, status: str):
    """Update status for a NewSession."""
    try:
        upd = update(NewSession).where(NewSession.session_id == session_id).values(status=status, updated_at=datetime.utcnow())
        await db.execute(upd)
        await db.commit()
        logger.info("Updated NewSession %s -> %s", session_id, status)
    except Exception as e:
        logger.exception("Failed to update session %s status to %s: %s", session_id, status, e)


async def get_stored_reports(db, session_id: str, jd_id: str | None = None):
    """Return stored NewReport entries for a session."""
    try:
        if jd_id:
            stmt = select(NewReport).where(NewReport.session_id == session_id, NewReport.jd_id == jd_id).order_by(NewReport.created_at.desc())
        else:
            stmt = select(NewReport).where(NewReport.session_id == session_id).order_by(NewReport.created_at.desc())

        res = await db.execute(stmt)
        reports = res.scalars().all()
        out = []
        for r in reports:
            out.append({
                "id": r.id,
                "session_id": r.session_id,
                "jd_id": r.jd_id,
                "match_results": json.loads(r.match_results) if getattr(r, "match_results", None) else [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return out
    except Exception as e:
        logger.exception("Failed to get stored reports for %s: %s", session_id, e)
        return []


# retry_failed_sessions intentionally left as a noop placeholder because the
# application processor has the payload context required to re-submit an
# application if necessary. If you want automatic retries, implement logic to
# re-fetch the original application and call process_job_application.
async def retry_failed_sessions():
    logger.debug("retry_failed_sessions: disabled in per-application workflow")
    
