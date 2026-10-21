"""backend/models/season.py - League Season & Configuration Model.

Purpose:
    Stores annual fantasy football league settings, scoring configurations,
    financial prize parameters, and data availability flags.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.earnings import EarningsLedger
    from backend.models.lineup import WeeklyLineup
    from backend.models.matchup import Matchup
    from backend.models.team import Team
    from backend.models.trade import Trade
    from backend.models.transaction import Transaction


class Season(Base):
    """Annual league instance governing rules, payouts, and season lifecycle."""

    __tablename__ = "seasons"

    season_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[str] = mapped_column(String(64), nullable=False)
    league_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regular_season_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    current_week: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    playoff_team_count: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    playoff_matchup_length: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scoring_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PPR")
    scoring_settings: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    roster_slots: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    faab_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    weekly_win_payout: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("10.00")
    )
    champion_payout: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("600.00")
    )
    runner_up_payout: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("300.00")
    )
    third_place_payout: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("100.00")
    )
    has_transaction_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_boxscore_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    teams: Mapped[list[Team]] = relationship(
        "Team", back_populates="season", cascade="all, delete-orphan"
    )
    matchups: Mapped[list[Matchup]] = relationship(
        "Matchup", back_populates="season", cascade="all, delete-orphan"
    )
    weekly_lineups: Mapped[list[WeeklyLineup]] = relationship(
        "WeeklyLineup", back_populates="season", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="season", cascade="all, delete-orphan"
    )
    trades: Mapped[list[Trade]] = relationship(
        "Trade", back_populates="season", cascade="all, delete-orphan"
    )
    earnings_ledger: Mapped[list[EarningsLedger]] = relationship(
        "EarningsLedger", back_populates="season", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Season year={self.season_year} league={self.league_name!r} "
            f"active={self.is_active} completed={self.is_completed}>"
        )
