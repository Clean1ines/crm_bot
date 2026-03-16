import enum
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, func, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

class Base(DeclarativeBase):
    pass

class ThreadStatus(str, enum.Enum):
    ACTIVE = "active"
    MANUAL = "manual"  # Эскалация на оператора
    CLOSED = "closed"

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

# 1. ПРОЕКТЫ (Компании / Клиенты SaaS)
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False) # Твой ID клиента
    
    # Настройки бота для этого бизнеса
    bot_token: Mapped[str] = mapped_column(String, nullable=False) # Зашифрованный токен
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="Ты полезный ассистент.")
    webhook_url: Mapped[str] = mapped_column(String, nullable=True) # Куда слать лиды (Zapier, Make)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Связи
    clients = relationship("Client", back_populates="project", cascade="all, delete-orphan")
    knowledge_base = relationship("KnowledgeBase", back_populates="project", cascade="all, delete-orphan")


# 2. КЛИЕНТЫ ТЕЛЕГРАМА (Конечные пользователи, которые пишут ботам)
class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    crm_contact_id: Mapped[str] = mapped_column(String(100), nullable=True) # Если синхронизируем с их CRM
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    project = relationship("Project", back_populates="clients")
    threads = relationship("Thread", back_populates="client", cascade="all, delete-orphan")


# 3. ТРЕДЫ (Диалоговые сессии / Замена clarification_sessions)
class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ThreadStatus] = mapped_column(default=ThreadStatus.ACTIVE, nullable=False)
    
    # Саммари диалога для экономии контекста (LangGraph будет сюда писать)
    context_summary: Mapped[str] = mapped_column(Text, nullable=True) 
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Связи
    client = relationship("Client", back_populates="threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")


# 4. СООБЩЕНИЯ (Идеальная плоская структура для LangGraph)
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Специфично для LangGraph Tool Calling
    tool_call_id: Mapped[str] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Связи
    thread = relationship("Thread", back_populates="messages")


# 5. БАЗА ЗНАНИЙ (RAG)
class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String, primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Вектор для BAAI/bge-small-en-v1.5 (FastEmbed) обычно имеет размерность 384
    embedding: Mapped[Vector] = mapped_column(Vector(384), nullable=False) 
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Связи
    project = relationship("Project", back_populates="knowledge_base")