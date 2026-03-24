"""
SQLAlchemy ORM models for the MRAK-OS platform.

Defines database schema for multi-tenant AI bot platform including:
- Projects, clients, threads, messages
- Knowledge base with pgvector embeddings
- Event store for event-sourced agent runtime
- Workflow templates and custom workflows
- Manager assignments and execution queue
- User identities for multi-provider authentication
"""

import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Text, ForeignKey, DateTime, func, Boolean,
    Integer, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class ThreadStatus(str, enum.Enum):
    """Status values for conversation threads."""
    ACTIVE = "active"
    MANUAL = "manual"  # Escalated to human manager
    CLOSED = "closed"


class MessageRole(str, enum.Enum):
    """Role values for messages in conversations."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class EventType(str, enum.Enum):
    """Event types for the event-sourced agent runtime."""
    MESSAGE_RECEIVED = "message_received"
    AI_REPLIED = "ai_replied"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    TICKET_CREATED = "ticket_created"
    MANAGER_REPLIED = "manager_replied"
    CONVERSATION_STARTED = "conversation_started"
    CONVERSATION_CLOSED = "conversation_closed"
    WORKFLOW_LOADED = "workflow_loaded"


class Project(Base):
    """
    Project model representing a tenant/business in the SaaS platform.
    
    Each project has isolated bot configuration, knowledge base,
    managers, and workflow settings.
    """
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    # Bot configuration (encrypted at rest)
    bot_token: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default="Ты полезный ассистент."
    )
    webhook_url: Mapped[str] = mapped_column(String, nullable=True)
    
    # Manager bot configuration
    manager_bot_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Bot usernames for display in UI
    client_bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manager_bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Workflow configuration
    template_slug: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default=None
    )
    is_pro_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    clients = relationship(
        "Client", back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_base = relationship(
        "KnowledgeBase", back_populates="project", cascade="all, delete-orphan"
    )
    managers = relationship(
        "ProjectManager", back_populates="project", cascade="all, delete-orphan"
    )
    events = relationship(
        "Event", back_populates="project", cascade="all, delete-orphan"
    )
    workflows = relationship(
        "Workflow", back_populates="project", cascade="all, delete-orphan"
    )
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_projects_template_slug", "template_slug"),
        Index("idx_projects_pro_mode", "is_pro_mode", postgresql_where=(is_pro_mode == True)),
        Index("idx_projects_user_id", "user_id"),
        Index("idx_projects_client_bot_username", "client_bot_username"),
        Index("idx_projects_manager_bot_username", "manager_bot_username"),
    )


class Client(Base):
    """
    Client model representing an end-user who interacts with a project's bot.
    
    Each client belongs to exactly one project and can have multiple
    conversation threads.
    """
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    crm_contact_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="telegram"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="clients")
    threads = relationship(
        "Thread", back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "chat_id", name="uq_clients_project_chat"),
        Index("idx_clients_chat_id", "chat_id"),
    )


class Thread(Base):
    """
    Thread model representing a conversation session between a client and bot.
    
    Threads track conversation state, escalation status, and summary
    for context management in LangGraph.
    """
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ThreadStatus] = mapped_column(
        default=ThreadStatus.ACTIVE, nullable=False
    )
    interaction_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="normal"
    )
    
    # Context management for LangGraph
    context_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Manager assignment for escalated threads
    manager_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Workflow tracking
    workflow_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflows.id"), nullable=True
    )
    workflow_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client = relationship("Client", back_populates="threads")
    messages = relationship(
        "Message", back_populates="thread", cascade="all, delete-orphan"
    )
    events = relationship(
        "Event", back_populates="thread", cascade="all, delete-orphan"
    )
    workflow = relationship("Workflow", back_populates="threads")

    __table_args__ = (
        Index(
            "idx_threads_manager_chat",
            "manager_chat_id",
            postgresql_where=(status == ThreadStatus.MANUAL)
        ),
        Index("idx_threads_workflow", "workflow_id", "workflow_version"),
        Index("idx_threads_interaction_mode", "interaction_mode"),
    )


class Message(Base):
    """
    Message model representing a single message in a conversation thread.
    
    Messages are immutable and follow the event-sourcing pattern
    where all state changes are recorded as events.
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # LangGraph tool calling support
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    thread = relationship("Thread", back_populates="messages")

    __table_args__ = (
        Index("idx_messages_thread_created", "thread_id", "created_at"),
    )


class KnowledgeDocument(Base):
    """
    Document model representing an uploaded file in the knowledge base.
    
    Each document can have multiple chunks in the knowledge_base table.
    """
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="knowledge_documents")
    chunks = relationship(
        "KnowledgeBase", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_knowledge_documents_project", "project_id"),
        Index("idx_knowledge_documents_status", "status"),
    )


class KnowledgeBase(Base):
    """
    KnowledgeBase model for RAG (Retrieval-Augmented Generation).
    
    Stores document chunks with vector embeddings for semantic search
    using pgvector. Each chunk belongs to exactly one project and optionally
    to a document.
    """
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Vector embedding for semantic search (BAAI/bge-small-en-v1.5 = 384 dims)
    embedding: Mapped[Vector] = mapped_column(Vector(384), nullable=False)
    
    # Metadata for filtering and organization
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chunk_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="knowledge_base")
    document = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_knowledge_project_category", "project_id", "category"),
        Index("idx_knowledge_base_document", "document_id"),
        Index(
            "idx_knowledge_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100}
        ),
    )


class ProjectManager(Base):
    """
    ProjectManager model linking managers (by Telegram chat_id) to projects.
    
    A project can have multiple managers who receive escalation notifications.
    """
    __tablename__ = "project_managers"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    manager_chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="managers")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "manager_chat_id",
            name="uq_project_managers_project_chat"
        ),
    )


class Event(Base):
    """
    Event model for the event-sourced agent runtime.
    
    All state-changing actions in the system are recorded as immutable
    events. This enables replay, debugging, analytics, and projections.
    
    Each event belongs to a stream (conversation) and a project.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    stream_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="events")
    thread = relationship(
        "Thread",
        foreign_keys=[stream_id],
        primaryjoin="Event.stream_id == Thread.id",
        back_populates="events",
        viewonly=True
    )

    __table_args__ = (
        Index("idx_events_stream_created", "stream_id", "created_at"),
        Index("idx_events_project_type", "project_id", "event_type"),
        Index("idx_events_created", "created_at"),
    )


class WorkflowTemplate(Base):
    """
    WorkflowTemplate model for pre-built workflow configurations.
    
    Templates allow users to quickly set up projects with ready-made
    graph structures (support, leads, orders, etc.).
    """
    __tablename__ = "workflow_templates"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # LangGraph-compatible graph definition
    graph_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_templates_active", "is_active", postgresql_where=(is_active == True)),
        Index("idx_templates_slug", "slug"),
    )


class Workflow(Base):
    """
    Workflow model for custom user-created workflow configurations.
    
    Pro mode users can create and manage their own graph structures
    via the visual canvas. Each workflow has versioning for safe updates.
    """
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # LangGraph-compatible graph definition from canvas
    graph_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="workflows")
    threads = relationship(
        "Thread",
        foreign_keys=[Thread.workflow_id],
        back_populates="workflow",
        viewonly=True
    )

    __table_args__ = (
        Index("idx_workflows_project", "project_id"),
        Index(
            "idx_workflows_active",
            "project_id", "is_active",
            postgresql_where=(is_active == True)
        ),
        UniqueConstraint("project_id", "name", name="uq_workflows_project_name"),
    )


class User(Base):
    """
    User model representing platform users (project owners, etc.).
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    telegram_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_metadata: Mapped[dict] = mapped_column(JSON, default={})
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    identities = relationship("AuthIdentity", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", foreign_keys=[Project.user_id], back_populates="user")

    __table_args__ = (
        Index("idx_users_telegram_id", "telegram_id"),
        Index("idx_users_email", "email"),
        Index("idx_users_project_id", "project_id"),
    )


class AuthIdentity(Base):
    """
    AuthIdentity model linking a user with external authentication providers.
    """
    __tablename__ = "auth_identities"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_auth_identities_provider_provider_id"),
        Index("idx_auth_identities_user", "user_id"),
    )
