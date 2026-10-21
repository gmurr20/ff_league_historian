"""backend/jobs/payout_policy.py - Declarative Season Payout Policy Resolver.

Purpose:
    Provides declarative financial payout configurations per season year.
    Preserves historical payouts for completed legacy seasons while allowing
    ante adjustments year-over-year.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAYOUT_RULES_PATH = REPO_ROOT / "db" / "season_payout_rules.json"

DEFAULT_PAYOUT_RULES: dict[str, Decimal] = {
    "weekly_win_payout": Decimal("10.00"),
    "weekly_high_score_payout": Decimal("10.00"),
    "weekly_high_score_loss_payout": Decimal("10.00"),
    "champion_payout": Decimal("500.00"),
    "runner_up_payout": Decimal("300.00"),
    "third_place_payout": Decimal("200.00"),
    "fourth_place_payout": Decimal("150.00"),
    "fifth_place_payout": Decimal("100.00"),
    "regular_season_most_points_payout": Decimal("30.00"),
}


def load_season_payout_rules(season_year: int) -> dict[str, Decimal]:
    """Resolve financial payout parameters for a given season year.

    Preserves historical payouts via season_overrides in db/season_payout_rules.json
    and applies default ante rules when no year-specific override is declared.

    Args:
        season_year: Four-digit NFL season year (e.g. 2024).

    Returns:
        Mapping of payout parameter names to Decimal amounts.
    """
    rules = dict(DEFAULT_PAYOUT_RULES)
    if PAYOUT_RULES_PATH.is_file():
        try:
            data: dict[str, Any] = json.loads(PAYOUT_RULES_PATH.read_text(encoding="utf-8"))
            if "default" in data and isinstance(data["default"], dict):
                for k, v in data["default"].items():
                    if k in rules:
                        rules[k] = Decimal(str(v))
            overrides = data.get("season_overrides", {})
            yr_str = str(season_year)
            if yr_str in overrides and isinstance(overrides[yr_str], dict):
                for k, v in overrides[yr_str].items():
                    if k in rules:
                        rules[k] = Decimal(str(v))
        except Exception:
            pass
    return rules
