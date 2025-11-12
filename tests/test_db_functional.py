"""
Functional test for db.py using the actual database schema

This test validates the database connection and basic operations 
using the existing database schema.
"""
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text

# Add the project root to Python path  
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import modules after path setup
def import_db_modules():
    from app.services.db import engine, AsyncSessionLocal, get_db
    return engine, AsyncSessionLocal, get_db

engine, AsyncSessionLocal, get_db = import_db_modules()


async def test_database_functionality():
    """Test database functionality with the current schema."""
    print("🔍 Testing Database Functionality")
    print("=" * 40)
    
    try:
        # Test 1: Basic connection
        print("1. Testing basic database connection...")
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1
        print("✅ Basic connection successful")
        
        # Test 2: Session creation
        print("2. Testing session creation...")
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT current_database()"))
            db_name = result.fetchone()
            print(f"✅ Session created successfully, connected to: {db_name[0]}")
        
        # Test 3: get_db dependency function
        print("3. Testing get_db dependency function...")
        session_count = 0
        async for session in get_db():
            session_count += 1
            assert hasattr(session, 'execute')
            assert hasattr(session, 'commit')
            break  # Only test one session
        assert session_count == 1
        print("✅ get_db function working correctly")
        
        # Test 4: Query existing tables
        print("4. Testing table queries...")
        async with AsyncSessionLocal() as session:
            # Check middleware_sessions table
            result = await session.execute(text(
                "SELECT COUNT(*) FROM middleware_sessions"
            ))
            session_count = result.fetchone()[0]
            print(f"✅ Found {session_count} middleware sessions in database")
            
            # Check middleware_reports table
            result = await session.execute(text(
                "SELECT COUNT(*) FROM middleware_reports"
            ))
            report_count = result.fetchone()[0]
            print(f"✅ Found {report_count} middleware reports in database")
        
        # Test 5: Transaction handling
        print("5. Testing transaction handling...")
        async with AsyncSessionLocal() as session:
            # Start a transaction that we'll rollback
            await session.execute(text("BEGIN"))
            try:
                # This should work
                await session.execute(text("SELECT 1"))
                await session.execute(text("ROLLBACK"))
                print("✅ Transaction handling working correctly")
            except Exception as e:
                await session.execute(text("ROLLBACK"))
                raise e
        
        # Test 6: Multiple concurrent sessions
        print("6. Testing concurrent sessions...")
        async def session_task(task_id):
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(f"SELECT {task_id} as task_id"))
                return result.fetchone()[0]
        
        # Run multiple sessions concurrently
        tasks = [session_task(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        assert results == [0, 1, 2, 3, 4]
        print("✅ Concurrent sessions working correctly")
        
        print("\n🎉 All database functionality tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Database functionality test failed: {e}")
        return False


async def test_database_info():
    """Get information about the database setup."""
    print("\n📊 Database Information")
    print("=" * 40)
    
    try:
        async with engine.begin() as conn:
            # Database version
            result = await conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"PostgreSQL Version: {version.split(',')[0]}")
            
            # Current database
            result = await conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            print(f"Database Name: {db_name}")
            
            # Tables
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            ))
            tables = [row[0] for row in result.fetchall()]
            print(f"Tables: {', '.join(tables)}")
            
            # Connection info
            result = await conn.execute(text("SELECT inet_server_addr(), inet_server_port()"))
            server_info = result.fetchone()
            if server_info[0]:
                print(f"Server: {server_info[0]}:{server_info[1]}")
            
            print("✅ Database information retrieved successfully")
            
    except Exception as e:
        print(f"❌ Failed to get database information: {e}")


if __name__ == "__main__":
    async def main():
        # Run functionality tests
        success = await test_database_functionality()
        
        # Get database info
        await test_database_info()
        
        if success:
            print("\n🎉 All tests passed! The db.py module is working correctly.")
            sys.exit(0)
        else:
            print("\n💥 Some tests failed!")
            sys.exit(1)
    
    asyncio.run(main())