"""backend/models/sync_run.py - Ingestion Job Audit Run Model.

Purpose:
    Audit trail recording historical backfill runs and active weekly cron executions,
    processing counts, week ranges, and error messages.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class SyncRun(Base):
    """Audit record for ingestion jobs (BACKFILL or WEEKLY_CRON)."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    season_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_range: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SyncRun id={self.id} type={self.run_type!r} "
            f"season={self.season_year} status={self.status!r}>"
        )
