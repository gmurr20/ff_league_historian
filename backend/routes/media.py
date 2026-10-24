"""backend/routes/media.py - Media Asset Streaming Endpoint.

Purpose:
    Serves archived custom team logos and manager avatars directly from Postgres/SQLite
    with permanent public caching headers and ETag support.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify

from backend.database import SessionLocal
from backend.models.media import MediaAsset

media_bp = Blueprint("media", __name__)


@media_bp.route("/media/<asset_id>", methods=["GET"])
def get_media_asset(asset_id: str) -> tuple[Any, int] | Response:
    """Stream archived media asset bytes from database."""
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        asset = session.query(MediaAsset).filter_by(id=asset_id).first()
        if not asset:
            return (
                jsonify(
                    {
                        "error": "NOT_FOUND",
                        "message": f"Media asset '{asset_id}' not found",
                    }
                ),
                404,
            )

        resp = Response(asset.data, mimetype=asset.content_type)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        resp.headers["ETag"] = f'"{asset.id}"'
        return resp
