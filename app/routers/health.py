# routers/health.py
from fastapi import APIRouter, HTTPException
from app.helpers.validation import HealthCheckResponse
from app.services import job_portal_client, ai_agent_client
from app.services.db import engine
from sqlalchemy import text
import httpx

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/", response_model=HealthCheckResponse)
async def health_check():
    """Comprehensive health check for the middleware service."""
    dependencies = {}
    
    # Check database connection
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        dependencies["database"] = "healthy"
    except Exception:
        dependencies["database"] = "unhealthy"
    
    # Check job portal connection
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{job_portal_client.JOB_PORTAL_API_URL}/health")
            dependencies["job_portal"] = "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        dependencies["job_portal"] = "unhealthy"
    
    # Check AI agent connection
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{ai_agent_client.AI_AGENT_URL}/health")
            dependencies["ai_agent"] = "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        dependencies["ai_agent"] = "unhealthy"
    
    # Determine overall status
    status = "healthy" if all(dep == "healthy" for dep in dependencies.values()) else "degraded"
    
    return HealthCheckResponse(
        status=status,
        dependencies=dependencies
    )

@router.get("/liveness")
async def liveness_check():
    """Simple liveness check."""
    return {"status": "alive"}

@router.get("/readiness")
async def readiness_check():
    """Readiness check including critical dependencies."""
    try:
        # Check database
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Service not ready")