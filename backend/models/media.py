"""backend/models/media.py - Media Asset Model for Archived Avatars & Logos.

Purpose:
    Stores downloaded custom avatars and logos as binary assets in Postgres/SQLite
    to avoid client-side 401 authentication errors and ESPN CDN link rot.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MediaAsset(Base):
    """Archived media asset (custom logo/avatar image) keyed by deterministic URL hash."""

    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_url: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/jpeg")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MediaAsset id={self.id!r} size={self.byte_size} bytes content_type={self.content_type!r}>"
