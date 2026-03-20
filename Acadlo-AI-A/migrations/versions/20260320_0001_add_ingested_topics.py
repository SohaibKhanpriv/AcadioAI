"""Add ingested_topics table for topic extraction during ingestion

Revision ID: 004
Revises: 003
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingested_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=50), nullable=False),
        sa.Column("topic_name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("grade_level", sa.String(length=20), nullable=True),
        sa.Column(
            "suggested_objectives",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("topic_embedding", Vector(1536), nullable=True),
        sa.Column(
            "source_offsets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingested_topics_tenant_id",
        "ingested_topics",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_ingested_topics_tenant_subject",
        "ingested_topics",
        ["tenant_id", "subject"],
        unique=False,
    )
    op.create_index(
        "ix_ingested_topics_document_id",
        "ingested_topics",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingested_topics_document_id", table_name="ingested_topics")
    op.drop_index("ix_ingested_topics_tenant_subject", table_name="ingested_topics")
    op.drop_index("ix_ingested_topics_tenant_id", table_name="ingested_topics")
    op.drop_table("ingested_topics")
