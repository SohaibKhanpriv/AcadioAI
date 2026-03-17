"""Add StudentLesson, StudentLessonObjective; add skill_level to tutor_student_profiles

Revision ID: 003
Revises: 002
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add skill_level to tutor_student_profiles
    op.add_column(
        "tutor_student_profiles",
        sa.Column("skill_level", sa.String(length=20), nullable=True),
    )

    # Create student_lessons table
    op.create_table(
        "student_lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("student_id", sa.String(length=100), nullable=False),
        sa.Column("lesson_id", sa.String(length=100), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("grade", sa.String(length=20), nullable=True),
        sa.Column("skill_level", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="llm_generated"),
        sa.Column("lesson_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_student_lessons_tenant_student",
        "student_lessons",
        ["tenant_id", "student_id"],
        unique=False,
    )

    # Create student_lesson_objectives table
    op.create_table(
        "student_lesson_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("student_lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("objective_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_lesson_id"],
            ["student_lessons.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_student_lesson_objectives_tenant_lesson",
        "student_lesson_objectives",
        ["tenant_id", "student_lesson_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_lesson_objectives_tenant_lesson",
        table_name="student_lesson_objectives",
    )
    op.drop_table("student_lesson_objectives")

    op.drop_index("ix_student_lessons_tenant_student", table_name="student_lessons")
    op.drop_table("student_lessons")

    op.drop_column("tutor_student_profiles", "skill_level")
