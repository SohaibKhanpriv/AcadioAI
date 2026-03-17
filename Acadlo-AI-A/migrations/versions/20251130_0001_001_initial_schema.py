"""Initial schema with documents, chunks, and ingestion_jobs tables

Revision ID: 001
Revises: 
Create Date: 2025-11-30

This migration:
1. Enables the pgvector extension for vector similarity search
2. Creates the documents table for storing ingested documents
3. Creates the chunks table for storing document chunks with embeddings
4. Creates the ingestion_jobs table for tracking ingestion progress
5. Creates all necessary indexes for performance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('visibility_roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('visibility_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('content_location_type', sa.String(length=20), nullable=False),
        sa.Column('content_location_value', sa.Text(), nullable=False),
        sa.Column('doc_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create documents indexes
    op.create_index('ix_documents_tenant_id', 'documents', ['tenant_id'], unique=False)
    op.create_index('ix_documents_external_id', 'documents', ['external_id'], unique=False)
    op.create_index('ix_documents_source_type', 'documents', ['source_type'], unique=False)
    
    # Create chunks table
    op.create_table(
        'chunks',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('visibility_roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('visibility_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('start_offset', sa.Integer(), nullable=True),
        sa.Column('end_offset', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create chunks indexes
    op.create_index('ix_chunks_tenant_id', 'chunks', ['tenant_id'], unique=False)
    op.create_index('ix_chunks_document_id', 'chunks', ['document_id'], unique=False)
    
    # Create HNSW index for vector similarity search (cosine distance)
    op.execute('''
        CREATE INDEX ix_chunks_embedding_hnsw 
        ON chunks 
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')
    
    # Create ingestion_jobs table
    op.create_table(
        'ingestion_jobs',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create ingestion_jobs indexes
    op.create_index('ix_ingestion_jobs_tenant_id', 'ingestion_jobs', ['tenant_id'], unique=False)
    op.create_index('ix_ingestion_jobs_status', 'ingestion_jobs', ['status'], unique=False)
    op.create_index('ix_ingestion_jobs_document_id', 'ingestion_jobs', ['document_id'], unique=False)
    
    # Create a function to auto-update updated_at timestamp
    op.execute('''
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    ''')
    
    # Create triggers for auto-updating updated_at
    op.execute('''
        CREATE TRIGGER update_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    ''')
    
    op.execute('''
        CREATE TRIGGER update_ingestion_jobs_updated_at
        BEFORE UPDATE ON ingestion_jobs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    ''')


def downgrade() -> None:
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_ingestion_jobs_updated_at ON ingestion_jobs')
    op.execute('DROP TRIGGER IF EXISTS update_documents_updated_at ON documents')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column()')
    
    # Drop ingestion_jobs indexes and table
    op.drop_index('ix_ingestion_jobs_document_id', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_status', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_tenant_id', table_name='ingestion_jobs')
    op.drop_table('ingestion_jobs')
    
    # Drop chunks indexes and table
    op.execute('DROP INDEX IF EXISTS ix_chunks_embedding_hnsw')
    op.drop_index('ix_chunks_document_id', table_name='chunks')
    op.drop_index('ix_chunks_tenant_id', table_name='chunks')
    op.drop_table('chunks')
    
    # Drop documents indexes and table
    op.drop_index('ix_documents_source_type', table_name='documents')
    op.drop_index('ix_documents_external_id', table_name='documents')
    op.drop_index('ix_documents_tenant_id', table_name='documents')
    op.drop_table('documents')
    
    # Note: We don't drop the pgvector extension as it might be used by other schemas
