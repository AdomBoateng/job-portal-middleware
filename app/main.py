# import os
import asyncio
import logging
from fastapi import FastAPI
from app.routers import sessions, cvs, report, jd, health
from app.services.db import engine, Base
from dotenv import load_dotenv
from app.services.monitor import monitor_loop
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
    
    # start background monitor (also handle gracefully)
    try:
        asyncio.create_task(monitor_loop())
        logger.info("Background monitor started")
    except Exception as e:
        logger.error(f"Failed to start monitor: {e}")

@app.on_event("shutdown")
async def shutdown():
    pass
