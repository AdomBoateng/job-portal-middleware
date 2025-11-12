# helpers/exceptions.py
from fastapi import HTTPException
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MiddlewareException(Exception):
    """Base exception class for middleware-specific errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class JobPortalException(MiddlewareException):
    """Exception for job portal API errors."""
    pass

class AIAgentException(MiddlewareException):
    """Exception for AI agent API errors."""
    pass

class DatabaseException(MiddlewareException):
    """Exception for database-related errors."""
    pass

class ValidationException(MiddlewareException):
    """Exception for validation errors."""
    pass

class SessionNotFoundException(MiddlewareException):
    """Exception when session is not found."""
    pass

def handle_api_exception(func):
    """Decorator to handle API exceptions consistently."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except JobPortalException as e:
            logger.error(f"Job Portal Error: {e.message}", extra={"details": e.details})
            raise HTTPException(status_code=502, detail=f"Job Portal Error: {e.message}")
        except AIAgentException as e:
            logger.error(f"AI Agent Error: {e.message}", extra={"details": e.details})
            raise HTTPException(status_code=502, detail=f"AI Agent Error: {e.message}")
        except SessionNotFoundException as e:
            logger.error(f"Session Not Found: {e.message}", extra={"details": e.details})
            raise HTTPException(status_code=404, detail=f"Session not found: {e.message}")
        except ValidationException as e:
            logger.error(f"Validation Error: {e.message}", extra={"details": e.details})
            raise HTTPException(status_code=400, detail=f"Validation Error: {e.message}")
        except DatabaseException as e:
            logger.error(f"Database Error: {e.message}", extra={"details": e.details})
            raise HTTPException(status_code=500, detail="Internal database error")
        except Exception as e:
            logger.error(f"Unexpected Error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    return wrapper

def create_http_exception(status_code: int, message: str, details: Optional[Dict[str, Any]] = None) -> HTTPException:
    """Create a standardized HTTP exception."""
    detail = {"message": message}
    if details:
        detail["details"] = details
    return HTTPException(status_code=status_code, detail=detail)