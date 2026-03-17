#!/usr/bin/env python3
"""
Verify DB migrations: print current Alembic revision and check that
student_lessons (and optionally other) tables exist.
Run inside the app container: python scripts/verify_migrations.py
Or locally with same DATABASE_URL: python scripts/verify_migrations.py
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    from app.core.config import settings

    url = settings.DATABASE_URL
    if not url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    # Use sync URL for raw connection check if we only have async
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            # Current Alembic revision
            try:
                r = await conn.execute(text("SELECT version_num FROM alembic_version"))
                rev = r.scalar() or "(none)"
            except Exception as e:
                rev = f"ERROR: {e}"
            print(f"Current Alembic revision: {rev}")

            # Check student_lessons exists
            try:
                r = await conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'student_lessons')"
                    )
                )
                exists = r.scalar()
                if exists:
                    print("Table student_lessons: EXISTS")
                else:
                    print("Table student_lessons: MISSING (run: alembic upgrade head)")
                    sys.exit(1)
            except Exception as e:
                print(f"Table student_lessons check failed: {e}")
                sys.exit(1)
    finally:
        await engine.dispose()
    print("Migrations verification OK.")


if __name__ == "__main__":
    asyncio.run(main())
