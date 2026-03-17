"""Add tutor models: TutorSession, ObjectiveState, StudentProfile

Revision ID: 002
Revises: 001
Create Date: 2026-01-13 00:41:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tutor_sessions table
    op.create_table(
        'tutor_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('ou_id', sa.String(length=100), nullable=True),
        sa.Column('student_id', sa.String(length=100), nullable=False),
        sa.Column('region_id', sa.String(length=50), nullable=True),
        sa.Column('program_id', sa.String(length=100), nullable=True),
        sa.Column('lesson_id', sa.String(length=100), nullable=False),
        sa.Column('objective_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('context_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_objective_id', sa.String(length=100), nullable=True),
        sa.Column('session_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tutor_sessions_tenant_student', 'tutor_sessions', ['tenant_id', 'student_id'], unique=False)
    op.create_index('ix_tutor_sessions_tenant_lesson', 'tutor_sessions', ['tenant_id', 'lesson_id'], unique=False)
    op.create_index('ix_tutor_sessions_tenant_ou', 'tutor_sessions', ['tenant_id', 'ou_id'], unique=False)
    op.create_index('ix_tutor_sessions_tenant_status', 'tutor_sessions', ['tenant_id', 'status'], unique=False)

    # Create tutor_objective_states table
    op.create_table(
        'tutor_objective_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('objective_id', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('questions_asked', sa.Integer(), nullable=False),
        sa.Column('questions_correct', sa.Integer(), nullable=False),
        sa.Column('questions_incorrect', sa.Integer(), nullable=False),
        sa.Column('last_error_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('mastery_estimate', sa.String(length=20), nullable=False),
        sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mastered_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['tutor_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_objective_states_tenant_session', 'tutor_objective_states', ['tenant_id', 'session_id'], unique=False)
    op.create_index('ix_objective_states_tenant_objective', 'tutor_objective_states', ['tenant_id', 'objective_id'], unique=False)

    # Create tutor_student_profiles table
    op.create_table(
        'tutor_student_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('student_id', sa.String(length=100), nullable=False),
        sa.Column('primary_ou_id', sa.String(length=100), nullable=True),
        sa.Column('ou_memberships', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('primary_language', sa.String(length=10), nullable=True),
        sa.Column('grade_band', sa.String(length=20), nullable=True),
        sa.Column('region_id', sa.String(length=50), nullable=True),
        sa.Column('objective_stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('pace_estimate', sa.String(length=20), nullable=False),
        sa.Column('engagement_estimate', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'student_id', name='uq_student_profile_tenant_student')
    )
    op.create_index('ix_student_profiles_tenant_student', 'tutor_student_profiles', ['tenant_id', 'student_id'], unique=False)
    op.create_index('ix_student_profiles_tenant_ou', 'tutor_student_profiles', ['tenant_id', 'primary_ou_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_index('ix_student_profiles_tenant_ou', table_name='tutor_student_profiles')
    op.drop_index('ix_student_profiles_tenant_student', table_name='tutor_student_profiles')
    op.drop_table('tutor_student_profiles')
    
    op.drop_index('ix_objective_states_tenant_objective', table_name='tutor_objective_states')
    op.drop_index('ix_objective_states_tenant_session', table_name='tutor_objective_states')
    op.drop_table('tutor_objective_states')
    
    op.drop_index('ix_tutor_sessions_tenant_status', table_name='tutor_sessions')
    op.drop_index('ix_tutor_sessions_tenant_ou', table_name='tutor_sessions')
    op.drop_index('ix_tutor_sessions_tenant_lesson', table_name='tutor_sessions')
    op.drop_index('ix_tutor_sessions_tenant_student', table_name='tutor_sessions')
    op.drop_table('tutor_sessions')

