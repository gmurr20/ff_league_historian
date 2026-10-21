"""backend/models/manager.py - Canonical Human Manager Model.

Purpose:
    Represents persistent human managers participating across seasons, resolving
    account churn, co-management, and historical alias overrides.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.earnings import EarningsLedger
    from backend.models.team import Team


class Manager(Base):
    """Canonical human manager identity participating in the league."""

    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espn_member_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    teams: Mapped[list[Team]] = relationship(
        "Team", foreign_keys="Team.manager_id", back_populates="manager"
    )
    co_managed_teams: Mapped[list[Team]] = relationship(
        "Team", foreign_keys="Team.co_manager_id", back_populates="co_manager"
    )
    earnings_entries: Mapped[list[EarningsLedger]] = relationship(
        "EarningsLedger", back_populates="manager", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Manager id={self.id} name={self.display_name!r} guid={self.espn_member_id!r}>"
