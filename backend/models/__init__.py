"""backend/models - SQLAlchemy 2.0 ORM Models for Fantasy Football League Historian.

Purpose:
    Exports all 12 canonical ORM models representing the maximal ESPN data strategy
    with dual PostgreSQL 16 / SQLite dialect compatibility.
"""

from __future__ import annotations

from backend.models.common import JsonType
from backend.models.earnings import EarningsLedger
from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.sync_run import SyncRun
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import Transaction, TransactionItem

__all__ = [
    "JsonType",
    "RawEspnSnapshot",
    "Season",
    "Manager",
    "Team",
    "Player",
    "Matchup",
    "WeeklyLineup",
    "Transaction",
    "TransactionItem",
    "Trade",
    "EarningsLedger",
    "SyncRun",
]
