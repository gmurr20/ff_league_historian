"""backend/routes/meta.py - System Health & League Metadata Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify

from backend.database import SessionLocal
from backend.services.meta_service import get_health, get_meta

meta_bp = Blueprint("meta", __name__)


@meta_bp.route("/health", methods=["GET"])
def health() -> tuple[Any, int]:
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        payload, status_code = get_health(session)
        return jsonify(payload), status_code


@meta_bp.route("/meta", methods=["GET"])
def meta() -> tuple[Any, int]:
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        payload = get_meta(session)
        return jsonify(payload), 200
