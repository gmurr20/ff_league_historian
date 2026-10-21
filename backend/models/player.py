"""backend/models/player.py - Canonical NFL Player Model.

Purpose:
    Represents master NFL player records referenced across rosters, weekly lineups,
    waiver claims, and bilateral trades.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.lineup import WeeklyLineup
    from backend.models.transaction import TransactionItem


class Player(Base):
    """Canonical NFL player entity with position and team metadata."""

    __tablename__ = "players"

    espn_player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_position: Mapped[str] = mapped_column(String(16), nullable=False)
    pro_team: Mapped[str] = mapped_column(String(16), nullable=False, default="FA")
    headshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    weekly_lineups: Mapped[list[WeeklyLineup]] = relationship(
        "WeeklyLineup", back_populates="player"
    )
    transaction_items: Mapped[list[TransactionItem]] = relationship(
        "TransactionItem", back_populates="player"
    )

    def __repr__(self) -> str:
        return (
            f"<Player id={self.espn_player_id} name={self.full_name!r} "
            f"pos={self.default_position!r} team={self.pro_team!r}>"
        )
