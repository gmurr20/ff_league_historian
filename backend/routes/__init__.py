"""backend/routes - REST API Blueprints.

Purpose:
    Exports all modular route blueprints serving the read-only REST API endpoints.
"""

from __future__ import annotations

from backend.routes.earnings import earnings_bp
from backend.routes.history import history_bp
from backend.routes.meta import meta_bp
from backend.routes.standings import standings_bp
from backend.routes.trades import trades_bp
from backend.routes.transactions import transactions_bp

__all__ = [
    "meta_bp",
    "earnings_bp",
    "standings_bp",
    "history_bp",
    "trades_bp",
    "transactions_bp",
]
