"""backend/jobs/espn_client.py - ESPN Fantasy API HTTP Client & League Discoverer.

Purpose:
    Handles authenticated communication with ESPN Fantasy Football endpoints
    (modern v3 and legacy), parses authentication cookies, manages query parameters
    and x-fantasy-filter headers, and handles access errors gracefully.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EspnAccessError(Exception):
    """Raised when ESPN Fantasy API returns an access error (401, 403, 404)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


def get_configured_league_ids() -> list[str]:
    """Parse configured league IDs from ESPN_LEAGUE_IDS or ESPN_LEAGUE_ID environment variables.

    Returns:
        List of distinct league ID strings. Defaults to ["12345678"] if unset.
    """
    load_dotenv()
    league_ids_raw = os.getenv("ESPN_LEAGUE_IDS", "")
    single_id = os.getenv("ESPN_LEAGUE_ID", "")

    ids: list[str] = []
    if league_ids_raw:
        for item in league_ids_raw.split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in ids:
                ids.append(cleaned)

    if single_id:
        cleaned_single = single_id.strip()
        if cleaned_single and cleaned_single not in ids:
            ids.append(cleaned_single)

    return ids or ["12345678"]


class EspnClient:
    """Client for querying ESPN Fantasy Football API (v3 modern and legacy)."""

    MODERN_URL_TEMPLATE = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"
    )
    LEGACY_URL_TEMPLATE = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory/{league_id}?seasonId={year}"
    )

    def __init__(
        self,
        league_id: str | None = None,
        espn_s2: str | None = None,
        swid: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        load_dotenv()
        configured_ids = get_configured_league_ids()
        self.league_id = str(league_id or configured_ids[0])

        raw_s2 = espn_s2 if espn_s2 is not None else os.getenv("ESPN_S2", "")
        # Normalize: if already URL-encoded, unquote once to allow clean cookie jar handling
        self.espn_s2 = unquote(raw_s2) if "%" in raw_s2 else raw_s2
        self.swid = swid if swid is not None else os.getenv("ESPN_SWID", "")
        self.http_session = session or requests.Session()

    def _build_headers(self, x_fantasy_filter: dict[str, Any] | None = None) -> dict[str, str]:
        """Construct standard HTTP headers and optional x-fantasy-filter JSON."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        if x_fantasy_filter:
            headers["x-fantasy-filter"] = json.dumps(x_fantasy_filter)
        return headers

    def _build_cookies(self) -> dict[str, str]:
        """Construct session authentication cookies."""
        cookies: dict[str, str] = {}
        if self.espn_s2:
            cookies["espn_s2"] = self.espn_s2
        if self.swid:
            cookies["SWID"] = self.swid
        return cookies

    def fetch_league(
        self,
        season_year: int,
        views: list[str] | None = None,
        x_fantasy_filter: dict[str, Any] | None = None,
        allow_inaccessible: bool = True,
        league_id: str | None = None,
        scoring_period_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Fetch league payload for a given season.

        Args:
            season_year: Season year (e.g. 2023).
            views: List of ESPN API views (e.g. ['mSettings', 'mTeam', 'mMatchupScore']).
            x_fantasy_filter: Optional filter dict passed as x-fantasy-filter JSON header.
            allow_inaccessible: If True, returns None on 401/403/404 instead of raising.
            league_id: League ID override. Defaults to self.league_id.
            scoring_period_id: Optional ESPN scoringPeriodId query parameter.

        Returns:
            Dictionary containing league payload, or None if inaccessible and allow_inaccessible=True.

        Raises:
            EspnAccessError: If ESPN responds with 401, 403, or 404 and allow_inaccessible is False.
            requests.RequestException: On underlying connection or transport failure.
        """
        target_league_id = league_id or self.league_id

        # Modern vs Legacy URL selection
        if season_year < 2018:
            url = self.LEGACY_URL_TEMPLATE.format(league_id=target_league_id, year=season_year)
        else:
            url = self.MODERN_URL_TEMPLATE.format(year=season_year, league_id=target_league_id)

        params: list[tuple[str, str]] = []
        if scoring_period_id is not None:
            params.append(("scoringPeriodId", str(scoring_period_id)))
        if views:
            for v in views:
                params.append(("view", v))

        headers = self._build_headers(x_fantasy_filter=x_fantasy_filter)
        cookies = self._build_cookies()

        try:
            resp = self.http_session.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.error("HTTP request to ESPN API failed: %s", exc)
            raise

        if resp.status_code in (401, 403, 404):
            err_msg = (
                f"ESPN API access denied or not found (HTTP {resp.status_code}) for "
                f"league {target_league_id}, season {season_year}."
            )
            if allow_inaccessible:
                logger.warning(
                    "%s Continuing with accessible seasons (allow_inaccessible=True).",
                    err_msg,
                )
                return None
            raise EspnAccessError(
                err_msg,
                status_code=resp.status_code,
                response_text=resp.text,
            )

        if not resp.ok:
            resp.raise_for_status()

        data = resp.json()
        # Legacy endpoint returns a list with single item [ { ... } ]
        if isinstance(data, list):
            if not data:
                return None
            return data[0]
        if isinstance(data, dict):
            return data
        return None
