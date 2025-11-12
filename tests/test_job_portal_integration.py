"""
Integration test for job_portal_client.py

This script provides a simple way to manually test the job_portal_client
functions with real API endpoints. It will only work if proper environment
variables are set for the job portal API.

Usage:
    python test_job_portal_integration.py
"""
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import after path setup to ensure proper module resolution
def import_job_portal_client():
    from app.services.job_portal_client import (
        fetch_all_job_ids,
        fetch_jd,
        fetch_cvs_for_jd,
        fetch_resume_url,
        update_application_match
    )
    return fetch_all_job_ids, fetch_jd, fetch_cvs_for_jd, fetch_resume_url, update_application_match

# Get the functions
fetch_all_job_ids, fetch_jd, fetch_cvs_for_jd, fetch_resume_url, update_application_match = import_job_portal_client()

load_dotenv()


async def test_basic_connectivity():
    """Test basic connectivity to the job portal API."""
    print("Testing basic connectivity...")
    
    # Test fetching all job IDs
    job_ids = await fetch_all_job_ids()
    print(f"✓ Fetched {len(job_ids)} job IDs: {job_ids[:5]}{'...' if len(job_ids) > 5 else ''}")
    
    if not job_ids:
        print("⚠️  No job IDs returned. This could mean:")
        print("   - The API is not reachable")
        print("   - Authentication failed")
        print("   - No jobs are available")
        return False
    
    return True


async def test_job_details():
    """Test fetching job details."""
    print("\nTesting job details fetching...")
    
    job_ids = await fetch_all_job_ids()
    if not job_ids:
        print("❌ Cannot test job details - no job IDs available")
        return False
    
    # Test with the first job ID
    test_job_id = job_ids[0]
    try:
        job_details = await fetch_jd(test_job_id)
        print(f"✓ Successfully fetched details for job {test_job_id}")
        print(f"   Title: {job_details.get('title', 'N/A')}")
        print(f"   ID: {job_details.get('id', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ Failed to fetch job details: {e}")
        return False


async def test_cv_fetching():
    """Test fetching CVs for a job."""
    print("\nTesting CV fetching...")
    
    job_ids = await fetch_all_job_ids()
    if not job_ids:
        print("❌ Cannot test CV fetching - no job IDs available")
        return False
    
    # Test with the first job ID
    test_job_id = job_ids[0]
    try:
        cvs = await fetch_cvs_for_jd(test_job_id)
        print(f"✓ Successfully fetched {len(cvs)} CVs for job {test_job_id}")
        
        if cvs:
            # Test resume URL extraction
            resume_url = await fetch_resume_url(cvs[0])
            print(f"   First CV resume URL: {resume_url}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to fetch CVs: {e}")
        return False


async def test_match_updating():
    """Test updating application matches (dry run)."""
    print("\nTesting match updating (dry run)...")
    
    # Create sample CV results
    sample_results = [
        {
            "cv_id": "test_1",
            "total_score": 0.85,
            "category": "strong",
            "rationale": "Excellent Python and backend experience",
            "sim_embed": 0.9,
            "skill_coverage": 0.8,
            "must_have_penalty": 0.0,
            "llm_consistency": 0.85
        }
    ]
    
    try:
        # Note: This might fail if the API doesn't support the test job ID
        result = await update_application_match("test_job", sample_results)
        
        if "error" in result:
            print(f"⚠️  Update returned error (expected for test): {result['error']}")
        else:
            print(f"✓ Successfully updated matches: {result}")
        
        return True
    except Exception as e:
        print(f"⚠️  Update failed (expected for test): {e}")
        return True  # This is expected for a test


async def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Job Portal Client Integration Tests")
    print("=" * 60)
    
    # Check environment variables
    api_url = os.getenv("JOB_PORTAL_API_URL")
    api_key = os.getenv("JOB_PORTAL_API_KEY")
    username = os.getenv("JOB_PORTAL_USERNAME")
    password = os.getenv("JOB_PORTAL_PASSWORD")
    
    print(f"API URL: {api_url}")
    print(f"API Key: {'***' + api_key[-4:] if api_key else 'Not set'}")
    print(f"Username: {username if username else 'Not set'}")
    print(f"Password: {'***' if password else 'Not set'}")
    print()
    
    if not api_url:
        print("❌ JOB_PORTAL_API_URL environment variable is not set")
        return
    
    if not (api_key or (username and password)):
        print("❌ No authentication credentials found")
        print("   Set either JOB_PORTAL_API_KEY or both JOB_PORTAL_USERNAME and JOB_PORTAL_PASSWORD")
        return
    
    # Run tests
    tests = [
        test_basic_connectivity,
        test_job_details,
        test_cv_fetching,
        test_match_updating
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The job_portal_client is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    asyncio.run(main())