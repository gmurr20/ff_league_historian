"""backend/routes - REST API Blueprints.

Purpose:
    Exports all modular route blueprints serving the read-only REST API endpoints.
"""

from __future__ import annotations

from backend.routes.earnings import earnings_bp
from backend.routes.hall_of_fame import hall_of_fame_bp
from backend.routes.meta import meta_bp
from backend.routes.standings import standings_bp
from backend.routes.trades import trades_bp
from backend.routes.transactions import transactions_bp

__all__ = [
    "meta_bp",
    "earnings_bp",
    "standings_bp",
    "hall_of_fame_bp",
    "trades_bp",
    "transactions_bp",
]
