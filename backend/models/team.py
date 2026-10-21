"""backend/models/team.py - Annual Franchise Team Model.

Purpose:
    Represents an annual team instance in a specific season, connecting the canonical
    human manager to seasonal records, statistics, divisional alignments, and FAAB balances.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.earnings import EarningsLedger
    from backend.models.lineup import WeeklyLineup
    from backend.models.manager import Manager
    from backend.models.matchup import Matchup
    from backend.models.season import Season
    from backend.models.trade import Trade
    from backend.models.transaction import Transaction


class Team(Base):
    """Annual franchise instance linking a manager to yearly standings and statistics."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    espn_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    team_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team_abbrev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_id: Mapped[int] = mapped_column(Integer, ForeignKey("managers.id"), nullable=False)
    co_manager_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("managers.id"), nullable=True
    )
    raw_owner_guids: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    division_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    division_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    division_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    division_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    division_ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points_for: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    points_against: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    streak_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    streak_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    playoff_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_standing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faab_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    waiver_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquisitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ir_moves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("season_year", "espn_team_id", name="uq_teams_season_espn_team"),
    )

    # Relationships
    season: Mapped[Season] = relationship("Season", back_populates="teams")
    manager: Mapped[Manager] = relationship(
        "Manager", foreign_keys=[manager_id], back_populates="teams"
    )
    co_manager: Mapped[Manager | None] = relationship(
        "Manager", foreign_keys=[co_manager_id], back_populates="co_managed_teams"
    )
    home_matchups: Mapped[list[Matchup]] = relationship(
        "Matchup", foreign_keys="Matchup.home_team_id", back_populates="home_team"
    )
    away_matchups: Mapped[list[Matchup]] = relationship(
        "Matchup", foreign_keys="Matchup.away_team_id", back_populates="away_team"
    )
    weekly_lineups: Mapped[list[WeeklyLineup]] = relationship(
        "WeeklyLineup", back_populates="team", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", foreign_keys="Transaction.team_id", back_populates="team"
    )
    proposed_trades: Mapped[list[Trade]] = relationship(
        "Trade", foreign_keys="Trade.proposing_team_id", back_populates="proposing_team"
    )
    accepted_trades: Mapped[list[Trade]] = relationship(
        "Trade", foreign_keys="Trade.accepting_team_id", back_populates="accepting_team"
    )
    earnings_entries: Mapped[list[EarningsLedger]] = relationship(
        "EarningsLedger", back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Team id={self.id} season={self.season_year} "
            f"name={self.team_name!r} manager_id={self.manager_id}>"
        )
