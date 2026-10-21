"""backend/models/earnings.py - Financial Earnings Ledger Model.

Purpose:
    Represents financial payouts for regular-season weekly wins ($10), ties ($5),
    weekly high scores ($10), weekly high scores in a loss ($10), regular-season
    most points champion ($30), and season final placement prizes (1st: $500, 2nd: $300,
    3rd: $200, 4th: $150, 5th: $100).
    Maintains dual-dialect nulls-not-distinct uniqueness across PostgreSQL 16 and SQLite.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.manager import Manager
    from backend.models.season import Season
    from backend.models.team import Team


class EarningsLedger(Base):
    """Financial earnings entry recording weekly prizes and season championship podium awards."""

    __tablename__ = "earnings_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("managers.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "manager_id",
            "season_year",
            "week",
            "entry_type",
            postgresql_nulls_not_distinct=True,
            name="uq_earnings_entry",
        ),
    )

    # Relationships
    manager: Mapped[Manager] = relationship("Manager", back_populates="earnings_entries")
    team: Mapped[Team] = relationship("Team", back_populates="earnings_entries")
    season: Mapped[Season] = relationship("Season", back_populates="earnings_ledger")

    def __repr__(self) -> str:
        return (
            f"<EarningsLedger id={self.id} manager_id={self.manager_id} "
            f"season={self.season_year} week={self.week} type={self.entry_type!r} amount={self.amount}>"
        )
