"""backend/gunicorn.conf.py - Gunicorn WSGI Production Server Configuration."""

from __future__ import annotations

import os
import threading
import time

workers = 2
threads = 4
worker_class = "gthread"
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"


def _live_score_poller_loop(server: object) -> None:
    """Background daemon in master process that syncs live ESPN scores & projections every 10 minutes."""
    interval_sec = int(os.getenv("LIVE_SYNC_INTERVAL_SECONDS", "600"))
    # Initial short delay after boot so workers start cleanly first
    time.sleep(15)
    while True:
        try:
            from backend.database import get_session
            from backend.jobs.sync_live_scores import sync_live_scores

            with get_session() as session:
                run = sync_live_scores(session=session)
                if hasattr(server, "log") and run.status == "SUCCESS":
                    server.log.info(
                        f"Background live score sync completed: season={run.season_year} "
                        f"week={run.week_range} records={run.records_processed}"
                    )
        except Exception as exc:
            if hasattr(server, "log"):
                server.log.warning(f"Background live score sync error: {exc}")
        time.sleep(interval_sec)


def on_starting(server: object) -> None:
    """Run database initialization and start background live score poller on master startup."""
    try:
        from backend.database import init_db

        init_db()
        if hasattr(server, "log"):
            server.log.info("Database schema initialized and verified.")
    except Exception as e:
        if hasattr(server, "log"):
            server.log.warning(f"init_db on_starting failed: {e}")

    if os.getenv("DISABLE_LIVE_SCORE_POLLER", "").lower() not in ("1", "true", "yes"):
        poller = threading.Thread(
            target=_live_score_poller_loop,
            args=(server,),
            name="espn-live-score-poller",
            daemon=True,
        )
        poller.start()


