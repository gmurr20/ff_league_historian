"""backend/jobs/media_downloader.py - Custom Avatar & Logo Media Downloader.

Purpose:
    Downloads private/custom avatar and logo images from ESPN (e.g. mystique-api)
    using authenticated session cookies, archives them in the media_assets table,
    and returns canonical /api/v1/media/<asset_id> URLs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import requests
from sqlalchemy.orm import Session

from backend.jobs.espn_client import EspnClient
from backend.models.manager import Manager
from backend.models.media import MediaAsset
from backend.models.team import Team

logger = logging.getLogger(__name__)

# Matches ESPN private custom logo / avatar URLs
MYSTIQUE_PATTERN = re.compile(
    r"mystique-api\.fantasy\.espn\.com/apis/v1/domains/lm/images/([a-f0-9\-]+)"
)


def get_asset_id_for_url(url: str) -> str:
    """Generate a deterministic ID for an image URL.

    For ESPN mystique URLs, uses the image UUID directly.
    For any other URL, computes a 16-character SHA-256 hex digest.
    """
    match = MYSTIQUE_PATTERN.search(url)
    if match:
        return match.group(1)
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def is_custom_espn_url(url: str | None) -> bool:
    """Check if URL points to ESPN private mystique image store."""
    if not url:
        return False
    return "mystique-api.fantasy.espn.com" in url or "mystique" in url


def archive_media_asset(
    session: Session,
    url: str | None,
    http_session: requests.Session | None = None,
    cookies: dict[str, str] | None = None,
) -> str | None:
    """Download and archive a custom logo/avatar into media_assets if not already stored.

    Args:
        session: Active SQLAlchemy session.
        url: Original image URL.
        http_session: Optional requests.Session instance with auth headers.
        cookies: Optional ESPN authentication cookies (espn_s2, SWID).

    Returns:
        Canonical internal relative URL `/api/v1/media/<asset_id>`,
        or the original URL if not a custom ESPN asset or if download failed.
    """
    if not url or not is_custom_espn_url(url):
        return url

    # Already archived to internal endpoint
    if url.startswith("/api/v1/media/"):
        return url

    asset_id = get_asset_id_for_url(url)

    # 1. Check if asset already exists in media_assets (100% idempotent)
    existing = session.query(MediaAsset).filter_by(id=asset_id).first()
    if existing:
        return f"/api/v1/media/{asset_id}"

    # 2. Download from ESPN using authenticated session
    try:
        requester = http_session or requests.Session()
        req_cookies = cookies or {}
        resp = requester.get(url, cookies=req_cookies, timeout=15)
        if resp.status_code == 200 and resp.content:
            raw_content_type = resp.headers.get("Content-Type", "image/jpeg")
            clean_content_type = raw_content_type.split(";")[0].strip() or "image/jpeg"

            asset = MediaAsset(
                id=asset_id,
                original_url=url,
                content_type=clean_content_type,
                data=resp.content,
                byte_size=len(resp.content),
            )
            session.add(asset)
            session.flush()
            logger.info("Archived media asset %s (%d bytes) for %s", asset_id, len(resp.content), url)
            return f"/api/v1/media/{asset_id}"
        else:
            logger.warning(
                "Could not download custom media from %s (HTTP %s). Keeping original URL.",
                url,
                resp.status_code,
            )
            return url
    except Exception as exc:
        logger.warning("Network error downloading media from %s: %s. Keeping original URL.", url, exc)
        return url


def download_and_archive_all_league_media(
    session: Session,
    client: EspnClient | Any | None = None,
) -> int:
    """Scan all managers and teams, archiving any custom mystique images into media_assets.

    Idempotent: updates existing Manager.avatar_url and Team.logo_url to `/api/v1/media/<asset_id>`.

    Args:
        session: Active SQLAlchemy session.
        client: Optional EspnClient instance.

    Returns:
        Number of media assets newly archived or updated.
    """
    espn_client = client if isinstance(client, EspnClient) else EspnClient()
    http_session = getattr(espn_client, "http_session", requests.Session())
    cookies = espn_client._build_cookies() if hasattr(espn_client, "_build_cookies") else {}

    count = 0

    # 1. Managers with custom avatars
    managers = (
        session.query(Manager)
        .filter(Manager.avatar_url.isnot(None))
        .all()
    )
    for mgr in managers:
        if mgr.avatar_url and is_custom_espn_url(mgr.avatar_url):
            new_url = archive_media_asset(
                session, mgr.avatar_url, http_session=http_session, cookies=cookies
            )
            if new_url and new_url != mgr.avatar_url:
                mgr.avatar_url = new_url
                count += 1

    # 2. Teams with custom logos
    teams = (
        session.query(Team)
        .filter(Team.logo_url.isnot(None))
        .all()
    )
    for team in teams:
        if team.logo_url and is_custom_espn_url(team.logo_url):
            new_url = archive_media_asset(
                session, team.logo_url, http_session=http_session, cookies=cookies
            )
            if new_url and new_url != team.logo_url:
                team.logo_url = new_url
                count += 1

    session.flush()
    return count
