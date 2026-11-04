"""backend/models/draft.py - Draft Board, Draft Settings & Traded Pick Models.

Purpose:
    - DraftPick: individual selections in the annual league draft, capturing
      overall pick order, round, round pick, drafted player, drafting franchise,
      auction bid amount, and keeper designation.
    - DraftSettings: ESPN `settings.draftSettings` per season (snake/auction type,
      round-1 pick order by franchise slot, keeper count, draft date). Required to
      map an overall pick number back to the franchise that originally owned it.
    - TradedDraftPick: canonical identity of a traded draft pick
      (draft_year, round, original franchise slot) attached to the TransactionItem
      that moved it. Lets the draft board follow a specific team's pick as it is
      re-traded across seasons.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.common import JsonType

if TYPE_CHECKING:
    from backend.models.player import Player
    from backend.models.season import Season
    from backend.models.team import Team
    from backend.models.transaction import TransactionItem


class DraftSettings(Base):
    """ESPN draft configuration for a season (pick order, type, keepers, date)."""

    __tablename__ = "draft_settings"

    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), primary_key=True
    )
    draft_type: Mapped[str] = mapped_column(String(32), nullable=False, default="SNAKE")
    order_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Round-1 order expressed as ESPN franchise slots (espn_team_id).
    pick_order: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    keeper_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draft_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_drafted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_settings: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)

    def __repr__(self) -> str:
        return (
            f"<DraftSettings season={self.season_year} type={self.draft_type!r} "
            f"order={self.pick_order}>"
        )


class TradedDraftPick(Base):
    """Identity of a draft pick moved by a trade item (tied to its original franchise)."""

    __tablename__ = "traded_draft_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("transaction_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    draft_year: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    # ESPN franchise slot (espn_team_id) that originally owned the pick. NULL means
    # "not recorded" and is inferred at read time from pick ownership.
    original_espn_team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_pick: Mapped[int | None] = mapped_column(Integer, nullable=True)

    transaction_item: Mapped[TransactionItem] = relationship(
        "TransactionItem", back_populates="traded_pick"
    )

    __table_args__ = (
        Index(
            "idx_traded_draft_picks_identity", "draft_year", "round", "original_espn_team_id"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TradedDraftPick year={self.draft_year} round={self.round} "
            f"original={self.original_espn_team_id} overall={self.overall_pick}>"
        )


class DraftPick(Base):
    """Individual draft pick selection on the league draft board."""

    __tablename__ = "draft_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.season_year", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    round_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.espn_player_id"), nullable=False
    )
    bid_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nominating_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    is_keeper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lineup_slot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_draft_type_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    season: Mapped[Season] = relationship("Season", foreign_keys=[season_year])
    team: Mapped[Team] = relationship("Team", foreign_keys=[team_id])
    nominating_team: Mapped[Team | None] = relationship("Team", foreign_keys=[nominating_team_id])
    player: Mapped[Player] = relationship("Player", foreign_keys=[player_id])

    __table_args__ = (
        UniqueConstraint("season_year", "overall_pick", name="uq_draft_picks_season_overall"),
    )
