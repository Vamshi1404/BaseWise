import asyncio
import os
import sys

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def test_db():
    print("Connecting to Supabase Postgres...")
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT current_database(), current_schema();"))
        row = res.fetchone()
        print("✅ CONNECTIVITY SUCCESSFUL!")
        print(f"   Database: {row[0]}, Schema: {row[1]}")

        # Check if tables created by schema.sql exist
        tables_res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';"))
        tables = [r[0] for r in tables_res.fetchall()]
        print(f"   Public tables found ({len(tables)}):", ", ".join(tables))
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_db())
