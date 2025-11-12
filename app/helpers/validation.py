# helpers/validation.py
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, validator, Field
from datetime import datetime

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None

class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class CVMatchResult(BaseModel):
    """Validation model for CV match results."""
    cv_id: str
    total_score: float = Field(description="Total matching score")
    category: str = Field(description="Matching category: REJECT, ACCEPT, STRONG, MODERATE, WEAK, etc.")
    rationale: str = Field(min_length=10, description="Explanation for the score")
    sim_embed: Optional[float] = Field(default=None, description="Similarity embedding score")
    skill_coverage: Optional[float] = Field(default=None, description="Skill coverage score")
    must_have_penalty: Optional[float] = Field(default=None, description="Penalty for missing must-have skills")
    llm_consistency: Optional[float] = Field(default=None, description="LLM consistency score")
    
    # Add jd_id for compatibility with new format
    jd_id: Optional[str] = Field(default=None, description="Job description ID")

    @validator('category')
    def validate_category(cls, v):
        # Expanded category list to support new AI agent format
        allowed_categories = ['REJECT', 'ACCEPT', 'STRONG', 'MODERATE', 'WEAK', 'strong', 'moderate', 'weak']
        if v not in allowed_categories:
            raise ValueError(f'Category must be one of {allowed_categories}')
        return v

class JobApplicationRequest(BaseModel):
    """Request model for job application processing."""
    job_id: str
    force_reprocess: bool = False
    include_processed: bool = False

class AddCVsRequest(BaseModel):
    """Request model for adding CVs to a session."""
    cvs: List[Dict[str, Any]]
    
    @validator('cvs')
    def validate_cvs(cls, v):
        if not v:
            raise ValueError('CVs list cannot be empty')
        
        required_fields = ['cv_id', 'filename', 'base64_content']
        for cv in v:
            missing_fields = [field for field in required_fields if field not in cv]
            if missing_fields:
                raise ValueError(f'Missing required fields: {missing_fields}')
        return v

class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    dependencies: Dict[str, str] = {}

def validate_session_id(session_id: str) -> bool:
    """Validate session ID format."""
    import re
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(session_id))

def validate_job_id(job_id: str) -> bool:
    """Validate job ID format."""
    try:
        int(job_id)
        return True
    except ValueError:
        return False