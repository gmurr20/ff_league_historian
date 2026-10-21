"""backend/models/transaction.py - Transaction & Movement Items Model.

Purpose:
    Represents league transactions (executed/failed waivers, free agent adds, drops)
    and normalized player movement items. Supports FAAB Bidding War receipts via
    related_espn_transaction_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.player import Player
    from backend.models.season import Season
    from backend.models.team import Team


class Transaction(Base):
    """Transaction record capturing waiver claims, failed bids, free agents, and drops."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoring_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    espn_transaction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    bid_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waiver_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_commissioner_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    related_espn_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_summary: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "espn_transaction_id",
            name="uq_transactions_season_espn_tx",
        ),
    )

    # Relationships
    season: Mapped[Season] = relationship("Season", back_populates="transactions")
    team: Mapped[Team | None] = relationship(
        "Team", foreign_keys=[team_id], back_populates="transactions"
    )
    items: Mapped[list[TransactionItem]] = relationship(
        "TransactionItem", back_populates="transaction", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} season={self.season_year} type={self.transaction_type!r} "
            f"status={self.status!r} bid={self.bid_amount} team_id={self.team_id}>"
        )


class TransactionItem(Base):
    """Normalized player movement item attached to a transaction."""

    __tablename__ = "transaction_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.espn_player_id"), nullable=False
    )
    from_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    to_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Relationships
    transaction: Mapped[Transaction] = relationship("Transaction", back_populates="items")
    player: Mapped[Player] = relationship("Player", back_populates="transaction_items")
    from_team: Mapped[Team | None] = relationship("Team", foreign_keys=[from_team_id])
    to_team: Mapped[Team | None] = relationship("Team", foreign_keys=[to_team_id])

    def __repr__(self) -> str:
        return (
            f"<TransactionItem id={self.id} tx={self.transaction_id} "
            f"player={self.player_id} type={self.item_type!r}>"
        )
