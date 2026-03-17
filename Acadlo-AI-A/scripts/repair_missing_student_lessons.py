#!/usr/bin/env python3
"""
One-off repair when alembic_version says 003 but student_lessons table is missing.

Run inside container: python scripts/repair_missing_student_lessons.py
Uses the same DATABASE_URL as the app; creates tables/columns only if missing.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    from app.core.config import settings

    url = settings.DATABASE_URL
    if not url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            # Check current state
            r = await conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'student_lessons')")
            )
            if r.scalar():
                print("Table student_lessons already exists. No repair needed.")
                return

            rev_r = await conn.execute(text("SELECT version_num FROM alembic_version"))
            rev = rev_r.scalar() or "(none)"
            print(f"Current alembic revision: {rev}. Creating missing student_lessons and related objects...")

            # End the read transaction so we can start a new one for DDL
            await conn.commit()

            # Run DDL in a transaction (same as migration 003, with IF NOT EXISTS where possible)
            async with conn.begin():
                # 1. skill_level on tutor_student_profiles (add only if missing)
                r = await conn.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'tutor_student_profiles' AND column_name = 'skill_level'
                """))
                if not r.scalar():
                    await conn.execute(text("ALTER TABLE tutor_student_profiles ADD COLUMN skill_level VARCHAR(20)"))
                    print("  Added column tutor_student_profiles.skill_level")
                else:
                    print("  Column tutor_student_profiles.skill_level already exists")

                # 2. student_lessons table
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS student_lessons (
                        id UUID NOT NULL PRIMARY KEY,
                        tenant_id VARCHAR(100) NOT NULL,
                        student_id VARCHAR(100) NOT NULL,
                        lesson_id VARCHAR(100) NOT NULL,
                        topic VARCHAR(200) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        grade VARCHAR(20),
                        skill_level VARCHAR(20),
                        language VARCHAR(10),
                        source VARCHAR(30) NOT NULL DEFAULT 'llm_generated',
                        lesson_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """))
                print("  Ensured table student_lessons")

                # Index (ignore if exists)
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_student_lessons_tenant_student ON student_lessons (tenant_id, student_id)
                """))
                print("  Ensured index ix_student_lessons_tenant_student")

                # 3. student_lesson_objectives table
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS student_lesson_objectives (
                        id UUID NOT NULL PRIMARY KEY,
                        tenant_id VARCHAR(100) NOT NULL,
                        student_lesson_id UUID NOT NULL REFERENCES student_lessons(id) ON DELETE CASCADE,
                        objective_id VARCHAR(100) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        description TEXT,
                        display_order INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """))
                print("  Ensured table student_lesson_objectives")

                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_student_lesson_objectives_tenant_lesson
                    ON student_lesson_objectives (tenant_id, student_lesson_id)
                """))
                print("  Ensured index ix_student_lesson_objectives_tenant_lesson")

            print("Repair complete.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
