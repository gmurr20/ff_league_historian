"""backend/services/history_service.py - Head-to-Head Rivalry Query Service.

Purpose:
    Computes career head-to-head records across franchises and canonical managers.
    Enforces Critical Guardrail #4: Excludes consolation ladder games and playoff byes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.team import Team


def get_head_to_head(
    session: Session,
    manager_a_id: int | None = None,
    manager_b_id: int | None = None,
) -> dict[str, Any]:
    """Calculate career rivalry matrix and pairwise comparative deep-dive."""
    managers = session.query(Manager).order_by(Manager.display_name.asc()).all()
    mgr_map = {m.id: m.display_name for m in managers}
    mgr_avatar_map = {m.id: m.avatar_url for m in managers}

    # Pre-fetch all teams to resolve team_id -> (manager_id, team_name, logo_url)
    teams = session.query(Team).order_by(Team.season_year.desc(), Team.id.desc()).all()
    team_info: dict[int, tuple[int, str, str | None]] = {
        t.id: (t.manager_id, t.team_name, t.logo_url) for t in teams
    }
    latest_team_by_mgr: dict[int, Team] = {}
    for t in teams:
        if t.manager_id not in latest_team_by_mgr:
            latest_team_by_mgr[t.manager_id] = t

    mgr_ref_list = [
        {
            "manager_id": m.id,
            "display_name": m.display_name,
            "team_name": (
                latest_team_by_mgr[m.id].team_name
                if m.id in latest_team_by_mgr
                else m.display_name
            ),
            "avatar_url": (
                latest_team_by_mgr[m.id].logo_url
                if m.id in latest_team_by_mgr and latest_team_by_mgr[m.id].logo_url
                else m.avatar_url
            ),
        }
        for m in managers
    ]
    mgr_ref_map = {item["manager_id"]: item for item in mgr_ref_list}

    # CRITICAL GUARDRAIL #4: Filter completed matchups in REGULAR or WINNERS_BRACKET only
    valid_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.matchup_type.in_(["REGULAR", "WINNERS_BRACKET"]),
            Matchup.away_team_id.isnot(None),
            Matchup.is_completed.is_(True),
        )
        .order_by(Matchup.season_year.asc(), Matchup.week.asc())
        .all()
    )

    # Accumulate head-to-head stats across all pairs (manager_a_id, manager_b_id)
    pair_stats: dict[tuple[int, int], dict[str, Any]] = {}

    for m in valid_matchups:
        if m.away_team_id is None:
            continue
        h_info = team_info.get(m.home_team_id)
        a_info = team_info.get(m.away_team_id)
        if not h_info or not a_info:
            continue

        h_mgr_id, _, _ = h_info
        a_mgr_id, _, _ = a_info
        if h_mgr_id == a_mgr_id:
            continue

        h_score = float(m.home_score)
        a_score = float(m.away_score)

        # Initialize pair stats if needed
        for p1, p2 in [(h_mgr_id, a_mgr_id), (a_mgr_id, h_mgr_id)]:
            if (p1, p2) not in pair_stats:
                pair_stats[(p1, p2)] = {
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "points_for": 0.0,
                    "points_against": 0.0,
                    "total_games": 0,
                }

        # Update Home perspective
        pair_stats[(h_mgr_id, a_mgr_id)]["total_games"] += 1
        pair_stats[(h_mgr_id, a_mgr_id)]["points_for"] += h_score
        pair_stats[(h_mgr_id, a_mgr_id)]["points_against"] += a_score

        # Update Away perspective
        pair_stats[(a_mgr_id, h_mgr_id)]["total_games"] += 1
        pair_stats[(a_mgr_id, h_mgr_id)]["points_for"] += a_score
        pair_stats[(a_mgr_id, h_mgr_id)]["points_against"] += h_score

        if m.is_tie or h_score == a_score:
            pair_stats[(h_mgr_id, a_mgr_id)]["ties"] += 1
            pair_stats[(a_mgr_id, h_mgr_id)]["ties"] += 1
        elif h_score > a_score:
            pair_stats[(h_mgr_id, a_mgr_id)]["wins"] += 1
            pair_stats[(a_mgr_id, h_mgr_id)]["losses"] += 1
        else:
            pair_stats[(h_mgr_id, a_mgr_id)]["losses"] += 1
            pair_stats[(a_mgr_id, h_mgr_id)]["wins"] += 1

    # Build full matrix entries
    matrix: list[dict[str, Any]] = []
    for (m_a, m_b), stats in pair_stats.items():
        total = stats["total_games"]
        win_pct = round((stats["wins"] + 0.5 * stats["ties"]) / total, 3) if total > 0 else 0.0
        matrix.append(
            {
                "manager_a_id": m_a,
                "manager_a_name": mgr_map.get(m_a, ""),
                "manager_b_id": m_b,
                "manager_b_name": mgr_map.get(m_b, ""),
                "wins": stats["wins"],
                "losses": stats["losses"],
                "ties": stats["ties"],
                "win_pct": win_pct,
                "points_for": round(stats["points_for"], 2),
                "points_against": round(stats["points_against"], 2),
                "total_games": total,
            }
        )

    matrix.sort(key=lambda x: (x["manager_a_name"].lower(), x["manager_b_name"].lower()))

    # Build deep pairwise details if both manager IDs are provided and distinct
    pair_detail: dict[str, Any] | None = None
    if manager_a_id is not None and manager_b_id is not None and manager_a_id != manager_b_id:
        reg_split = {"a_wins": 0, "b_wins": 0, "ties": 0, "a_points": 0.0, "b_points": 0.0}
        play_split = {"a_wins": 0, "b_wins": 0, "ties": 0, "a_points": 0.0, "b_points": 0.0}

        pairwise_games: list[dict[str, Any]] = []
        biggest_blowout: dict[str, Any] | None = None
        closest_game: dict[str, Any] | None = None
        max_margin = -1.0
        min_margin = float("inf")

        for m in valid_matchups:
            if m.away_team_id is None:
                continue
            h_info = team_info.get(m.home_team_id)
            a_info = team_info.get(m.away_team_id)
            if not h_info or not a_info:
                continue

            h_mgr_id, h_name, h_logo = h_info
            a_mgr_id, a_name, a_logo = a_info

            # Check if this matchup involves both specified managers
            is_match = (h_mgr_id == manager_a_id and a_mgr_id == manager_b_id) or (
                h_mgr_id == manager_b_id and a_mgr_id == manager_a_id
            )
            if not is_match:
                continue

            is_a_home = h_mgr_id == manager_a_id
            a_score = float(m.home_score if is_a_home else m.away_score)
            b_score = float(m.away_score if is_a_home else m.home_score)
            a_team_name = h_name if is_a_home else a_name
            b_team_name = a_name if is_a_home else h_name
            a_logo_url = (h_logo if is_a_home else a_logo) or mgr_avatar_map.get(manager_a_id)
            b_logo_url = (a_logo if is_a_home else h_logo) or mgr_avatar_map.get(manager_b_id)

            winner_id: int | None = None
            if a_score > b_score:
                winner_id = manager_a_id
            elif b_score > a_score:
                winner_id = manager_b_id

            split_target = reg_split if m.matchup_type == "REGULAR" else play_split
            split_target["a_points"] += a_score
            split_target["b_points"] += b_score

            if m.is_tie or a_score == b_score:
                split_target["ties"] += 1
            elif a_score > b_score:
                split_target["a_wins"] += 1
            else:
                split_target["b_wins"] += 1

            # Blowout / closest highlights (only for decisive games)
            margin = round(abs(a_score - b_score), 2)
            if winner_id is not None:
                winner_score = max(a_score, b_score)
                loser_score = min(a_score, b_score)
                highlight_data = {
                    "season_year": m.season_year,
                    "week": m.week,
                    "matchup_type": m.matchup_type,
                    "winner_manager_id": winner_id,
                    "winner_name": mgr_map.get(winner_id, ""),
                    "winner_score": winner_score,
                    "loser_score": loser_score,
                    "margin": margin,
                }
                if margin > max_margin:
                    max_margin = margin
                    biggest_blowout = highlight_data
                if margin < min_margin:
                    min_margin = margin
                    closest_game = highlight_data

            pairwise_games.append(
                {
                    "matchup_id": m.id,
                    "season_year": m.season_year,
                    "week": m.week,
                    "matchup_type": m.matchup_type,
                    "manager_a_team_name": a_team_name,
                    "manager_b_team_name": b_team_name,
                    "manager_a_logo_url": a_logo_url,
                    "manager_b_logo_url": b_logo_url,
                    "manager_a_score": a_score,
                    "manager_b_score": b_score,
                    "winner_manager_id": winner_id,
                }
            )

        reg_split["a_points"] = round(reg_split["a_points"], 2)
        reg_split["b_points"] = round(reg_split["b_points"], 2)
        play_split["a_points"] = round(play_split["a_points"], 2)
        play_split["b_points"] = round(play_split["b_points"], 2)

        comb_a_pts = round(reg_split["a_points"] + play_split["a_points"], 2)
        comb_b_pts = round(reg_split["b_points"] + play_split["b_points"], 2)
        combined_split = {
            "a_wins": reg_split["a_wins"] + play_split["a_wins"],
            "b_wins": reg_split["b_wins"] + play_split["b_wins"],
            "ties": reg_split["ties"] + play_split["ties"],
            "a_points": comb_a_pts,
            "b_points": comb_b_pts,
            "point_differential": round(comb_a_pts - comb_b_pts, 2),
        }

        # Calculate current streak from chronological games
        streak_len = 0
        streak_type: str = "NONE"
        streak_mgr_id: int | None = None

        if pairwise_games:
            last_game = pairwise_games[-1]
            last_winner = last_game["winner_manager_id"]
            if last_winner is None:
                streak_type = "TIE"
                streak_len = 1
                for g in reversed(pairwise_games[:-1]):
                    if g["winner_manager_id"] is None:
                        streak_len += 1
                    else:
                        break
            else:
                streak_type = "WIN"
                streak_mgr_id = last_winner
                streak_len = 1
                for g in reversed(pairwise_games[:-1]):
                    if g["winner_manager_id"] == last_winner:
                        streak_len += 1
                    else:
                        break

        current_streak = {
            "manager_id": streak_mgr_id,
            "display_name": mgr_map.get(streak_mgr_id) if streak_mgr_id else None,
            "length": streak_len,
            "type": streak_type,
        }

        pair_detail = {
            "manager_a": mgr_ref_map.get(
                manager_a_id,
                {
                    "manager_id": manager_a_id,
                    "display_name": mgr_map.get(manager_a_id, ""),
                    "team_name": mgr_map.get(manager_a_id, ""),
                    "avatar_url": mgr_avatar_map.get(manager_a_id),
                },
            ),
            "manager_b": mgr_ref_map.get(
                manager_b_id,
                {
                    "manager_id": manager_b_id,
                    "display_name": mgr_map.get(manager_b_id, ""),
                    "team_name": mgr_map.get(manager_b_id, ""),
                    "avatar_url": mgr_avatar_map.get(manager_b_id),
                },
            ),
            "regular_season": reg_split,
            "playoffs": play_split,
            "combined": combined_split,
            "current_streak": current_streak,
            "biggest_blowout": biggest_blowout,
            "closest_game": closest_game,
            "matchups": pairwise_games,
        }

    return {
        "managers": mgr_ref_list,
        "matrix": matrix,
        "pair_detail": pair_detail,
    }
