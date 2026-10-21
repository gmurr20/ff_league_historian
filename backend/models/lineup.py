"""backend/models/lineup.py - Weekly Boxscore Lineup Model.

Purpose:
    Represents weekly player start/sit entries per team with projected and actual fantasy
    points, enabling Trade Autopsies, Coaching Lineup Efficiency, and Position Crowns.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.player import Player
    from backend.models.season import Season
    from backend.models.team import Team


class WeeklyLineup(Base):
    """Weekly player-level start/sit entry for a franchise."""

    __tablename__ = "weekly_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.espn_player_id"), nullable=False
    )
    slot_position: Mapped[str] = mapped_column(String(16), nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actual_points: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    projected_points: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    acquisition_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weekly_stats: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "week",
            "team_id",
            "player_id",
            name="uq_weekly_lineups_season_week_team_player",
        ),
    )

    # Relationships
    season: Mapped[Season] = relationship("Season", back_populates="weekly_lineups")
    team: Mapped[Team] = relationship("Team", back_populates="weekly_lineups")
    player: Mapped[Player] = relationship("Player", back_populates="weekly_lineups")

    def __repr__(self) -> str:
        return (
            f"<WeeklyLineup id={self.id} season={self.season_year} week={self.week} "
            f"team_id={self.team_id} player_id={self.player_id} starter={self.is_starter}>"
        )
