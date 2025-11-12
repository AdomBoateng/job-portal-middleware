# models.py
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from sqlalchemy import Column, String, DateTime, ARRAY, Integer
from sqlalchemy.dialects.postgresql import JSONB
from app.services.db import Base

# -------------------------
# SQLAlchemy tables/models
# -------------------------
class MiddlewareSession(Base):
    __tablename__ = "middleware_sessions"
    session_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    jd_id = Column(String, nullable=False)               # Required but not part of primary key
    cv_ids = Column(ARRAY(String), default=[])
    ai_session_id = Column(String, nullable=True)
    status = Column(String, default="pending")         # pending, active, processing, completed, failed, superseded
    retry_count = Column(Integer, default=0)             # Number of retry attempts
    last_failure_reason = Column(String, nullable=True) # Type of last failure
    last_retry_at = Column(DateTime, nullable=True)     # Timestamp of last retry
    next_retry_at = Column(DateTime, nullable=True)     # When next retry should occur
    superseded_at = Column(DateTime, nullable=True)     # When session was superseded
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class MiddlewareReport(Base):
    __tablename__ = "middleware_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))  # Our internal ID
    session_id = Column(String, nullable=False)  # Foreign key to middleware_sessions.session_id
    match_report_id = Column(String, nullable=False)  # AI agent's match_report_id
    jd_id = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    match_results = Column(JSONB, nullable=True)  # JSONB column for match results
    created_at = Column(DateTime, default=datetime.utcnow)
    ai_created_at = Column(String, nullable=True)  # Store AI agent's created_at timestamp


# -------------------------
# Pydantic models / schemas
# -------------------------
class JDIn(BaseModel):
    job: dict                       # full job object (use job.title, job.description, etc.)
    responsibilities: List[str] = []
    skills: List[str] = []

class CVForJD(BaseModel):
    id: int
    user_id: int
    firstname: Optional[str]
    lastname: Optional[str]
    resume: Optional[str]           # resume URL (string)
    email: Optional[str] = None
    phone: Optional[str] = None
    created_date: Optional[str] = None
    # ... accept other fields as in job portal payload

class CreateSessionRequest(BaseModel):
    jd_id: str
    cv_ids: List[str] = []

class SessionResponse(BaseModel):
    session_id: str
    jd_id: Optional[str] = None
    cv_ids: List[str] = []
    ai_session_id: Optional[str] = None
    status: str
    last_checked: Optional[datetime]

# AI Agent API payload models
class AIJobDescription(BaseModel):
    """Job description format for AI agent API"""
    jd_id: str
    title: str
    description: str
    skills: List[str] = []
    responsibilities: List[str] = []

class AICV(BaseModel):
    """CV format for AI agent API"""
    cv_id: str
    jd_id: str
    filename: str
    base64_content: str

class AIAgentSessionPayload(BaseModel):
    """Complete payload format for AI agent session API"""
    session_id: str
    job_descriptions: List[AIJobDescription]
    cvs: List[AICV]
    status: str = "active"  # Session status: pending, active, processing, completed, failed

# New models for AI Agent match report format
class MatchResult(BaseModel):
    """Individual CV match result in AI agent response"""
    jd_id: str
    cv_id: str
    category: str  # REJECT, ACCEPT, etc.
    total_score: float
    sim_embed: Optional[float] = None
    skill_coverage: Optional[float] = None
    must_have_penalty: Optional[float] = None
    llm_consistency: Optional[float] = None
    rationale: str

class MatchReport(BaseModel):
    """Match report from AI agent"""
    match_report_id: str
    session_id: str
    jd_id: str
    summary: str
    match_results: List[MatchResult]
    created_at: str

class AIAgentReportResponse(BaseModel):
    """AI agent report response format"""
    status: str  # completed, processing, failed
    reports: Optional[List[MatchReport]] = None
    message: Optional[str] = None
