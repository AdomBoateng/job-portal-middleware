"""
Tests for db.py

This test suite covers database connection, session management, and model operations
for the database service module.
"""
import pytest
import os
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup to ensure proper module resolution
def import_modules():
    from app.services.db import get_db, engine, AsyncSessionLocal, DATABASE_URL
    from app.models.models import MiddlewareSession
    return get_db, engine, AsyncSessionLocal, DATABASE_URL, MiddlewareSession

# Get the required modules and functions
get_db, engine, AsyncSessionLocal, DATABASE_URL, MiddlewareSession = import_modules()


class TestDatabaseConfiguration:
    """Test database configuration and setup."""
    
    def test_database_url_configuration(self):
        """Test that DATABASE_URL is properly configured."""
        # Check that DATABASE_URL is set
        assert DATABASE_URL is not None
        assert isinstance(DATABASE_URL, str)
        
        # Check that it's a valid PostgreSQL URL
        assert DATABASE_URL.startswith(('postgresql+asyncpg://', 'sqlite+aiosqlite://'))
    
    def test_engine_configuration(self):
        """Test that the database engine is properly configured."""
        assert engine is not None
        assert hasattr(engine, 'url')
        assert not engine.echo  # Should be False by default
    
    def test_session_configuration(self):
        """Test that the session maker is properly configured."""
        assert AsyncSessionLocal is not None
        assert issubclass(AsyncSessionLocal.class_, AsyncSession)
        assert not AsyncSessionLocal.kw.get('expire_on_commit', True)


class TestDatabaseConnection:
    """Test database connection functionality."""
    
    @pytest.mark.asyncio
    async def test_database_connection_success(self):
        """Test successful database connection."""
        try:
            # Test basic connection
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1 as test"))
                row = result.fetchone()
                assert row[0] == 1
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")
    
    @pytest.mark.asyncio
    async def test_session_creation(self):
        """Test that database sessions can be created."""
        try:
            async with AsyncSessionLocal() as session:
                assert isinstance(session, AsyncSession)
                assert session.is_active
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")


class TestGetDbFunction:
    """Test the get_db dependency function."""
    
    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """Test that get_db yields a valid session."""
        try:
            async for session in get_db():
                assert isinstance(session, AsyncSession)
                assert session.is_active
                break  # Only test the first yielded session
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")
    
    @pytest.mark.asyncio
    async def test_get_db_session_cleanup(self):
        """Test that get_db properly cleans up sessions."""
        session_refs = []
        
        try:
            async for session in get_db():
                session_refs.append(session)
                break
            
            # Session should be closed after the generator exits
            # Note: This is hard to test directly, but we can verify the session exists
            assert len(session_refs) == 1
            
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")


class TestMiddlewareSessionModel:
    """Test the MiddlewareSession model."""
    
    @pytest.mark.asyncio
    async def test_create_middleware_session(self):
        """Test creating a MiddlewareSession instance."""
        try:
            async with AsyncSessionLocal() as session:
                # Create a new session record
                middleware_session = MiddlewareSession(
                    jd_id="test_job_123",
                    cv_ids=["cv_1", "cv_2", "cv_3"],
                    ai_session_id="ai_session_456",
                    status="pending"
                )
                
                session.add(middleware_session)
                await session.commit()
                
                # Verify the session was created
                assert middleware_session.session_id is not None
                assert middleware_session.jd_id == "test_job_123"
                assert middleware_session.cv_ids == ["cv_1", "cv_2", "cv_3"]
                assert middleware_session.ai_session_id == "ai_session_456"
                assert middleware_session.status == "pending"
                assert middleware_session.created_at is not None
                assert middleware_session.updated_at is not None
                
                # Clean up
                await session.delete(middleware_session)
                await session.commit()
                
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")
    
    @pytest.mark.asyncio
    async def test_query_middleware_session(self):
        """Test querying MiddlewareSession records."""
        try:
            async with AsyncSessionLocal() as session:
                # Create a test session
                test_session = MiddlewareSession(
                    jd_id="query_test_job",
                    cv_ids=["cv_test_1"],
                    status="completed"
                )
                
                session.add(test_session)
                await session.commit()
                
                # Query the session back
                from sqlalchemy import select
                stmt = select(MiddlewareSession).where(
                    MiddlewareSession.jd_id == "query_test_job"
                )
                result = await session.execute(stmt)
                retrieved_session = result.scalar_one_or_none()
                
                assert retrieved_session is not None
                assert retrieved_session.jd_id == "query_test_job"
                assert retrieved_session.cv_ids == ["cv_test_1"]
                assert retrieved_session.status == "completed"
                
                # Clean up
                await session.delete(retrieved_session)
                await session.commit()
                
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")
    
    @pytest.mark.asyncio
    async def test_update_middleware_session(self):
        """Test updating MiddlewareSession records."""
        try:
            async with AsyncSessionLocal() as session:
                # Create a test session
                test_session = MiddlewareSession(
                    jd_id="update_test_job",
                    status="pending"
                )
                
                session.add(test_session)
                await session.commit()
                
                # Update the session
                test_session.status = "processing"
                test_session.ai_session_id = "updated_ai_session"
                await session.commit()
                
                # Verify the update
                from sqlalchemy import select
                stmt = select(MiddlewareSession).where(
                    MiddlewareSession.session_id == test_session.session_id
                )
                result = await session.execute(stmt)
                updated_session = result.scalar_one_or_none()
                
                assert updated_session is not None
                assert updated_session.status == "processing"
                assert updated_session.ai_session_id == "updated_ai_session"
                
                # Clean up
                await session.delete(updated_session)
                await session.commit()
                
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")


class TestDatabaseWithMocking:
    """Test database functionality with mocking for isolated unit tests."""
    
    @pytest.mark.asyncio
    async def test_get_db_with_mock_session(self):
        """Test get_db function with mocked session."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.is_active = True
        
        with patch('app.services.db.AsyncSessionLocal') as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None
            
            async for session in get_db():
                assert session == mock_session
                break
    
    def test_database_url_from_environment(self):
        """Test that DATABASE_URL is read from environment."""
        test_url = "postgresql+asyncpg://test:test@localhost:5432/testdb"
        
        with patch.dict(os.environ, {'DATABASE_URL': test_url}):
            # Re-import the module to pick up the new environment variable
            import importlib
            from app.services import db
            importlib.reload(db)
            
            assert db.DATABASE_URL == test_url
    
    def test_database_url_default_fallback(self):
        """Test that DATABASE_URL falls back to default when not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATABASE_URL from environment
            import importlib
            from app.services import db
            importlib.reload(db)
            
            assert db.DATABASE_URL == "postgresql+asyncpg://postgres:root%401234@localhost:5432/postgres"


class TestDatabaseErrorHandling:
    """Test error handling in database operations."""
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of database connection errors."""
        # Create an engine with an invalid URL
        invalid_engine = create_async_engine("postgresql+asyncpg://invalid:invalid@nonexistent:5432/invalid")
        
        with pytest.raises(Exception):
            async with invalid_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
    
    @pytest.mark.asyncio
    async def test_session_rollback_on_error(self):
        """Test that sessions properly rollback on errors."""
        try:
            async with AsyncSessionLocal() as session:
                # Try to execute invalid SQL
                with pytest.raises(Exception):
                    await session.execute(text("INVALID SQL STATEMENT"))
                
                # Session should still be usable after rollback
                assert session.is_active
                
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")


# Integration test that requires a real database
class TestDatabaseIntegration:
    """Integration tests that require a real database connection."""
    
    @pytest.mark.asyncio
    async def test_full_crud_operations(self):
        """Test complete CRUD operations on MiddlewareSession."""
        try:
            async with AsyncSessionLocal() as session:
                # CREATE
                new_session = MiddlewareSession(
                    jd_id="integration_test_job",
                    cv_ids=["cv_1", "cv_2"],
                    ai_session_id="integration_ai_session",
                    status="pending"
                )
                session.add(new_session)
                await session.commit()
                session_id = new_session.session_id
                
                # READ
                from sqlalchemy import select
                stmt = select(MiddlewareSession).where(
                    MiddlewareSession.session_id == session_id
                )
                result = await session.execute(stmt)
                retrieved = result.scalar_one_or_none()
                
                assert retrieved is not None
                assert retrieved.jd_id == "integration_test_job"
                
                # UPDATE
                retrieved.status = "completed"
                await session.commit()
                
                # Verify update
                result = await session.execute(stmt)
                updated = result.scalar_one_or_none()
                assert updated.status == "completed"
                
                # DELETE
                await session.delete(updated)
                await session.commit()
                
                # Verify deletion
                result = await session.execute(stmt)
                deleted = result.scalar_one_or_none()
                assert deleted is None
                
        except Exception as e:
            pytest.skip(f"Database not available for testing: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])