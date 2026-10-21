"""backend/models/raw_snapshot.py - Raw ESPN API Snapshot Model.

Purpose:
    Stores immutable raw JSON responses from ESPN Fantasy API views for zero-network
    re-parsing and deterministic offline testing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.common import JsonType


class RawEspnSnapshot(Base):
    """Raw ESPN API response archive keyed by season, view name, and scoring period."""

    __tablename__ = "raw_espn_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    view_name: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any] | list[Any]] = mapped_column(JsonType, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "view_name",
            "scoring_period",
            name="uq_raw_espn_snapshots_season_view_period",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RawEspnSnapshot id={self.id} season={self.season_year} "
            f"view={self.view_name!r} period={self.scoring_period}>"
        )
