"""
Integration test for db.py with real database operations

This test requires a working PostgreSQL database and will create/drop tables as needed.
Run this test when you want to validate the complete database functionality.
"""
import pytest
import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup
def import_modules():
    from app.services.db import engine, AsyncSessionLocal
    from app.models.models import MiddlewareSession, Base
    return engine, AsyncSessionLocal, MiddlewareSession, Base

engine, AsyncSessionLocal, MiddlewareSession, Base = import_modules()


async def setup_database():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def teardown_database():
    """Drop all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_database_setup_and_crud():
    """Test complete database setup and CRUD operations."""
    try:
        # Setup database tables
        await setup_database()
        print("✅ Database tables created successfully")
        
        async with AsyncSessionLocal() as session:
            # CREATE
            print("Testing CREATE operation...")
            new_session = MiddlewareSession(
                jd_id="integration_test_job_001",
                cv_ids=["cv_001", "cv_002", "cv_003"],
                ai_session_id="ai_session_integration_001",
                status="pending"
            )
            session.add(new_session)
            await session.commit()
            session_id = new_session.session_id
            print(f"✅ Created session with ID: {session_id}")
            
            # READ
            print("Testing READ operation...")
            from sqlalchemy import select
            stmt = select(MiddlewareSession).where(
                MiddlewareSession.session_id == session_id
            )
            result = await session.execute(stmt)
            retrieved = result.scalar_one_or_none()
            
            assert retrieved is not None
            assert retrieved.jd_id == "integration_test_job_001"
            assert retrieved.cv_ids == ["cv_001", "cv_002", "cv_003"]
            assert retrieved.ai_session_id == "ai_session_integration_001"
            assert retrieved.status == "pending"
            print("✅ READ operation successful")
            
            # UPDATE
            print("Testing UPDATE operation...")
            retrieved.status = "completed"
            retrieved.cv_ids = ["cv_001", "cv_002", "cv_003", "cv_004"]
            await session.commit()
            
            # Verify update
            result = await session.execute(stmt)
            updated = result.scalar_one_or_none()
            assert updated.status == "completed"
            assert len(updated.cv_ids) == 4
            print("✅ UPDATE operation successful")
            
            # Test querying multiple records
            print("Testing multiple record operations...")
            # Create additional sessions
            for i in range(3):
                extra_session = MiddlewareSession(
                    jd_id=f"bulk_test_job_{i:03d}",
                    status="pending"
                )
                session.add(extra_session)
            await session.commit()
            
            # Query all sessions
            all_sessions_stmt = select(MiddlewareSession)
            result = await session.execute(all_sessions_stmt)
            all_sessions = result.scalars().all()
            assert len(all_sessions) >= 4  # At least our 4 test sessions
            print(f"✅ Found {len(all_sessions)} total sessions in database")
            
            # DELETE
            print("Testing DELETE operation...")
            # Delete all test sessions
            for sess in all_sessions:
                await session.delete(sess)
            await session.commit()
            
            # Verify deletion
            result = await session.execute(all_sessions_stmt)
            remaining = result.scalars().all()
            assert len(remaining) == 0
            print("✅ DELETE operation successful")
        
        print("🎉 All CRUD operations completed successfully!")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        raise
    finally:
        # Clean up database tables
        await teardown_database()
        print("✅ Database cleanup completed")


@pytest.mark.asyncio
async def test_database_transactions():
    """Test database transaction handling."""
    try:
        await setup_database()
        
        # Test successful transaction
        async with AsyncSessionLocal() as session:
            session1 = MiddlewareSession(jd_id="transaction_test_1", status="pending")
            session.add(session1)
            await session.commit()
            
            # Verify it was committed
            from sqlalchemy import select
            stmt = select(MiddlewareSession).where(MiddlewareSession.jd_id == "transaction_test_1")
            result = await session.execute(stmt)
            found = result.scalar_one_or_none()
            assert found is not None
            print("✅ Transaction commit successful")
        
        # Test transaction rollback
        try:
            async with AsyncSessionLocal() as session:
                session2 = MiddlewareSession(jd_id="transaction_test_2", status="pending")
                session.add(session2)
                # Don't commit, let it rollback
                raise Exception("Intentional rollback")
        except Exception:
            pass  # Expected
        
        # Verify rollback worked
        async with AsyncSessionLocal() as session:
            stmt = select(MiddlewareSession).where(MiddlewareSession.jd_id == "transaction_test_2")
            result = await session.execute(stmt)
            found = result.scalar_one_or_none()
            assert found is None
            print("✅ Transaction rollback successful")
        
        # Clean up
        async with AsyncSessionLocal() as session:
            stmt = select(MiddlewareSession).where(MiddlewareSession.jd_id == "transaction_test_1")
            result = await session.execute(stmt)
            found = result.scalar_one_or_none()
            if found:
                await session.delete(found)
                await session.commit()
        
    finally:
        await teardown_database()


@pytest.mark.asyncio
async def test_database_performance():
    """Test database performance with multiple operations."""
    import time
    
    try:
        await setup_database()
        
        start_time = time.time()
        
        # Create multiple sessions in bulk
        async with AsyncSessionLocal() as session:
            sessions = []
            for i in range(100):
                sess = MiddlewareSession(
                    jd_id=f"perf_test_job_{i:03d}",
                    cv_ids=[f"cv_{j}" for j in range(i % 5)],
                    status="pending"
                )
                sessions.append(sess)
                session.add(sess)
            
            await session.commit()
            create_time = time.time() - start_time
            print(f"✅ Created 100 sessions in {create_time:.3f} seconds")
            
            # Query them back
            query_start = time.time()
            from sqlalchemy import select
            stmt = select(MiddlewareSession).where(MiddlewareSession.jd_id.like("perf_test_job_%"))
            result = await session.execute(stmt)
            found_sessions = result.scalars().all()
            query_time = time.time() - query_start
            
            assert len(found_sessions) == 100
            print(f"✅ Queried 100 sessions in {query_time:.3f} seconds")
            
            # Clean up
            for sess in found_sessions:
                await session.delete(sess)
            await session.commit()
        
        total_time = time.time() - start_time
        print(f"✅ Total test time: {total_time:.3f} seconds")
        
    finally:
        await teardown_database()


if __name__ == "__main__":
    async def run_all_tests():
        print("🔍 Database Integration Tests")
        print("=" * 50)
        
        try:
            print("\n📊 Running CRUD operations test...")
            await test_database_setup_and_crud()
            
            print("\n🔄 Running transaction test...")
            await test_database_transactions()
            
            print("\n⚡ Running performance test...")
            await test_database_performance()
            
            print("\n🎉 All integration tests passed!")
            
        except Exception as e:
            print(f"\n💥 Integration tests failed: {e}")
            sys.exit(1)
    
    asyncio.run(run_all_tests())