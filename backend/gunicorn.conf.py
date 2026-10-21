"""backend/gunicorn.conf.py - Gunicorn WSGI Production Server Configuration."""

from __future__ import annotations

import os

workers = 2
threads = 4
worker_class = "gthread"
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
