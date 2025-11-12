"""
Tests for orchestrator.py

This test suite covers the orchestration logic including session creation,
CV processing, AI agent integration, and database operations.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup
def import_modules():
    from app.services.orchestrator import create_middleware_session, process_session
    from app.models.models import MiddlewareSession
    from app.services.db import AsyncSessionLocal
    return create_middleware_session, process_session, MiddlewareSession, AsyncSessionLocal

create_middleware_session, process_session, MiddlewareSession, AsyncSessionLocal = import_modules()


class TestCreateMiddlewareSession:
    """Test the create_middleware_session function."""
    
    @pytest.mark.asyncio
    async def test_create_session_success(self):
        """Test successful session creation."""
        # Mock database session
        mock_db_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_commit = AsyncMock()
        mock_db_session.execute = mock_execute
        mock_db_session.commit = mock_commit
        
        # Test data
        jd_id = "123"
        cv_ids = ["cv_001", "cv_002", "cv_003"]
        
        # Execute function
        result = await create_middleware_session(mock_db_session, jd_id, cv_ids)
        
        # Verify result
        assert "session_id" in result
        assert isinstance(result["session_id"], str)
        assert len(result["session_id"]) == 36  # UUID length
        
        # Verify database operations
        mock_execute.assert_called_once()
        mock_commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_session_with_empty_cv_ids(self):
        """Test session creation with empty CV list."""
        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()
        
        result = await create_middleware_session(mock_db_session, "456", [])
        
        assert "session_id" in result
        mock_db_session.execute.assert_called_once()
        mock_db_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_session_database_error(self):
        """Test handling of database errors during session creation."""
        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("Database error"))
        
        with pytest.raises(Exception, match="Database error"):
            await create_middleware_session(mock_db_session, "789", ["cv_001"])


class TestProcessSession:
    """Test the process_session function."""
    
    @pytest.mark.asyncio
    async def test_process_session_success(self):
        """Test successful session processing."""
        session_id = str(uuid.uuid4())
        
        # Mock database session and middleware session
        mock_db_session = AsyncMock()
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = []
        
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        
        # Mock job portal responses
        mock_jd_response = {
            "job": {
                "title": "Software Engineer",
                "description": "Develop software applications"
            },
            "skills": ["Python", "FastAPI"],
            "responsibilities": ["Code development", "Testing"]
        }
        
        mock_applications = [
            {
                "id": 1,
                "resume": "https://example.com/resume1.pdf",
                "firstname": "John",
                "lastname": "Doe"
            },
            {
                "id": 2,
                "resume": "https://example.com/resume2.pdf",
                "firstname": "Jane",
                "lastname": "Smith"
            }
        ]
        
        # Mock AI agent response
        mock_ai_response = {
            "session_id": "ai_session_123",
            "status": "success"
        }
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs, \
             patch('app.utils.utils.download_and_base64', new_callable=AsyncMock) as mock_download, \
             patch('app.services.ai_agent_client.start_session_on_ai', new_callable=AsyncMock) as mock_ai_start:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            mock_download.return_value = "base64_encoded_content"
            mock_ai_start.return_value = mock_ai_response
            
            # Execute function
            result = await process_session(session_id, mock_db_session)
            
            # Verify result
            assert "ai_response" in result
            assert result["ai_response"]["session_id"] == "ai_session_123"
            
            # Verify external calls
            mock_fetch_jd.assert_called_once_with(123)
            mock_fetch_cvs.assert_called_once_with(123)
            assert mock_download.call_count == 2  # Two CVs downloaded
            mock_ai_start.assert_called_once()
            
            # Verify AI payload structure
            ai_call_args = mock_ai_start.call_args[0][0]
            assert ai_call_args["session_id"] == session_id
            assert len(ai_call_args["job_descriptions"]) == 1
            assert len(ai_call_args["cvs"]) == 2
            assert ai_call_args["cvs"][0]["cv_id"] == "1"
            assert ai_call_args["cvs"][0]["filename"] == "John_Doe.pdf"
    
    @pytest.mark.asyncio
    async def test_process_session_not_found(self):
        """Test processing of non-existent session."""
        session_id = str(uuid.uuid4())
        
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        with pytest.raises(ValueError, match="session not found"):
            await process_session(session_id, mock_db_session)
    
    @pytest.mark.asyncio
    async def test_process_session_no_new_cvs(self):
        """Test processing when no new CVs are available."""
        session_id = str(uuid.uuid4())
        
        # Mock middleware session with existing CV IDs
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = ["1", "2"]  # CVs already processed
        
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        
        # Mock job portal responses - same CVs as already processed
        mock_jd_response = {"job": {"title": "Test", "description": "Test"}}
        mock_applications = [
            {"id": 1, "resume": "https://example.com/resume1.pdf"},
            {"id": 2, "resume": "https://example.com/resume2.pdf"}
        ]
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            
            result = await process_session(session_id, mock_db_session)
            
            assert result["status"] == "no_new_cvs"
    
    @pytest.mark.asyncio
    async def test_process_session_cvs_without_resume(self):
        """Test processing CVs that don't have resume URLs."""
        session_id = str(uuid.uuid4())
        
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = []
        
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        
        # Mock applications without resume URLs
        mock_jd_response = {"job": {"title": "Test", "description": "Test"}}
        mock_applications = [
            {"id": 1, "resume": None},  # No resume URL
            {"id": 2},  # Missing resume field
            {"id": 3, "resume": ""}  # Empty resume URL
        ]
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            
            result = await process_session(session_id, mock_db_session)
            
            assert result["status"] == "no_new_cvs"
    
    @pytest.mark.asyncio
    async def test_process_session_download_error(self):
        """Test handling of resume download errors."""
        session_id = str(uuid.uuid4())
        
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = []
        
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        
        mock_jd_response = {"job": {"title": "Test", "description": "Test"}}
        mock_applications = [{"id": 1, "resume": "https://invalid-url.com/resume.pdf"}]
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs, \
             patch('app.utils.utils.download_and_base64', new_callable=AsyncMock) as mock_download:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            mock_download.side_effect = Exception("Download failed")
            
            with pytest.raises(Exception, match="Download failed"):
                await process_session(session_id, mock_db_session)
    
    @pytest.mark.asyncio
    async def test_process_session_ai_agent_error(self):
        """Test handling of AI agent communication errors."""
        session_id = str(uuid.uuid4())

        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = []

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        mock_db_session.commit = AsyncMock()

        mock_jd_response = {"job": {"title": "Test", "description": "Test"}}
        mock_applications = [{"id": 1, "resume": "https://example.com/resume.pdf", "firstname": "Test", "lastname": "User"}]
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs, \
             patch('app.utils.utils.download_and_base64', new_callable=AsyncMock) as mock_download, \
             patch('app.services.ai_agent_client.start_session_on_ai', new_callable=AsyncMock) as mock_ai_start:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            mock_download.return_value = "base64_content"
            mock_ai_start.side_effect = Exception("AI agent error")
            
            with pytest.raises(Exception, match="AI agent error"):
                await process_session(session_id, mock_db_session)
    
    @pytest.mark.asyncio
    async def test_process_session_filename_generation(self):
        """Test filename generation for CVs."""
        session_id = str(uuid.uuid4())
        
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = "123"
        mock_middleware_session.cv_ids = []
        
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        mock_db_session.commit = AsyncMock()
        
        mock_jd_response = {"job": {"title": "Test", "description": "Test"}}
        mock_applications = [
            {
                "id": 1,
                "resume": "https://example.com/resume1.pdf",
                "firstname": "John",
                "lastname": "Doe"
            },
            {
                "id": 2,
                "resume": "https://example.com/resume2.pdf",
                "firstname": None,  # No firstname
                "lastname": "Smith"
            },
            {
                "id": 3,
                "resume": "https://example.com/resume3.pdf"
                # No name fields
            }
        ]
        
        mock_ai_response = {"session_id": "ai_123"}
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs, \
             patch('app.utils.utils.download_and_base64', new_callable=AsyncMock) as mock_download, \
             patch('app.services.ai_agent_client.start_session_on_ai', new_callable=AsyncMock) as mock_ai_start:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            mock_download.return_value = "base64_content"
            mock_ai_start.return_value = mock_ai_response
            
            await process_session(session_id, mock_db_session)
            
            # Check the AI payload for filename generation
            ai_call_args = mock_ai_start.call_args[0][0]
            cvs = ai_call_args["cvs"]
            
            assert len(cvs) == 3
            assert cvs[0]["filename"] == "John_Doe.pdf"
            assert cvs[1]["filename"] == "cv_2.pdf"  # Fallback when no firstname
            assert cvs[2]["filename"] == "cv_3.pdf"  # Fallback when no names


class TestOrchestratorIntegration:
    """Integration tests for orchestrator functions."""
    
    @pytest.mark.asyncio
    async def test_full_session_workflow(self):
        """Test the complete session workflow from creation to processing."""
        # This would be an integration test that requires a test database
        # For now, we'll use mocks but structure it like an integration test
        
        jd_id = "456"
        cv_ids = ["cv_001", "cv_002"]
        
        # Mock database operations
        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()
        
        # Test session creation
        session_result = await create_middleware_session(mock_db_session, jd_id, cv_ids)
        session_id = session_result["session_id"]
        
        # Mock middleware session for processing
        mock_middleware_session = MagicMock()
        mock_middleware_session.session_id = session_id
        mock_middleware_session.jd_id = jd_id
        mock_middleware_session.cv_ids = cv_ids
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_middleware_session
        mock_db_session.execute.return_value = mock_result
        
        # Mock external service responses
        mock_jd_response = {"job": {"title": "Test Job", "description": "Test Description"}}
        mock_applications = [
            {"id": 999, "resume": "https://example.com/new_resume.pdf", "firstname": "New", "lastname": "Candidate"}
        ]
        mock_ai_response = {"session_id": "ai_session_999", "status": "started"}
        
        with patch('app.services.job_portal_client.fetch_jd', new_callable=AsyncMock) as mock_fetch_jd, \
             patch('app.services.job_portal_client.fetch_cvs_for_jd', new_callable=AsyncMock) as mock_fetch_cvs, \
             patch('app.utils.utils.download_and_base64', new_callable=AsyncMock) as mock_download, \
             patch('app.services.ai_agent_client.start_session_on_ai', new_callable=AsyncMock) as mock_ai_start:
            
            mock_fetch_jd.return_value = mock_jd_response
            mock_fetch_cvs.return_value = mock_applications
            mock_download.return_value = "new_cv_base64_content"
            mock_ai_start.return_value = mock_ai_response
            
            # Test session processing
            process_result = await process_session(session_id, mock_db_session)
            
            # Verify the workflow
            assert process_result["ai_response"]["session_id"] == "ai_session_999"
            
            # Verify all external services were called
            mock_fetch_jd.assert_called_once()
            mock_fetch_cvs.assert_called_once()
            mock_download.assert_called_once()
            mock_ai_start.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])