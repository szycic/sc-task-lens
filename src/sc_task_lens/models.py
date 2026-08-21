"""SQLAlchemy Database Models for SC Task Lens.

Defines tables for screenshots, task candidates, Notion configuration,
field mappings, and AI engine settings.
"""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sc_task_lens.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


class Screenshot(Base):
    """Stores metadata of uploaded screenshots."""
    __tablename__ = "screenshots"

    id: Any = Column(Integer, primary_key=True, index=True)
    filename: Any = Column(String(255), nullable=False)
    file_path: Any = Column(String(500), nullable=False)
    uploaded_at: Any = Column(DateTime, default=_utc_now)
    is_processed: Any = Column(Boolean, default=False)

    task_candidate = relationship("TaskCandidate", back_populates="screenshot", uselist=False, cascade="all, delete-orphan")


class TaskCandidate(Base):
    """Stores visual-extracted task candidates and their lifecycle stage."""
    __tablename__ = "task_candidates"

    id: Any = Column(Integer, primary_key=True, index=True)
    screenshot_id: Any = Column(Integer, ForeignKey("screenshots.id"), nullable=True, index=True)
    title: Any = Column(String(255), nullable=False)
    summary: Any = Column(Text, nullable=True)
    is_task: Any = Column(Boolean, default=True)
    priority: Any = Column(String(20), nullable=True)       # Select option matching Notion schema (e.g. 'HIGH', 'MEDIUM', 'LOW')
    start_date: Any = Column(String(100), nullable=True)     # ISO YYYY-MM-DD or formatted date string
    deadline: Any = Column(String(100), nullable=True)       # ISO YYYY-MM-DD or formatted due date string
    source_url: Any = Column(String(500), nullable=True)     # Extracted HTTP/HTTPS URL or user-provided reference
    project: Any = Column(String(100), nullable=True)        # e.g. "Work", "Personal"
    status: Any = Column(String(20), default="PENDING", index=True)      # 'PENDING', 'AI_PROCESSED', 'CREATED', 'IGNORED'
    previous_status: Any = Column(String(20), nullable=True) # Tracks exact stage prior to IGNORED status
    auto_ignored_reason: Any = Column(String(255), nullable=True)
    notion_page_id: Any = Column(String(255), nullable=True)
    notion_url: Any = Column(String(500), nullable=True)
    created_at: Any = Column(DateTime, default=_utc_now)
    updated_at: Any = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    screenshot = relationship("Screenshot", back_populates="task_candidate")


class NotionConfig(Base):
    """Stores Notion API integration token and target database ID."""
    __tablename__ = "notion_configs"

    id: Any = Column(Integer, primary_key=True, index=True)
    api_token: Any = Column(String(255), nullable=True)
    database_id: Any = Column(String(255), nullable=True)
    database_title: Any = Column(String(255), nullable=True)
    last_schema_json: Any = Column(Text, nullable=True)


class NotionFieldMapping(Base):
    """Stores mapping between TaskCandidate fields and Notion Database properties."""
    __tablename__ = "notion_field_mappings"

    id: Any = Column(Integer, primary_key=True, index=True)
    task_field: Any = Column(String(50), unique=True, nullable=False)  # 'title', 'summary', 'priority', 'start_date', 'deadline', 'source_url', 'project', 'attachment'
    notion_property_name: Any = Column(String(100), nullable=False)     # Property name in Notion (e.g., 'Task Name')
    notion_property_type: Any = Column(String(50), nullable=False)      # Notion type ('title', 'rich_text', 'date', 'select', 'status', 'url', 'files')
    value_mappings_json: Any = Column(Text, nullable=True)             # Options map JSON string


class AISettings(Base):
    """Stores AI engine provider configuration (Mock, OpenAI, Gemini, Groq)."""
    __tablename__ = "ai_settings"

    id: Any = Column(Integer, primary_key=True, index=True)
    provider: Any = Column(String(50), default="mock")  # 'mock', 'openai', 'gemini', 'groq'
    api_key: Any = Column(String(255), nullable=True)
    model_name: Any = Column(String(100), nullable=True)
    custom_prompt: Any = Column(Text, nullable=True)


class SystemSettings(Base):
    """Stores system-wide administrative configuration (UI refresh & auto-purge settings)."""
    __tablename__ = "system_settings"

    id: Any = Column(Integer, primary_key=True, index=True)

    # Frontend Dashboard UI Auto-Refresh Configuration
    ui_auto_refresh_enabled: Any = Column(Boolean, default=True)
    ui_auto_refresh_interval_seconds: Any = Column(Integer, default=30)

    # Automatic Purge Settings
    auto_purge_synced_enabled: Any = Column(Boolean, default=False)
    purge_synced_days: Any = Column(Integer, default=30)

    auto_purge_ignored_enabled: Any = Column(Boolean, default=False)
    purge_ignored_days: Any = Column(Integer, default=30)

    # Web Push VAPID Configuration
    vapid_private_key: Any = Column(Text, nullable=True)
    vapid_public_key: Any = Column(Text, nullable=True)
    vapid_claims_sub: Any = Column(String(255), default="mailto:admin@sc-task-lens.local")

    updated_at: Any = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class PushSubscription(Base):
    """Stores Web Push API subscriptions for client devices to receive push notifications."""
    __tablename__ = "push_subscriptions"

    id: Any = Column(Integer, primary_key=True, index=True)
    endpoint: Any = Column(Text, unique=True, nullable=False, index=True)
    p256dh: Any = Column(Text, nullable=False)
    auth: Any = Column(Text, nullable=False)
    user_agent: Any = Column(String(255), nullable=True)
    created_at: Any = Column(DateTime, default=_utc_now)
