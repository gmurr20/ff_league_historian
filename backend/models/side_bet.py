"""backend/models/side_bet.py - Commissioner & Peer-to-Peer Side Bet Model.

Purpose:
    Represents 1v1 and NvM group fantasy side bets for a specific season and week,
    persisting canonical espn_team_id arrays, point spreads, stakes, and scoring modes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.common import JsonType


class SideBet(Base):
    """Side bet entity supporting 1v1 and group matchups with point spreads and stakes."""

    __tablename__ = "side_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bet_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    side_a_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Side A")
    side_b_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Side B")
    side_a_espn_team_ids: Mapped[list[int]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    side_b_espn_team_ids: Mapped[list[int]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    spread_side_a: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=Decimal("0.00")
    )
    stake_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    stake_description: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    scoring_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTERS")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_side_bets_season_week", "season_year", "week"),
    )

    def __repr__(self) -> str:
        return (
            f"<SideBet id={self.id} uuid={self.bet_uuid!r} "
            f"season={self.season_year} week={self.week} "
            f"title={self.title!r} spread={self.spread_side_a} stake={self.stake_amount}>"
        )
