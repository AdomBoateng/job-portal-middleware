import os
# import httpx
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv
import logging

load_dotenv()
JOB_PORTAL_API_URL = os.getenv("JOB_PORTAL_API_URL")
JOB_PORTAL_API_KEY = os.getenv("JOB_PORTAL_API_KEY", "supersecretkey")
# JOB_PORTAL_USERNAME = os.getenv("JOB_PORTAL_USERNAME", "admin@gmail.com")
# JOB_PORTAL_PASSWORD = os.getenv("JOB_PORTAL_PASSWORD", "password")

logger = logging.getLogger("app.job_portal_client")

def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers for job portal API."""
    headers = {"Content-Type": "application/json"}
    
    if JOB_PORTAL_API_KEY:
        headers["Authorization"] = f"Bearer {JOB_PORTAL_API_KEY}"
    # elif JOB_PORTAL_USERNAME and JOB_PORTAL_PASSWORD:
    #     headers["Authorization"] = f"Basic {JOB_PORTAL_USERNAME}:{JOB_PORTAL_PASSWORD}"
    
    return headers

# async def fetch_all_job_ids() -> List[int]:
#     """Fetch all job IDs from job portal with proper error handling."""
#     try:
#         headers = get_auth_headers()
#         async with httpx.AsyncClient(timeout=30) as client:
#             r = await client.get(f"{JOB_PORTAL_API_URL}/api/v1/jobs", headers=headers)
            
#             if r.status_code == 403:
#                 logger.warning("Access forbidden to job portal - check authentication credentials")
#                 return []  # Return empty list instead of crashing
            
#             r.raise_for_status()
#             jobs = r.json()
#             logger.info(f"Fetched {len(jobs)} jobs from job portal")
#             return [job["id"] for job in jobs]
            
#     except httpx.ConnectError as e:
#         logger.warning(f"Cannot connect to job portal at {JOB_PORTAL_API_URL}: {e}")
#         return []
#     except httpx.HTTPStatusError as e:
#         logger.error(f"HTTP error accessing job portal: {e.response.status_code} - {e.response.text}")
#         return []
#     except Exception as e:
#         logger.error(f"Unexpected error fetching job IDs: {e}")
#         return []

# async def fetch_all_jobs_with_status() -> List[Dict[str, Any]]:
#     """Fetch all jobs with their status information from job portal."""
#     try:
#         headers = get_auth_headers()
#         async with httpx.AsyncClient(timeout=30) as client:
#             r = await client.get(f"{JOB_PORTAL_API_URL}/api/v1/jobs", headers=headers)
            
#             if r.status_code == 403:
#                 logger.warning("Access forbidden to job portal - check authentication credentials")
#                 return []
            
#             r.raise_for_status()
#             jobs = r.json()
#             logger.info(f"Fetched {len(jobs)} jobs with status from job portal")
#             return jobs
            
#     except httpx.ConnectError as e:
#         logger.warning(f"Cannot connect to job portal at {JOB_PORTAL_API_URL}: {e}")
#         return []
#     except httpx.HTTPStatusError as e:
#         logger.error(f"HTTP error accessing job portal: {e.response.status_code} - {e.response.text}")
#         return []
#     except Exception as e:
#         logger.error(f"Unexpected error fetching jobs with status: {e}")
#         return []

# async def get_job_status(jd_id: int) -> str:
#     """Get the status of a specific job."""
#     try:
#         job = await fetch_jd(jd_id)
#         return job.get("job", {}).get("status", "unknown")
#     except Exception as e:
#         logger.error(f"Error fetching job status for {jd_id}: {e}")
#         return "unknown"

# async def fetch_jd(jd_id: int) -> Dict[str, Any]:
#     """Fetch job description with error handling."""
#     try:
#         headers = get_auth_headers()
#         async with httpx.AsyncClient(timeout=30) as client:
#             r = await client.get(f"{JOB_PORTAL_API_URL}/api/v1/jobs/{jd_id}", headers=headers)
            
#             if r.status_code == 403:
#                 logger.warning(f"Access forbidden to job {jd_id}")
#                 raise httpx.HTTPStatusError("Access forbidden", request=r.request, response=r)
            
#             r.raise_for_status()
#             return r.json()
            
#     except httpx.ConnectError as e:
#         logger.error(f"Cannot connect to job portal: {e}")
#         raise
#     except Exception as e:
#         logger.error(f"Error fetching job {jd_id}: {e}")
#         raise

# async def fetch_cvs_for_jd(jd_id: int) -> List[Dict[str, Any]]:
#     """Fetch CVs for a job with error handling."""
#     try:
#         headers = get_auth_headers()
#         async with httpx.AsyncClient(timeout=30) as client:
#             r = await client.get(f"{JOB_PORTAL_API_URL}/api/v1/job-applications?job_id={jd_id}", headers=headers)
            
#             if r.status_code == 403:
#                 logger.warning(f"Access forbidden to applications for job {jd_id}")
#                 return []
            
#             r.raise_for_status()
#             applications = r.json()
#             logger.info(f"Fetched {len(applications)} applications for job {jd_id}")
#             return applications
            
#     except httpx.ConnectError as e:
#         logger.warning(f"Cannot connect to job portal: {e}")
#         return []
#     except Exception as e:
#         logger.error(f"Error fetching CVs for job {jd_id}: {e}")
#         return []

# async def fetch_resume_url(application: Dict[str, Any]) -> str:
#     return application.get("resume")  # caller will validate

def update_application_match(cv_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "results": cv_results
        }
        
        headers = {
        "Content-Type": "application/json",
        "X-AI-Secret": JOB_PORTAL_API_KEY,
        }
        # async with httpx.AsyncClient(timeout=60, verify=False) as client:
        result= requests.post(
            JOB_PORTAL_API_URL, 
            json=payload, 
            headers=headers, 
            timeout=60,
            verify=False
        )   
        
        # if r.status_code == 403:
        #     logger.warning(Access forbidden when pushing results for job)
        #     return {"error": "Access forbidden"}
        
        # r.raise_for_status()
        print(payload)
        
        print(result.json())
        # logger.info(f"Successfully pushed result for job {job_id}")
        return result
            
    # except httpx.ConnectError as e:
    #     logger.error(f"Cannot connect to job portal: {e}")
    #     return {"error": f"Connection failed: {e}"}
    # except Exception as e:
    #     logger.error(f"Error pushing results for job {job_id}: {e}")
    #     return {"error": f"Failed to push results: {e}"}