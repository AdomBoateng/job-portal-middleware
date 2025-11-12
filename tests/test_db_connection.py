#!/usr/bin/env python3
"""
Database connection test script
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

async def test_database_connection():
    """Test database connection with current settings."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    
    database_url = os.getenv("DATABASE_URL")
    print(f"Testing connection to: {database_url}")
    
    try:
        # Create engine
        engine = create_async_engine(database_url, echo=True)
        
        # Test connection
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            print(f"✅ Connection successful! Test query result: {row}")
            
        # Test database info
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.fetchone()
            print(f"📊 PostgreSQL version: {version[0]}")
            
        # Test database name
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()
            print(f"🗄️  Current database: {db_name[0]}")
            
        await engine.dispose()
        print("✅ Database connection test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Specific error handling
        if "password authentication failed" in str(e):
            print("💡 Hint: Check your database password")
        elif "could not connect to server" in str(e):
            print("💡 Hint: Check if PostgreSQL is running and accessible")
        elif "does not exist" in str(e):
            print("💡 Hint: Check if the database exists")
        elif "Name or service not known" in str(e):
            print("💡 Hint: Check your database host/port")
            
        return False

if __name__ == "__main__":
    print("🔍 Database Connection Test")
    print("=" * 40)
    
    success = asyncio.run(test_database_connection())
    
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Connection test failed!")
        sys.exit(1)