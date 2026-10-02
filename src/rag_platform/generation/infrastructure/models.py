"""SQLAlchemy ORM model for the generation context."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rag_platform.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptTemplateModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    model_target: Mapped[str] = mapped_column(String(100), nullable=False)
