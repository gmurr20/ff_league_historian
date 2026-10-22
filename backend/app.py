"""backend/app.py - Flask Application Factory.

Purpose:
    Initializes and configures the read-only Flask REST API server with CORS,
    strict caching headers, dependency-injected session factories, and error handlers.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from backend.config import config_by_name
from backend.database import SessionLocal, init_db
from backend.routes import (
    earnings_bp,
    hall_of_fame_bp,
    meta_bp,
    standings_bp,
    trades_bp,
    transactions_bp,
)

load_dotenv()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)

    # Load configuration
    env_name = os.getenv("FLASK_ENV", "default")
    config_cls = config_by_name.get(env_name, config_by_name["default"])
    app.config.from_object(config_cls)

    # Apply test config overrides if provided
    if test_config:
        app.config.update(test_config)

    # Configure session factory (default to database.SessionLocal)
    if "SESSION_FACTORY" not in app.config:
        app.config["SESSION_FACTORY"] = SessionLocal

    # Enable CORS for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints under canonical /api/v1 prefix
    app.register_blueprint(meta_bp, url_prefix="/api/v1")
    app.register_blueprint(earnings_bp, url_prefix="/api/v1")
    app.register_blueprint(standings_bp, url_prefix="/api/v1")
    app.register_blueprint(hall_of_fame_bp, url_prefix="/api/v1")
    app.register_blueprint(trades_bp, url_prefix="/api/v1")
    app.register_blueprint(transactions_bp, url_prefix="/api/v1")

    # Cache-Control hook for successful GET requests
    @app.after_request
    def set_caching_headers(response: Response) -> Response:
        if (
            request.method == "GET"
            and request.path.startswith("/api/v1/")
            and 200 <= response.status_code < 400
        ):
            response.headers["Cache-Control"] = "public, max-age=60"
        return response

    # Global JSON error handlers
    @app.errorhandler(400)
    def bad_request(error: Any) -> tuple[Response, int]:
        msg = getattr(error, "description", "Bad Request")
        return jsonify({"error": "BAD_REQUEST", "message": msg}), 400

    @app.errorhandler(404)
    def not_found(error: Any) -> tuple[Response, int]:
        msg = getattr(error, "description", "Resource Not Found")
        return jsonify({"error": "NOT_FOUND", "message": msg}), 404

    @app.errorhandler(500)
    def internal_error(error: Any) -> tuple[Response, int]:
        msg = getattr(error, "description", "Internal Server Error")
        return jsonify({"error": "INTERNAL_SERVER_ERROR", "message": msg}), 500

    return app


# Module-level instance for WSGI servers (Gunicorn)
app = create_app()

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port)
