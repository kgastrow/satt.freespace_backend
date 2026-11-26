"""
Help Center models for FAQs, articles, and categories.

Support platform-wide (NULL organization_id) and org-specific content.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class HelpCategory(Base):
    """
    Categories for organizing help content.

    Multi-tenancy: Platform-wide (no organization_id).
    Categories are used to organize articles and FAQs.
    """

    __tablename__ = "help_category"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Content
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Display ordering
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    articles: Mapped[list[HelpArticle]] = relationship(
        "HelpArticle", back_populates="category"
    )
    faqs: Mapped[list[HelpFaq]] = relationship("HelpFaq", back_populates="category")

    __table_args__ = (
        Index(
            "uq_help_category_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<HelpCategory {self.name}>"


class HelpArticle(Base):
    """
    Help articles with rich content support.

    Multi-tenancy: NULL organization_id = platform-wide, UUID = org-specific.
    Supports draft/published workflow and markdown content.
    """

    __tablename__ = "help_article"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy: NULL = platform-wide, UUID = org-specific
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Category relationship
    category_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("help_category.id"), nullable=False, index=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        Enum("draft", "published", name="help_article_status"),
        nullable=False,
        default="draft",
        index=True,
    )

    # Publishing
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Media
    featured_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Display ordering
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Creator
    created_by_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="help_articles"
    )
    category: Mapped[HelpCategory] = relationship(
        "HelpCategory", back_populates="articles"
    )
    created_by: Mapped[User] = relationship("User")

    __table_args__ = (
        Index("idx_help_article_org_status", "organization_id", "status"),
        Index("idx_help_article_category_status", "category_id", "status"),
        Index(
            "idx_help_article_category_status_order",
            "category_id",
            "status",
            "display_order",
        ),
        Index(
            "uq_help_article_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        scope = "platform-wide" if self.organization_id is None else "org-specific"
        return f"<HelpArticle {self.title} ({scope}, {self.status})>"


class HelpFaq(Base):
    """
    Frequently Asked Questions.

    Multi-tenancy: NULL organization_id = platform-wide, UUID = org-specific.
    Supports draft/published workflow and display ordering.
    """

    __tablename__ = "help_faq"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy: NULL = platform-wide, UUID = org-specific
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Content
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Category relationship
    category_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("help_category.id"), nullable=False, index=True
    )

    # Display ordering
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        Enum("draft", "published", name="help_faq_status"),
        nullable=False,
        default="draft",
        index=True,
    )

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="help_faqs"
    )
    category: Mapped[HelpCategory] = relationship("HelpCategory", back_populates="faqs")

    __table_args__ = (
        Index("idx_help_faq_org_status", "organization_id", "status"),
        Index(
            "idx_help_faq_category_status_order",
            "category_id",
            "status",
            "display_order",
        ),
    )

    def __repr__(self) -> str:
        scope = "platform-wide" if self.organization_id is None else "org-specific"
        return f"<HelpFaq {self.question[:50]}... ({scope}, {self.status})>"
