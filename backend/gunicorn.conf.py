"""backend/gunicorn.conf.py - Gunicorn WSGI Production Server Configuration."""

from __future__ import annotations

import os

workers = 2
threads = 4
worker_class = "gthread"
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"


def on_starting(server: object) -> None:
    """Run database initialization and schema migration once on master process startup."""
    try:
        from backend.database import init_db

        init_db()
        if hasattr(server, "log"):
            server.log.info("Database schema initialized and verified.")
    except Exception as e:
        if hasattr(server, "log"):
            server.log.warning(f"init_db on_starting failed: {e}")

