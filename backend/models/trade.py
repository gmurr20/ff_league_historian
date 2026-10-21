"""backend/models/trade.py - Bilateral Trade Model.

Purpose:
    Represents completed two-team franchise trades with FAAB transfers for
    Trade Autopsies, Trade Networks, and Post-Acquisition starter point tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.season import Season
    from backend.models.team import Team


class Trade(Base):
    """Bilateral trade agreement capturing exchanged assets and FAAB dollars."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    espn_transaction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    proposing_team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    accepting_team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="EXECUTED")
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    faab_from_proposer: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    faab_from_accepter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trade_summary: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "espn_transaction_id",
            name="uq_trades_season_espn_tx",
        ),
    )

    # Relationships
    season: Mapped[Season] = relationship("Season", back_populates="trades")
    proposing_team: Mapped[Team] = relationship(
        "Team", foreign_keys=[proposing_team_id], back_populates="proposed_trades"
    )
    accepting_team: Mapped[Team] = relationship(
        "Team", foreign_keys=[accepting_team_id], back_populates="accepted_trades"
    )

    def __repr__(self) -> str:
        return (
            f"<Trade id={self.id} season={self.season_year} week={self.week} "
            f"proposer={self.proposing_team_id} accepter={self.accepting_team_id} status={self.status!r}>"
        )
