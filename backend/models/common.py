"""backend/models/common.py - Common ORM Column Types & Utilities.

Purpose:
    Provides cross-dialect JSON/JSONB column abstractions and common model helpers.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Cross-dialect JSON column type: persists as binary JSONB on PostgreSQL 16
# and standard JSON text on SQLite.
JsonType = JSON().with_variant(JSONB, "postgresql")
