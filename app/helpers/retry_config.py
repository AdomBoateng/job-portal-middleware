# helpers/retry_config.py
"""
Retry configuration for session failure handling.
Defines retry limits and delays for different types of failures.
"""
from datetime import timedelta

# Retry limits for different failure types
RETRY_LIMITS = {
    "network_error": 5,          # Network/connection issues - often temporary
    "ai_agent_error": 3,         # AI agent communication/processing errors
    "job_portal_error": 3,       # Job portal API errors
    "download_error": 3,         # CV download failures
    "validation_error": 1,       # Data validation errors - likely permanent
    "timeout_error": 4,          # Timeout errors - may resolve
    "unknown_error": 2,          # Unclassified errors
    "default": 3                 # Default retry limit
}

# Base delay in minutes for retry attempts (will use exponential backoff)
BASE_RETRY_DELAY_MINUTES = 2

# Maximum retry delay in hours (cap for exponential backoff)
MAX_RETRY_DELAY_HOURS = 2

# Enable exponential backoff
ENABLE_EXPONENTIAL_BACKOFF = True


def get_retry_limit(failure_reason: str) -> int:
    """
    Get the retry limit for a specific failure type.
    
    Args:
        failure_reason: Type of failure (e.g., "network_error", "ai_agent_error")
        
    Returns:
        Maximum number of retries allowed for this failure type
    """
    return RETRY_LIMITS.get(failure_reason, RETRY_LIMITS["default"])


def calculate_next_retry_time(retry_count: int, failure_reason: str = "default") -> timedelta:
    """
    Calculate the delay until next retry attempt using exponential backoff.
    
    Args:
        retry_count: Current number of retry attempts
        failure_reason: Type of failure (for potential custom logic)
        
    Returns:
        timedelta representing when the next retry should occur
    """
    if ENABLE_EXPONENTIAL_BACKOFF:
        # Exponential backoff: 2^retry_count * base_delay
        delay_minutes = (2 ** retry_count) * BASE_RETRY_DELAY_MINUTES
        
        # Cap at maximum delay
        max_delay_minutes = MAX_RETRY_DELAY_HOURS * 60
        delay_minutes = min(delay_minutes, max_delay_minutes)
    else:
        # Fixed delay
        delay_minutes = BASE_RETRY_DELAY_MINUTES
    
    return timedelta(minutes=delay_minutes)


def classify_error(error_message: str) -> str:
    """
    Classify an error based on its message to determine failure type.
    
    Args:
        error_message: The error message string
        
    Returns:
        Failure type classification
    """
    error_lower = error_message.lower()
    
    # Network/connection errors
    if any(keyword in error_lower for keyword in [
        "connection", "network", "dns", "unreachable", "timeout", "refused"
    ]):
        if "timeout" in error_lower:
            return "timeout_error"
        return "network_error"
    
    # AI agent errors
    if any(keyword in error_lower for keyword in [
        "ai agent", "ai_agent", "processing failed", "match failed"
    ]):
        return "ai_agent_error"
    
    # Job portal errors
    if any(keyword in error_lower for keyword in [
        "job portal", "job_portal", "fetch_jd", "fetch_cvs"
    ]):
        return "job_portal_error"
    
    # Download errors
    if any(keyword in error_lower for keyword in [
        "download", "resume", "cv download", "base64"
    ]):
        return "download_error"
    
    # Validation errors
    if any(keyword in error_lower for keyword in [
        "validation", "invalid", "missing field", "schema"
    ]):
        return "validation_error"
    
    # Default
    return "unknown_error"


def should_retry(retry_count: int, failure_reason: str) -> bool:
    """
    Determine if a session should be retried based on current retry count and failure type.
    
    Args:
        retry_count: Current number of retries
        failure_reason: Type of failure
        
    Returns:
        True if should retry, False if should supersede
    """
    max_retries = get_retry_limit(failure_reason)
    return retry_count < max_retries
