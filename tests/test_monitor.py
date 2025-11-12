"""
Comprehensive tests for monitor.py module.

This module tests the monitoring service that:
- Discovers jobs and creates middleware sessions
- Processes job applications 
- Checks processing sessions for completion
- Retries failed sessions
- Handles CV updates to existing sessions
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.monitor import (
    monitor_loop,
    discover_and_process_jobs,
    process_job_applications,
    get_active_session_for_job,
    add_cvs_to_existing_session,
    check_processing_sessions,
    check_session_completion,
    retry_failed_sessions,
    update_session_status
)


class TestMonitorLoop:
    """Test the main monitoring loop."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.asyncio.sleep')
    @patch('app.services.monitor.retry_failed_sessions')
    @patch('app.services.monitor.check_processing_sessions')
    @patch('app.services.monitor.discover_and_process_jobs')
    async def test_monitor_loop_iteration(self, mock_discover, mock_check, mock_retry, mock_sleep):
        """Test single iteration of monitor loop."""
        # Mock all functions to be async
        mock_discover.return_value = None
        mock_check.return_value = None
        mock_retry.return_value = None
        mock_sleep.side_effect = KeyboardInterrupt  # Stop after one iteration
        
        with pytest.raises(KeyboardInterrupt):
            await monitor_loop()
            
        mock_discover.assert_called_once()
        mock_check.assert_called_once()
        mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.asyncio.sleep')
    @patch('app.services.monitor.retry_failed_sessions')
    @patch('app.services.monitor.check_processing_sessions')
    @patch('app.services.monitor.discover_and_process_jobs')
    async def test_monitor_loop_error_handling(self, mock_discover, mock_check, mock_retry, mock_sleep):
        """Test monitor loop handles errors gracefully."""
        # First iteration: discover fails, so check and retry won't be called
        # Second iteration: all succeed, then stop
        mock_discover.side_effect = [Exception("Test error"), None]
        mock_check.return_value = None
        mock_retry.return_value = None
        mock_sleep.side_effect = [None, KeyboardInterrupt]  # Run twice then stop
        
        with pytest.raises(KeyboardInterrupt):
            await monitor_loop()
            
        # Should continue despite error
        assert mock_discover.call_count == 2
        # These only get called in the second iteration when discover succeeds
        assert mock_check.call_count == 1
        assert mock_retry.call_count == 1


class TestDiscoverAndProcessJobs:
    """Test job discovery and processing logic."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    @patch('app.services.monitor.process_job_applications')
    @patch('app.services.job_portal_client.fetch_all_job_ids')
    async def test_discover_jobs_success(self, mock_fetch_jobs, mock_process, mock_session):
        """Test successful job discovery and processing."""
        # Setup
        mock_job_ids = [123, 456, 789]
        mock_fetch_jobs.return_value = mock_job_ids
        mock_process.return_value = None
        
        mock_db_session = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db_session
        
        # Execute
        await discover_and_process_jobs()
        
        # Verify
        mock_fetch_jobs.assert_called_once()
        assert mock_process.call_count == len(mock_job_ids)
        for job_id in mock_job_ids:
            mock_process.assert_any_call(mock_db_session, job_id)
    
    @pytest.mark.asyncio
    @patch('app.services.job_portal_client.fetch_all_job_ids')
    async def test_discover_jobs_no_jobs_found(self, mock_fetch_jobs):
        """Test when no jobs are found."""
        mock_fetch_jobs.return_value = []
        
        # Should not raise an error
        await discover_and_process_jobs()
        
        mock_fetch_jobs.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.job_portal_client.fetch_all_job_ids')
    async def test_discover_jobs_api_error(self, mock_fetch_jobs):
        """Test handling of job portal API errors."""
        mock_fetch_jobs.side_effect = Exception("API Error")
        
        # Should not raise an error but log it
        await discover_and_process_jobs()
        
        mock_fetch_jobs.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    @patch('app.services.monitor.process_job_applications')
    @patch('app.services.job_portal_client.fetch_all_job_ids')
    async def test_discover_jobs_individual_job_error(self, mock_fetch_jobs, mock_process, mock_session):
        """Test handling of individual job processing errors."""
        mock_fetch_jobs.return_value = [123, 456]
        mock_process.side_effect = [Exception("Job error"), None]
        
        mock_db_session = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db_session
        
        # Should continue processing other jobs despite error
        await discover_and_process_jobs()
        
        assert mock_process.call_count == 2


class TestProcessJobApplications:
    """Test processing applications for specific jobs."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.process_session')
    @patch('app.services.monitor.create_middleware_session')
    @patch('app.services.monitor.get_active_session_for_job')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_process_new_job_success(self, mock_fetch_cvs, mock_get_session, mock_create, mock_process):
        """Test processing a new job with no existing session."""
        job_id = 123
        mock_db = AsyncMock()
        
        # Setup mock data
        mock_applications = [
            {"id": 1, "firstname": "John", "lastname": "Doe"},
            {"id": 2, "firstname": "Jane", "lastname": "Smith"}
        ]
        mock_fetch_cvs.return_value = mock_applications
        mock_get_session.return_value = None  # No existing session
        mock_create.return_value = {"session_id": "test-session-id"}
        mock_process.return_value = None
        
        # Execute
        await process_job_applications(mock_db, job_id)
        
        # Verify
        mock_fetch_cvs.assert_called_once_with(job_id)
        mock_get_session.assert_called_once_with(mock_db, str(job_id))
        mock_create.assert_called_once_with(mock_db, str(job_id), ["1", "2"])
        mock_process.assert_called_once_with("test-session-id", mock_db)
    
    @pytest.mark.asyncio
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_process_job_no_applications(self, mock_fetch_cvs):
        """Test processing job with no applications."""
        job_id = 123
        mock_db = AsyncMock()
        mock_fetch_cvs.return_value = []
        
        await process_job_applications(mock_db, job_id)
        
        mock_fetch_cvs.assert_called_once_with(job_id)
        # Should return early without further processing
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.add_cvs_to_existing_session')
    @patch('app.services.monitor.get_active_session_for_job')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_process_job_with_existing_session_new_cvs(self, mock_fetch_cvs, mock_get_session, mock_add_cvs):
        """Test processing job with existing session and new CVs."""
        job_id = 123
        mock_db = AsyncMock()
        
        # Setup existing session
        mock_session = MagicMock()
        mock_session.session_id = "existing-session"
        mock_session.cv_ids = ["1", "2"]
        
        mock_applications = [
            {"id": 1, "firstname": "John"},  # Existing
            {"id": 2, "firstname": "Jane"},  # Existing
            {"id": 3, "firstname": "Bob"}    # New
        ]
        
        mock_fetch_cvs.return_value = mock_applications
        mock_get_session.return_value = mock_session
        mock_add_cvs.return_value = None
        
        await process_job_applications(mock_db, job_id)
        
        mock_add_cvs.assert_called_once_with(mock_db, mock_session, ["3"])
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.get_active_session_for_job')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_process_job_with_existing_session_no_new_cvs(self, mock_fetch_cvs, mock_get_session):
        """Test processing job with existing session but no new CVs."""
        job_id = 123
        mock_db = AsyncMock()
        
        mock_session = MagicMock()
        mock_session.cv_ids = ["1", "2"]
        
        mock_applications = [
            {"id": 1, "firstname": "John"},
            {"id": 2, "firstname": "Jane"}
        ]
        
        mock_fetch_cvs.return_value = mock_applications
        mock_get_session.return_value = mock_session
        
        await process_job_applications(mock_db, job_id)
        
        # Should not create new session or add CVs
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.update_session_status')
    @patch('app.services.monitor.process_session')
    @patch('app.services.monitor.create_middleware_session')
    @patch('app.services.monitor.get_active_session_for_job')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_process_job_processing_error(self, mock_fetch_cvs, mock_get_session, mock_create, mock_process, mock_update_status):
        """Test handling of processing errors."""
        job_id = 123
        mock_db = AsyncMock()
        
        mock_applications = [{"id": 1, "firstname": "John"}]
        mock_fetch_cvs.return_value = mock_applications
        mock_get_session.return_value = None
        mock_create.return_value = {"session_id": "test-session"}
        mock_process.side_effect = Exception("Processing error")
        mock_update_status.return_value = None
        
        await process_job_applications(mock_db, job_id)
        
        mock_update_status.assert_called_once_with(mock_db, "test-session", "failed")


class TestGetActiveSessionForJob:
    """Test retrieving active sessions for jobs."""
    
    @pytest.mark.asyncio
    async def test_get_active_session_found(self):
        """Test finding an active session."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result
        
        result = await get_active_session_for_job(mock_db, "123")
        
        assert result == mock_session
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_active_session_not_found(self):
        """Test when no active session exists."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await get_active_session_for_job(mock_db, "123")
        
        assert result is None


class TestAddCvsToExistingSession:
    """Test adding CVs to existing sessions."""
    
    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.add_cvs_to_session_with_jd')
    @patch('app.utils.utils.download_and_base64')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_add_cvs_with_ai_session(self, mock_fetch_cvs, mock_download, mock_ai_add):
        """Test adding CVs to session with AI session ID."""
        mock_db = AsyncMock()
        
        # Setup session
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.jd_id = "123"
        mock_session.ai_session_id = "ai-session-123"
        mock_session.cv_ids = ["1"]
        
        # Setup new applications
        new_cv_ids = ["2", "3"]
        mock_applications = [
            {"id": 2, "resume": "http://example.com/resume2.pdf", "firstname": "Jane", "lastname": "Doe"},
            {"id": 3, "resume": "http://example.com/resume3.pdf", "firstname": "Bob", "lastname": "Smith"}
        ]
        
        mock_fetch_cvs.return_value = mock_applications
        mock_download.return_value = "base64_content"
        mock_ai_add.return_value = {"status": "success"}
        
        await add_cvs_to_existing_session(mock_db, mock_session, new_cv_ids)
        
        # Verify database update
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()
        
        # Verify AI agent call
        mock_ai_add.assert_called_once()
        call_args = mock_ai_add.call_args
        assert call_args[0][0] == "ai-session-123"
        assert call_args[0][1] == "123"
        cvs_payload = call_args[0][2]["cvs"]
        assert len(cvs_payload) == 2
    
    @pytest.mark.asyncio
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_add_cvs_without_ai_session(self, mock_fetch_cvs):
        """Test adding CVs to session without AI session ID."""
        mock_db = AsyncMock()
        
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.ai_session_id = None
        mock_session.cv_ids = ["1"]
        
        new_cv_ids = ["2"]
        mock_fetch_cvs.return_value = []
        
        await add_cvs_to_existing_session(mock_db, mock_session, new_cv_ids)
        
        # Should update database but not call AI agent
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.update_session_status')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    async def test_add_cvs_error_handling(self, mock_fetch_cvs, mock_update_status):
        """Test error handling when adding CVs."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        
        mock_fetch_cvs.side_effect = Exception("Fetch error")
        mock_update_status.return_value = None
        
        await add_cvs_to_existing_session(mock_db, mock_session, ["2"])
        
        mock_update_status.assert_called_once_with(mock_db, "test-session", "failed")


class TestCheckProcessingSessions:
    """Test checking processing sessions for completion."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.check_session_completion')
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_check_processing_sessions_success(self, mock_session_local, mock_check_completion):
        """Test checking processing sessions successfully."""
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        # Setup mock processing sessions
        mock_sessions = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_sessions
        mock_db.execute.return_value = mock_result
        
        mock_check_completion.return_value = None
        
        await check_processing_sessions()
        
        # Verify all sessions were checked
        assert mock_check_completion.call_count == len(mock_sessions)
        for session in mock_sessions:
            mock_check_completion.assert_any_call(mock_db, session)
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.check_session_completion')
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_check_processing_sessions_individual_error(self, mock_session_local, mock_check_completion):
        """Test handling individual session check errors."""
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        mock_sessions = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_sessions
        mock_db.execute.return_value = mock_result
        
        # First session fails, second succeeds
        mock_check_completion.side_effect = [Exception("Check error"), None]
        
        await check_processing_sessions()
        
        # Should check both sessions despite first error
        assert mock_check_completion.call_count == 2
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_check_processing_sessions_database_error(self, mock_session_local):
        """Test handling database connection errors."""
        mock_session_local.side_effect = Exception("Name or service not known")
        
        # Should not raise exception but log warning
        await check_processing_sessions()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_check_processing_sessions_other_database_error(self, mock_session_local):
        """Test handling other database errors."""
        mock_session_local.side_effect = Exception("Other database error")
        
        # Should not raise exception but log error
        await check_processing_sessions()


class TestCheckSessionCompletion:
    """Test checking individual session completion."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.store_match_report')
    @patch('app.services.monitor.update_session_status')
    @patch('app.services.job_portal_client.update_application_match')
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_completed_success(self, mock_fetch_report, mock_update_match, mock_update_status, mock_store_report):
        """Test handling completed session with new match report format."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.ai_session_id = "ai-session"
        mock_session.jd_id = "123"
        
        # Mock new format report with match_report_id
        mock_report = {
            "status": "completed",
            "match_report_id": "rep_1_1759481689",
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
        mock_fetch_report.return_value = mock_report
        mock_update_match.return_value = None
        mock_update_status.return_value = None
        mock_store_report.return_value = None
        
        await check_session_completion(mock_db, mock_session)
        
        mock_fetch_report.assert_called_once_with("ai-session", "123")
        mock_store_report.assert_called_once_with(mock_db, mock_report, "test-session")
        # Verify processed results are passed to job portal
        call_args = mock_update_match.call_args[0]
        assert call_args[0] == "123"
        processed_results = call_args[1]
        assert len(processed_results) == 1
        assert processed_results[0]["category"] == "weak"  # REJECT -> weak mapping
        mock_update_status.assert_called_once_with(mock_db, "test-session", "completed")
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.update_session_status')
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_failed(self, mock_fetch_report, mock_update_status):
        """Test handling failed session."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.ai_session_id = "ai-session"
        mock_session.jd_id = "123"
        
        mock_report = {"status": "failed", "error": "Processing failed"}
        mock_fetch_report.return_value = mock_report
        mock_update_status.return_value = None
        
        await check_session_completion(mock_db, mock_session)
        
        mock_update_status.assert_called_once_with(mock_db, "test-session", "failed")
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.store_match_report')
    @patch('app.services.monitor.update_session_status')
    @patch('app.services.job_portal_client.update_application_match')
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_completed_with_multiple_reports(self, mock_fetch_report, mock_update_match, mock_update_status, mock_store_report):
        """Test handling completed session with multiple reports format."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.ai_session_id = "ai-session"
        mock_session.jd_id = "123"
        
        # Mock new format with reports array
        mock_report = {
            "status": "completed",
            "match_report_id": "rep_1_1759481689",
            "summary": "AI match for JD 1: 2 CVs evaluated.",
            "match_results": [
                {
                    "jd_id": "1",
                    "cv_id": "1",
                    "category": "REJECT",
                    "total_score": 0.2425,
                    "rationale": "CV mentions Python but lacks required skills"
                }
            ],
            "created_at": "2025-10-03T08:54:49.805000",
            "reports": [
                {
                    "match_report_id": "rep_1_1759481689",
                    "session_id": "test-session-2025-10-02",
                    "jd_id": "1",
                    "summary": "AI match for JD 1: 2 CVs evaluated.",
                    "match_results": [
                        {"jd_id": "1", "cv_id": "1", "category": "REJECT", "total_score": 0.2425, "rationale": "Test"}
                    ],
                    "created_at": "2025-10-03T08:54:49.805000"
                }
            ]
        }
        mock_fetch_report.return_value = mock_report
        mock_update_match.return_value = None
        mock_update_status.return_value = None
        mock_store_report.return_value = None
        
        await check_session_completion(mock_db, mock_session)
        
        # Should store each individual report
        assert mock_store_report.call_count == 1  # One report in the reports array
        mock_update_status.assert_called_once_with(mock_db, "test-session", "completed")
    
    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_still_processing(self, mock_fetch_report):
        """Test handling session still in progress."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.ai_session_id = "ai-session"
        mock_session.jd_id = "123"
        
        mock_report = {"status": "processing"}
        mock_fetch_report.return_value = mock_report
        
        await check_session_completion(mock_db, mock_session)
        
        # Should update last_checked
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_report_not_found(self, mock_fetch_report):
        """Test handling when report is not found (404)."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        
        mock_fetch_report.side_effect = Exception("404 not found")
        
        # Should not raise exception
        await check_session_completion(mock_db, mock_session)
    
    @pytest.mark.asyncio
    @patch('app.services.ai_agent_client.fetch_report')
    async def test_session_unexpected_error(self, mock_fetch_report):
        """Test handling unexpected errors."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        
        mock_fetch_report.side_effect = Exception("Unexpected error")
        
        # Should not raise exception but log error
        await check_session_completion(mock_db, mock_session)


class TestRetryFailedSessions:
    """Test retrying failed sessions."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.process_session')
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_retry_failed_sessions_success(self, mock_session_local, mock_process):
        """Test successfully retrying failed sessions."""
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        # Setup mock failed sessions
        mock_sessions = [MagicMock(), MagicMock()]
        for i, session in enumerate(mock_sessions):
            session.session_id = f"failed-session-{i}"
            
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_sessions
        mock_db.execute.return_value = mock_result
        
        mock_process.return_value = None
        
        await retry_failed_sessions()
        
        # Verify all failed sessions were retried
        assert mock_process.call_count == len(mock_sessions)
        for session in mock_sessions:
            mock_process.assert_any_call(session.session_id, mock_db)
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.process_session')
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_retry_failed_sessions_individual_error(self, mock_session_local, mock_process):
        """Test handling individual retry errors."""
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        mock_sessions = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_sessions
        mock_db.execute.return_value = mock_result
        
        # First retry fails, second succeeds
        mock_process.side_effect = [Exception("Retry error"), None]
        
        await retry_failed_sessions()
        
        # Should attempt both retries despite first error
        assert mock_process.call_count == 2


class TestProcessMatchResultsForJobPortal:
    """Test processing match results from AI agent format to job portal format."""
    
    def test_process_reject_category(self):
        """Test mapping REJECT category to weak."""
        from app.services.monitor import process_match_results_for_job_portal
        
        match_results = [
            {
                "jd_id": "1",
                "cv_id": "1",
                "category": "REJECT",
                "total_score": 0.2425,
                "sim_embed": 0,
                "skill_coverage": 0.6,
                "must_have_penalty": 0.4,
                "llm_consistency": 0.75,
                "rationale": "CV mentions Python but lacks required skills"
            }
        ]
        
        processed = process_match_results_for_job_portal(match_results)
        
        assert len(processed) == 1
        assert processed[0]["category"] == "weak"
        assert processed[0]["cv_id"] == "1"
        assert processed[0]["total_score"] == 0.2425
        assert processed[0]["rationale"] == "CV mentions Python but lacks required skills"
        assert processed[0]["sim_embed"] == 0
        assert processed[0]["skill_coverage"] == 0.6
        assert processed[0]["must_have_penalty"] == 0.4
        assert processed[0]["llm_consistency"] == 0.75
    
    def test_process_accept_category(self):
        """Test mapping ACCEPT category to strong."""
        from app.services.monitor import process_match_results_for_job_portal
        
        match_results = [
            {
                "cv_id": "2",
                "category": "ACCEPT",
                "total_score": 0.85,
                "rationale": "Excellent match for all requirements"
            }
        ]
        
        processed = process_match_results_for_job_portal(match_results)
        
        assert len(processed) == 1
        assert processed[0]["category"] == "strong"
        assert processed[0]["cv_id"] == "2"
        assert processed[0]["total_score"] == 0.85
    
    def test_process_unknown_category_fallback(self):
        """Test fallback for unknown categories."""
        from app.services.monitor import process_match_results_for_job_portal
        
        match_results = [
            {
                "cv_id": "3",
                "category": "MAYBE",
                "total_score": 0.5,
                "rationale": "Uncertain match"
            }
        ]
        
        processed = process_match_results_for_job_portal(match_results)
        
        assert len(processed) == 1
        assert processed[0]["category"] == "maybe"  # Should keep original, lowercased
    
    def test_process_missing_optional_fields(self):
        """Test handling of missing optional fields."""
        from app.services.monitor import process_match_results_for_job_portal
        
        match_results = [
            {
                "cv_id": "4",
                "category": "REJECT",
                "total_score": 0.3,
                "rationale": "Basic requirements not met"
                # Missing optional fields
            }
        ]
        
        processed = process_match_results_for_job_portal(match_results)
        
        assert len(processed) == 1
        result = processed[0]
        assert result["cv_id"] == "4"
        assert result["category"] == "weak"
        assert result["total_score"] == 0.3
        # Optional fields should not be present
        assert "sim_embed" not in result
        assert "skill_coverage" not in result
        assert "must_have_penalty" not in result
        assert "llm_consistency" not in result
    
    def test_process_multiple_results(self):
        """Test processing multiple match results."""
        from app.services.monitor import process_match_results_for_job_portal
        
        match_results = [
            {
                "cv_id": "1",
                "category": "REJECT",
                "total_score": 0.2,
                "rationale": "Poor match"
            },
            {
                "cv_id": "2",
                "category": "ACCEPT",
                "total_score": 0.9,
                "rationale": "Excellent match"
            }
        ]
        
        processed = process_match_results_for_job_portal(match_results)
        
        assert len(processed) == 2
        assert processed[0]["category"] == "weak"
        assert processed[1]["category"] == "strong"


class TestStoreMatchReport:
    """Test storing match reports in the database."""
    
    @pytest.mark.asyncio
    async def test_store_report_missing_jd_id(self):
        """Test handling of report data without jd_id."""
        from app.services.monitor import store_match_report
        
        mock_db = AsyncMock()
        report_data = {
            "match_report_id": "rep_1_1759481689",
            # Missing jd_id
            "summary": "Test summary",
            "match_results": [{"cv_id": "1", "category": "REJECT"}],
        }
        
        await store_match_report(mock_db, report_data, "test-session")
        
        # Should not attempt to store due to missing jd_id
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_new_report_validates_required_fields(self):
        """Test that store_match_report validates required fields."""
        from app.services.monitor import store_match_report
        
        mock_db = AsyncMock()
        
        # Test with missing match_report_id
        report_data_no_id = {
            "jd_id": "1",
            "summary": "Test summary",
        }
        
        await store_match_report(mock_db, report_data_no_id, "test-session")
        mock_db.add.assert_not_called()
        
        # Test with missing jd_id
        report_data_no_jd = {
            "match_report_id": "rep_123",
            "summary": "Test summary",
        }
        
        await store_match_report(mock_db, report_data_no_jd, "test-session")
        mock_db.add.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.select')
    async def test_store_existing_report_skipped(self, mock_select):
        """Test skipping storage of existing match report."""
        from app.services.monitor import store_match_report
        
        mock_db = AsyncMock()
        mock_result = AsyncMock()
        mock_existing_report = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing_report  # Existing report
        mock_db.execute.return_value = mock_result
        
        # Mock the select statement
        mock_select_stmt = MagicMock()
        mock_select.return_value = mock_select_stmt
        mock_select_stmt.where.return_value = mock_select_stmt
        
        report_data = {
            "match_report_id": "rep_1_1759481689",
            "jd_id": "1",
            "summary": "Test summary",
            "match_results": [],
            "created_at": "2025-10-03T08:54:49.805000"
        }
        
        await store_match_report(mock_db, report_data, "test-session")
        
        # Should not add or commit
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_retry_failed_sessions_database_error(self, mock_session_local):
        """Test handling database connection errors during retry."""
        mock_session_local.side_effect = Exception("Name or service not known")
        
        # Should not raise exception but log warning
        await retry_failed_sessions()
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    async def test_retry_failed_sessions_other_database_error(self, mock_session_local):
        """Test handling other database errors during retry."""
        mock_session_local.side_effect = Exception("Other database error")
        
        # Should not raise exception but log error
        await retry_failed_sessions()


class TestUpdateSessionStatus:
    """Test updating session status."""
    
    @pytest.mark.asyncio
    async def test_update_session_status_success(self):
        """Test successfully updating session status."""
        mock_db = AsyncMock()
        session_id = "test-session"
        status = "completed"
        
        await update_session_status(mock_db, session_id, status)
        
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


class TestMonitorIntegration:
    """Integration tests for monitor functionality."""
    
    @pytest.mark.asyncio
    @patch('app.services.monitor.AsyncSessionLocal')
    @patch('app.services.monitor.process_session')
    @patch('app.services.monitor.create_middleware_session')
    @patch('app.services.job_portal_client.fetch_cvs_for_jd')
    @patch('app.services.job_portal_client.fetch_all_job_ids')
    async def test_full_monitoring_workflow(self, mock_fetch_jobs, mock_fetch_cvs, mock_create, mock_process, mock_session_local):
        """Test complete monitoring workflow from job discovery to processing."""
        # Setup mocks
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        mock_fetch_jobs.return_value = [123]
        mock_fetch_cvs.return_value = [
            {"id": 1, "firstname": "John", "lastname": "Doe"},
            {"id": 2, "firstname": "Jane", "lastname": "Smith"}
        ]
        
        # No existing session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        mock_create.return_value = {"session_id": "new-session"}
        mock_process.return_value = None
        
        # Execute discovery
        await discover_and_process_jobs()
        
        # Verify workflow
        mock_fetch_jobs.assert_called_once()
        mock_fetch_cvs.assert_called_once_with(123)
        mock_create.assert_called_once_with(mock_db, "123", ["1", "2"])
        mock_process.assert_called_once_with("new-session", mock_db)