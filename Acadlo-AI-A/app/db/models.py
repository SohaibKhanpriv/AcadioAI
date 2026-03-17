"""SQLAlchemy ORM models for Acadlo AI Core"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String, Text, DateTime, ForeignKey, Index,
    func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all ORM models"""
    pass


class Document(Base):
    """
    Document model - stores ingested documents.
    
    Each document belongs to a tenant and has visibility controls.
    """
    __tablename__ = "documents"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # External reference (for linking to ABP or other systems)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Document metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g., "ar-JO", "en-US"
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "policy", "curriculum"
    
    # Visibility/Access control
    visibility_roles: Mapped[List[str]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=list
    )  # e.g., ["Teacher", "Principal"]
    visibility_scopes: Mapped[List[str]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=list
    )  # e.g., ["School:123", "Directorate:5"]
    
    # Tags for filtering
    tags: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=dict
    )  # e.g., {"stage": "Primary", "year": "2025"}
    
    # Content storage
    content_location_type: Mapped[str] = mapped_column(
        String(20), 
        nullable=False
    )  # "text" or "blob"
    content_location_value: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )  # Full text or URL/path to blob
    
    # Additional metadata (renamed from 'metadata' which is reserved in SQLAlchemy)
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, 
        nullable=True, 
        default=dict
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk", 
        back_populates="document",
        cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[List["IngestionJob"]] = relationship(
        "IngestionJob",
        back_populates="document"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_external_id", "external_id"),
        Index("ix_documents_source_type", "source_type"),
    )


class Chunk(Base):
    """
    Chunk model - stores document chunks with embeddings.
    
    Each chunk is a portion of a document, with its own embedding vector
    for similarity search.
    """
    __tablename__ = "chunks"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign key to document
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Tenant isolation (denormalized for query performance)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Chunk content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Vector embedding for similarity search
    # OpenAI text-embedding-3-small produces 1536-dimensional vectors
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(1536), 
        nullable=True  # Nullable until embedding is generated
    )
    
    # Visibility (inherited from document, denormalized for query performance)
    visibility_roles: Mapped[List[str]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=list
    )
    visibility_scopes: Mapped[List[str]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=list
    )
    
    # Tags (inherited from document)
    tags: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=dict
    )
    
    # Position in original document
    start_offset: Mapped[Optional[int]] = mapped_column(nullable=True)
    end_offset: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
    
    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", 
        back_populates="chunks"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_chunks_tenant_id", "tenant_id"),
        Index("ix_chunks_document_id", "document_id"),
    )


class IngestionJob(Base):
    """
    IngestionJob model - tracks document ingestion progress.
    
    Status lifecycle: pending -> processing -> completed/failed
    """
    __tablename__ = "ingestion_jobs"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Associated document (nullable until document is created)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Job status
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="pending"
    )  # pending, processing, completed, failed
    
    # Error information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now(),
        onupdate=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Relationships
    document: Mapped[Optional["Document"]] = relationship(
        "Document", 
        back_populates="ingestion_jobs"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_ingestion_jobs_tenant_id", "tenant_id"),
        Index("ix_ingestion_jobs_status", "status"),
        Index("ix_ingestion_jobs_document_id", "document_id"),
    )


# =============================================================================
# Tutor Runtime Engine Models
# =============================================================================


class TutorSession(Base):
    """
    TutorSession model - represents a single tutoring session for a student.
    
    A session is created when a student starts working on a lesson, and tracks
    the overall progress through multiple learning objectives.
    """
    __tablename__ = "tutor_sessions"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Organization / OU context
    ou_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # Organization Unit ID (school/class where session is happening)
    
    # Student & region
    student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    region_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Program / lesson context
    program_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # e.g., "Grade1-Math-2025"
    lesson_id: Mapped[str] = mapped_column(String(100), nullable=False)
    objective_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )  # List of objective IDs for this session
    
    # Visibility / scopes for RAG (resolved by backend)
    context_scopes: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )  # e.g., ["School:123", "Class:456"]
    
    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active"
    )  # active, completed, aborted
    
    # Runtime snapshot
    current_objective_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # Which objective the tutor is currently working on
    
    # Extension metadata (renamed from 'metadata' which is reserved in SQLAlchemy)
    session_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )  # UI context, scenario, language, etc.
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )  # When first interaction occurred
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )  # When session was completed/aborted
    
    # Relationships
    objective_states: Mapped[List["ObjectiveState"]] = relationship(
        "ObjectiveState",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_tutor_sessions_tenant_student", "tenant_id", "student_id"),
        Index("ix_tutor_sessions_tenant_lesson", "tenant_id", "lesson_id"),
        Index("ix_tutor_sessions_tenant_ou", "tenant_id", "ou_id"),
        Index("ix_tutor_sessions_tenant_status", "tenant_id", "status"),
    )


class ObjectiveState(Base):
    """
    ObjectiveState model - tracks the state and progress of a single learning
    objective within a tutoring session.
    
    Each session has multiple objectives, and each objective has its own state
    tracking (questions asked, mastery level, teaching phase, etc.).
    """
    __tablename__ = "tutor_objective_states"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Foreign keys
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tutor_sessions.id", ondelete="CASCADE"),
        nullable=False
    )
    objective_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )  # Objective identifier from lesson backend
    
    # Teaching state & progress
    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="not_started"
    )  # ObjectiveTeachingState enum values
    questions_asked: Mapped[int] = mapped_column(nullable=False, default=0)
    questions_correct: Mapped[int] = mapped_column(nullable=False, default=0)
    questions_incorrect: Mapped[int] = mapped_column(nullable=False, default=0)
    
    # Error tracking
    last_error_types: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )  # e.g., ["place_value", "common_denominator"]
    
    # Mastery estimate
    mastery_estimate: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low"
    )  # low, medium, high
    
    # Extension
    extra: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )  # Per-objective notes, affect aggregates, etc.
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )  # When teaching for this objective began
    mastered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )  # When objective was mastered
    
    # Relationships
    session: Mapped["TutorSession"] = relationship(
        "TutorSession",
        back_populates="objective_states"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_objective_states_tenant_session", "tenant_id", "session_id"),
        Index("ix_objective_states_tenant_objective", "tenant_id", "objective_id"),
    )


class StudentProfile(Base):
    """
    StudentProfile model - persistent per-student profile that accumulates
    learning signals across all tutoring sessions.
    
    This model stores stable attributes (language, grade) and aggregated
    learning history (objective stats, pace, engagement) for a student
    within a tenant, with awareness of their primary OU.
    """
    __tablename__ = "tutor_student_profiles"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Identity & tenancy
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Organization / OU context
    primary_ou_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # Student's primary OU (main school/class)
    ou_memberships: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )  # Optional list of OU IDs where student is active
    
    # Stable attributes
    primary_language: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True
    )  # e.g., "ar", "en"
    grade_band: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )  # e.g., "G1", "G2-3"
    skill_level: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )  # beginner, intermediate, advanced
    region_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    # Learning profile (aggregated signals)
    objective_stats: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )  # Keyed by objective_id: { total_sessions, total_questions, total_correct, last_mastery_estimate }
    pace_estimate: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown"
    )  # fast, normal, slow, unknown
    engagement_estimate: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unknown"
    )  # high, medium, low, unknown
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Unique constraint and indexes
    __table_args__ = (
        UniqueConstraint("tenant_id", "student_id", name="uq_student_profile_tenant_student"),
        Index("ix_student_profiles_tenant_student", "tenant_id", "student_id"),
        Index("ix_student_profiles_tenant_ou", "tenant_id", "primary_ou_id"),
    )


# =============================================================================
# Student Lesson & Objectives (LLM-generated or external, per student)
# =============================================================================


class StudentLesson(Base):
    """
    StudentLesson model - stores a lesson (and its metadata) for a specific student.
    
    Used when no lesson_id is provided by the caller: after onboarding, the system
    may generate a lesson via LLM or reuse an existing one. The lesson_id field
    is the slug used as TutorSession.lesson_id.
    """
    __tablename__ = "student_lessons"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lesson_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )  # Slug used as TutorSession.lesson_id, e.g. lesson_division_g4_beginner
    topic: Mapped[str] = mapped_column(String(200), nullable=False)  # What the student asked, e.g. "division"
    title: Mapped[str] = mapped_column(String(500), nullable=False)  # LLM-generated title
    grade: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # e.g. "4"
    skill_level: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )  # beginner, intermediate, advanced
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # e.g. "en"
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="llm_generated"
    )  # llm_generated, external
    lesson_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    objectives: Mapped[List["StudentLessonObjective"]] = relationship(
        "StudentLessonObjective",
        back_populates="student_lesson",
        cascade="all, delete-orphan",
        order_by="StudentLessonObjective.display_order",
    )
    
    __table_args__ = (
        Index("ix_student_lessons_tenant_student", "tenant_id", "student_id"),
    )


class StudentLessonObjective(Base):
    """
    StudentLessonObjective model - one learning objective under a StudentLesson.
    """
    __tablename__ = "student_lesson_objectives"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    student_lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("student_lessons.id", ondelete="CASCADE"),
        nullable=False
    )
    objective_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )  # Slug used in ObjectiveState, e.g. obj_equal_sharing
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    student_lesson: Mapped["StudentLesson"] = relationship(
        "StudentLesson",
        back_populates="objectives"
    )
    
    __table_args__ = (
        Index("ix_student_lesson_objectives_tenant_lesson", "tenant_id", "student_lesson_id"),
    )
