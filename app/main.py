# import os
import asyncio
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from app.routers import sessions, cvs, report, jd, health, applications
from app.services.db import engine, Base
# Lazy-import monitor and scheduler when explicitly enabled to avoid
# importing background modules at startup when running applications-only.
from app.helpers.logging_config import setup_logging
from app.helpers.middleware import setup_middleware

load_dotenv()
setup_logging()
logger = logging.getLogger("app.main")

app = FastAPI(title="AI Middleware Orchestrator")
setup_middleware(app)

# include routers
app.include_router(sessions.router)
app.include_router(cvs.router)
app.include_router(report.router)
app.include_router(jd.router)
app.include_router(health.router)
app.include_router(applications.router)
    

# track background tasks so we can cancel them on shutdown
monitor_task = None


@app.on_event("startup")
async def startup():
    # create tables (skip if database is not available)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.warning(f"Database connection failed during startup: {e}")
        logger.warning("Continuing without database initialization")
    
    # Start background monitor only when enabled. The new workflow is
    # per-application: incoming requests (see `app/routers/applications.py`)
    # will attempt to process and fetch results synchronously. The monitor
    # acts as a reliable fallback that polls for any sessions left in
    # "processing" state and completes them.
    # Default to false: run only the per-application flow in `applications.py` unless explicitly enabled
    monitor_enabled = os.getenv("ENABLE_MONITOR", "false").lower() in ("1", "true", "yes")
    global monitor_task
    if monitor_enabled:
        try:
            # import lazily to avoid importing monitor module when disabled
            from app.services.monitor import monitor_loop
            monitor_task = asyncio.create_task(monitor_loop())
            logger.info("Background monitor started")
        except Exception as e:
            logger.error(f"Failed to start monitor: {e}")
    else:
        logger.info("Background monitor disabled via ENABLE_MONITOR env var")
    
    # start result scheduler for sending results to job portal (optional)
    scheduler_enabled = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("1", "true", "yes")
    # Log current startup configuration
    logger.info("Startup configuration: ENABLE_MONITOR=%s, ENABLE_SCHEDULER=%s", monitor_enabled, scheduler_enabled)

    if scheduler_enabled:
        try:
            # import lazily to avoid importing scheduler when disabled
            from app.services.result_scheduler import start_scheduler
            start_scheduler(interval_seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "30")))
            logger.info("Result scheduler started")
        except Exception as e:
            logger.error(f"Failed to start result scheduler: {e}")
    else:
        logger.info("Result scheduler disabled via ENABLE_SCHEDULER env var")

@app.on_event("shutdown")
async def shutdown():
    # stop the result scheduler if available
    try:
        from app.services.result_scheduler import stop_scheduler
        stop_scheduler()
        logger.info("Result scheduler stopped")
    except ImportError:
        logger.debug("Result scheduler module not available; nothing to stop")
    except Exception as e:
        logger.error(f"Error stopping result scheduler: {e}")

    # cancel the monitor task if it was started
    global monitor_task
    if monitor_task is not None:
        try:
            monitor_task.cancel()
            await monitor_task
            logger.info("Background monitor stopped")
        except asyncio.CancelledError:
            logger.info("Background monitor task cancelled")
        except Exception as e:
            logger.error(f"Error stopping monitor task: {e}")
