"""backend/models/matchup.py - Weekly Matchup & Team Scores Model.

Purpose:
    Represents weekly games across regular season, championship brackets, consolation
    ladders, and playoff bye weeks with Max PF and bench points.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.season import Season
    from backend.models.team import Team


class Matchup(Base):
    """Weekly matchup entity capturing scores, projections, Max PF, and bye weeks."""

    __tablename__ = "matchups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    espn_matchup_id: Mapped[int] = mapped_column(Integer, nullable=False)
    matchup_type: Mapped[str] = mapped_column(String(32), nullable=False, default="REGULAR")
    home_team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    away_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    home_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    away_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    home_projected: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    away_projected: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    home_optimal_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    away_optimal_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    home_bench_points: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    away_bench_points: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    winner_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    is_tie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_by_scoring_period: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "week",
            "espn_matchup_id",
            name="uq_matchups_season_week_espn_matchup",
        ),
    )

    # Relationships
    season: Mapped[Season] = relationship("Season", back_populates="matchups")
    home_team: Mapped[Team] = relationship(
        "Team", foreign_keys=[home_team_id], back_populates="home_matchups"
    )
    away_team: Mapped[Team | None] = relationship(
        "Team", foreign_keys=[away_team_id], back_populates="away_matchups"
    )
    winner_team: Mapped[Team | None] = relationship("Team", foreign_keys=[winner_team_id])

    def __repr__(self) -> str:
        return (
            f"<Matchup id={self.id} season={self.season_year} week={self.week} "
            f"type={self.matchup_type!r} home={self.home_team_id} away={self.away_team_id}>"
        )
