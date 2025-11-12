"""
Tests for job_portal_client.py

This test suite covers all functions in the job_portal_client module
with proper mocking to avoid making real API calls.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
import os

# Import the module to test
from app.services.job_portal_client import (
    fetch_all_job_ids,
    fetch_jd,
    fetch_cvs_for_jd,
    fetch_resume_url,
    update_application_match
)


class TestGetAuthHeaders:
    """Test the get_auth_headers function."""
    
    def test_auth_headers_with_api_key(self):
        """Test auth headers when API key is provided."""
        with patch.dict(os.environ, {
            'JOB_PORTAL_API_KEY': 'test-api-key',
            'JOB_PORTAL_USERNAME': '',
            'JOB_PORTAL_PASSWORD': ''
        }):
            # Need to reload the module to pick up new env vars
            import importlib
            from app.services import job_portal_client
            importlib.reload(job_portal_client)
            
            headers = job_portal_client.get_auth_headers()
            
            assert headers["Content-Type"] == "application/json"
            assert headers["Authorization"] == "Bearer test-api-key"
    
    def test_auth_headers_with_username_password(self):
        """Test auth headers when username/password are provided."""
        with patch.dict(os.environ, {
            'JOB_PORTAL_API_KEY': '',
            'JOB_PORTAL_USERNAME': 'testuser',
            'JOB_PORTAL_PASSWORD': 'testpass'
        }):
            import importlib
            from app.services import job_portal_client
            importlib.reload(job_portal_client)
            
            headers = job_portal_client.get_auth_headers()
            
            assert headers["Content-Type"] == "application/json"
            assert headers["Authorization"] == "Basic testuser:testpass"
    
    def test_auth_headers_no_credentials(self):
        """Test auth headers when no credentials are provided."""
        with patch.dict(os.environ, {
            'JOB_PORTAL_API_KEY': '',
            'JOB_PORTAL_USERNAME': '',
            'JOB_PORTAL_PASSWORD': ''
        }):
            import importlib
            from app.services import job_portal_client
            importlib.reload(job_portal_client)
            
            headers = job_portal_client.get_auth_headers()
            
            assert headers["Content-Type"] == "application/json"
            assert "Authorization" not in headers


class TestFetchAllJobIds:
    """Test the fetch_all_job_ids function."""
    
    @pytest.mark.asyncio
    async def test_fetch_all_job_ids_success(self):
        """Test successful fetching of job IDs."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "title": "Job 1"},
            {"id": 2, "title": "Job 2"},
            {"id": 3, "title": "Job 3"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_all_job_ids()
            
            assert result == [1, 2, 3]
            mock_instance.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_all_job_ids_forbidden(self):
        """Test handling of 403 Forbidden response."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_all_job_ids()
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_fetch_all_job_ids_connection_error(self):
        """Test handling of connection errors."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            
            result = await fetch_all_job_ids()
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_fetch_all_job_ids_http_error(self):
        """Test handling of HTTP status errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_response
            )
            
            result = await fetch_all_job_ids()
            
            assert result == []


class TestFetchJd:
    """Test the fetch_jd function."""
    
    @pytest.mark.asyncio
    async def test_fetch_jd_success(self):
        """Test successful fetching of job description."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "title": "Software Engineer",
            "description": "We are looking for a software engineer..."
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_jd(1)
            
            assert result["id"] == 1
            assert result["title"] == "Software Engineer"
            mock_instance.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_jd_forbidden(self):
        """Test handling of 403 Forbidden response."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_jd(1)
    
    @pytest.mark.asyncio
    async def test_fetch_jd_connection_error(self):
        """Test handling of connection errors."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            
            with pytest.raises(httpx.ConnectError):
                await fetch_jd(1)


class TestFetchCvsForJd:
    """Test the fetch_cvs_for_jd function."""
    
    @pytest.mark.asyncio
    async def test_fetch_cvs_for_jd_success(self):
        """Test successful fetching of CVs for a job."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "resume": "resume1.pdf", "candidate": "John Doe"},
            {"id": 2, "resume": "resume2.pdf", "candidate": "Jane Smith"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_cvs_for_jd(1)
            
            assert len(result) == 2
            assert result[0]["candidate"] == "John Doe"
            assert result[1]["candidate"] == "Jane Smith"
    
    @pytest.mark.asyncio
    async def test_fetch_cvs_for_jd_forbidden(self):
        """Test handling of 403 Forbidden response."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(return_value=mock_response)
            
            result = await fetch_cvs_for_jd(1)
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_fetch_cvs_for_jd_connection_error(self):
        """Test handling of connection errors."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            
            result = await fetch_cvs_for_jd(1)
            
            assert result == []


class TestFetchResumeUrl:
    """Test the fetch_resume_url function."""
    
    @pytest.mark.asyncio
    async def test_fetch_resume_url_success(self):
        """Test successful extraction of resume URL."""
        application = {
            "id": 1,
            "resume": "https://example.com/resume.pdf",
            "candidate": "John Doe"
        }
        
        result = await fetch_resume_url(application)
        
        assert result == "https://example.com/resume.pdf"
    
    @pytest.mark.asyncio
    async def test_fetch_resume_url_missing(self):
        """Test when resume URL is missing."""
        application = {
            "id": 1,
            "candidate": "John Doe"
        }
        
        result = await fetch_resume_url(application)
        
        assert result is None


class TestUpdateApplicationMatch:
    """Test the update_application_match function."""
    
    @pytest.mark.asyncio
    async def test_update_application_match_success(self):
        """Test successful pushing of match results."""
        cv_results = [
            {
                "cv_id": "1",
                "total_score": 0.82,
                "category": "strong",
                "rationale": "Good Python experience",
                "sim_embed": 0.9,
                "skill_coverage": 0.85,
                "must_have_penalty": 0.0,
                "llm_consistency": 0.75
            },
            {
                "cv_id": "2",
                "total_score": 0.65,
                "category": "moderate",
                "rationale": "Some relevant experience",
                "sim_embed": 0.7,
                "skill_coverage": 0.6,
                "must_have_penalty": 0.1,
                "llm_consistency": 0.65
            }
        ]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "updated": 2}
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)
            
            result = await update_application_match("123", cv_results)
            
            assert result["status"] == "success"
            assert result["updated"] == 2
            mock_instance.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_application_match_forbidden(self):
        """Test handling of 403 Forbidden response."""
        cv_results = [{"cv_id": "1", "total_score": 0.82}]
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)
            
            result = await update_application_match("123", cv_results)
            
            assert result["error"] == "Access forbidden"
    
    @pytest.mark.asyncio
    async def test_update_application_match_connection_error(self):
        """Test handling of connection errors."""
        cv_results = [{"cv_id": "1", "total_score": 0.82}]
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            
            result = await update_application_match("123", cv_results)
            
            assert "Connection failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_update_application_match_general_error(self):
        """Test handling of general exceptions."""
        cv_results = [{"cv_id": "1", "total_score": 0.82}]
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(side_effect=Exception("Unexpected error"))
            
            result = await update_application_match("123", cv_results)
            
            assert "Failed to push results" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])