# models/new_models.py
"""
New models for the updated workflow: one CV per JD, one session per application.
This file does not affect or modify the legacy models.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime
from typing import List
from pydantic import BaseModel

Base = declarative_base()

class NewSession(Base):
    __tablename__ = "new_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False)
    jd_id = Column(String(64), nullable=False)
    cv_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="processing")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime)
    # Relationship to reports
    reports = relationship("NewReport", back_populates="session")

class NewReport(Base):
    __tablename__ = "new_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("new_sessions.session_id"), nullable=False)
    jd_id = Column(String(64), nullable=False)
    cv_id = Column(String(64), nullable=False)
    total_score = Column(Float, default=0.0)
    category = Column(String(32))
    rationale = Column(Text)
    sim_embed = Column(Text)
    skill_coverage = Column(Text)
    must_have_penalty = Column(Float)
    llm_consistency = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Relationship to session
    session = relationship("NewSession", back_populates="reports")


# Pydantic models for AI Agent API integration
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
    status: str = "active"
