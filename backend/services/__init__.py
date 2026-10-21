"""backend/services - Read-Only Query Services.

Purpose:
    Exports domain-specific read-only query services implementing the canonical
    REST API contract specifications.
"""

from __future__ import annotations

from backend.services.earnings_service import get_earnings_leaderboard
from backend.services.history_service import get_head_to_head
from backend.services.meta_service import get_health, get_meta
from backend.services.standings_service import get_standings
from backend.services.trades_service import get_trades_trends
from backend.services.transactions_service import get_transactions_summary

__all__ = [
    "get_health",
    "get_meta",
    "get_earnings_leaderboard",
    "get_standings",
    "get_head_to_head",
    "get_trades_trends",
    "get_transactions_summary",
]
