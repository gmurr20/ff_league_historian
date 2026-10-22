"""backend/models/draft.py - Draft Board & Picks Model.

Purpose:
    Represents individual draft picks in the annual league draft, capturing
    overall pick order, round, round pick, drafted player, drafting franchise,
    auction bid amount, and keeper designation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.player import Player
    from backend.models.season import Season
    from backend.models.team import Team


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
