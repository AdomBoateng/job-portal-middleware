"""
Tests for AI Agent Client service.

This module tests the AI Agent Client which handles communication with the AI agent,
particularly the enhanced fetch_report function that supports the new match report format.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestAIAgentClient:
    """Test AI Agent Client service."""

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_new_format_array(self, mock_client_class):
        """Test fetch_report with new array format."""
        from app.services.ai_agent_client import fetch_report
        
        # Mock httpx client
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with new format (array of reports)
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "match_report_id": "rep_1_1759481689",
                "session_id": "test-session-2025-10-02",
                "jd_id": "1",
                "summary": "AI match for JD 1: 2 CVs evaluated.",
                "match_results": [
                    {
                        "jd_id": "1",
                        "cv_id": "1",
                        "category": "REJECT",
                        "total_score": 0.2425,
                        "sim_embed": 0,
                        "skill_coverage": 0.6,
                        "must_have_penalty": 0.4,
                        "llm_consistency": 0.75,
                        "rationale": "CV mentions Python but lacks front-end experience"
                    }
                ],
                "created_at": "2025-10-03T08:54:49.805000"
            }
        ]
        mock_client.get.return_value = mock_response
        
        result = await fetch_report("test-session", "1")
        
        # Should return processed format
        assert result["status"] == "completed"
        assert result["match_report_id"] == "rep_1_1759481689"
        assert result["summary"] == "AI match for JD 1: 2 CVs evaluated."
        assert len(result["match_results"]) == 1
        assert result["match_results"][0]["category"] == "REJECT"
        assert result["created_at"] == "2025-10-03T08:54:49.805000"
        assert "reports" in result
        assert len(result["reports"]) == 1

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_old_format_with_status(self, mock_client_class):
        """Test fetch_report with old format that has status."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with old format
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "completed",
            "match_results": [
                {
                    "cv_id": "1",
                    "total_score": 0.85,
                    "category": "strong",
                    "rationale": "Excellent match"
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        result = await fetch_report("test-session", "1")
        
        # Should return as-is for old format
        assert result["status"] == "completed"
        assert len(result["match_results"]) == 1
        assert result["match_results"][0]["category"] == "strong"

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_single_report_without_status(self, mock_client_class):
        """Test fetch_report with single report without status wrapper."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with single report (no status)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "match_report_id": "rep_single_123",
            "jd_id": "2",
            "summary": "Single report test",
            "match_results": [
                {
                    "jd_id": "2",
                    "cv_id": "2",
                    "category": "ACCEPT",
                    "total_score": 0.8,
                    "rationale": "Good match"
                }
            ],
            "created_at": "2025-10-03T09:00:00.000000"
        }
        mock_client.get.return_value = mock_response
        
        result = await fetch_report("test-session", "2")
        
        # Should wrap in status format
        assert result["status"] == "completed"
        assert result["match_report_id"] == "rep_single_123"
        assert result["summary"] == "Single report test"
        assert len(result["match_results"]) == 1
        assert result["match_results"][0]["category"] == "ACCEPT"

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_empty_response(self, mock_client_class):
        """Test fetch_report with empty or unexpected response."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock empty response
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response
        
        result = await fetch_report("test-session", "1")
        
        # Should return processing status for empty response
        assert result["status"] == "processing"
        assert result["match_results"] == []

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_multiple_reports_takes_latest(self, mock_client_class):
        """Test fetch_report with multiple reports returns the latest one."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with multiple reports
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "match_report_id": "rep_1_old",
                "session_id": "test-session",
                "jd_id": "1",
                "summary": "Old report",
                "match_results": [],
                "created_at": "2025-10-03T08:00:00.000000"
            },
            {
                "match_report_id": "rep_1_latest",
                "session_id": "test-session",
                "jd_id": "1",
                "summary": "Latest report",
                "match_results": [
                    {
                        "jd_id": "1",
                        "cv_id": "1",
                        "category": "ACCEPT",
                        "total_score": 0.9,
                        "rationale": "Latest evaluation"
                    }
                ],
                "created_at": "2025-10-03T09:00:00.000000"
            }
        ]
        mock_client.get.return_value = mock_response
        
        result = await fetch_report("test-session", "1")
        
        # Should return the latest report (last in array)
        assert result["status"] == "completed"
        assert result["match_report_id"] == "rep_1_latest"
        assert result["summary"] == "Latest report"
        assert len(result["match_results"]) == 1
        assert result["match_results"][0]["rationale"] == "Latest evaluation"
        assert len(result["reports"]) == 2  # Should include all reports

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_fetch_report_http_error(self, mock_client_class):
        """Test fetch_report handling HTTP errors."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock HTTP error
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "404 Not Found", 
            request=MagicMock(), 
            response=MagicMock()
        )
        
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_report("test-session", "1")

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_start_session_on_ai(self, mock_client_class):
        """Test start_session_on_ai function."""
        from app.services.ai_agent_client import start_session_on_ai
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "session_id": "ai-session-123",
            "status": "created"
        }
        mock_client.post.return_value = mock_response
        
        session_payload = {
            "session_id": "middleware-session",
            "job_descriptions": [],
            "cvs": []
        }
        
        result = await start_session_on_ai(session_payload)
        
        assert result["session_id"] == "ai-session-123"
        assert result["status"] == "created"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_add_cvs_to_session_with_jd(self, mock_client_class):
        """Test add_cvs_to_session_with_jd function."""
        from app.services.ai_agent_client import add_cvs_to_session_with_jd
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "cvs_added": 2
        }
        mock_client.post.return_value = mock_response
        
        cvs_payload = {
            "cvs": [
                {
                    "cv_id": "1",
                    "jd_id": "1",
                    "filename": "resume1.pdf",
                    "base64_content": "base64content1"
                }
            ]
        }
        
        result = await add_cvs_to_session_with_jd("ai-session-123", "1", cvs_payload)
        
        assert result["status"] == "success"
        assert result["cvs_added"] == 2
        mock_client.post.assert_called_once()


class TestAIAgentClientFormatCompatibility:
    """Test AI Agent Client backwards compatibility."""

    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.httpx.AsyncClient')
    async def test_backwards_compatibility_old_and_new_formats(self, mock_client_class):
        """Test that both old and new formats work correctly."""
        from app.services.ai_agent_client import fetch_report
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Test cases for different response formats
        test_cases = [
            # Old format with status
            {
                "response": {
                    "status": "completed",
                    "match_results": [{"cv_id": "1", "category": "strong"}]
                },
                "expected_status": "completed",
                "expected_match_results_count": 1
            },
            # New format array
            {
                "response": [
                    {
                        "match_report_id": "rep_123",
                        "match_results": [{"cv_id": "1", "category": "REJECT"}],
                        "summary": "Test"
                    }
                ],
                "expected_status": "completed",
                "expected_match_results_count": 1
            },
            # Single report without status
            {
                "response": {
                    "match_report_id": "rep_456",
                    "match_results": [{"cv_id": "1", "category": "ACCEPT"}]
                },
                "expected_status": "completed",
                "expected_match_results_count": 1
            },
            # Empty response
            {
                "response": [],
                "expected_status": "processing",
                "expected_match_results_count": 0
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            mock_response = MagicMock()
            mock_response.json.return_value = test_case["response"]
            mock_client.get.return_value = mock_response
            
            result = await fetch_report(f"session-{i}", "1")
            
            assert result["status"] == test_case["expected_status"], f"Test case {i} failed"
            assert len(result["match_results"]) == test_case["expected_match_results_count"], f"Test case {i} failed"