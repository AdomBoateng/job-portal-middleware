from fastapi import APIRouter, BackgroundTasks
from typing import Dict, Any

from app.services.db import AsyncSessionLocal
from app.services.application_processor import process_job_application

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/process", summary="Receive application payload from job portal and process")
async def receive_application(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Endpoint to receive application payloads from the job portal (REST webhook).

    Behavior:
    - Immediately acknowledge receipt to the caller
    - Schedule background processing that will create a session, send to AI agent,
      collect results and forward them to the job portal, and mark the session complete
    - Prevent duplicate processing: the service layer will skip if the application was already processed
    """

    # Acknowledge immediately and process in background
    async def _bg_process(msg: Dict[str, Any]):
        try:
            async with AsyncSessionLocal() as db:
                await process_job_application(db, msg)
        except Exception as e:
            # Log errors in background; can't raise to caller
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Background processing failed: {e}", exc_info=True)

    # Use BackgroundTasks to schedule without blocking the request thread
    # Pass the async function and its argument directly. BackgroundTasks will
    # properly await the coroutine in the running event loop. Avoid calling
    # asyncio.create_task from a thread (that causes "no running event loop").
    background_tasks.add_task(_bg_process, payload)

    return {
        "status": "received",
        "message": "Application received and scheduled for processing",
        "application_id": payload.get("application_id")
    }
