"""db/seed_dev.py - Development Database Seed Harness.

Purpose:
    Generates a deterministic, realistic multi-season dataset for local testing
    and offline verification. Covers all 12 tables and 8 primary data domains:
      - 3 seasons: 2022 (completed legacy), 2023 (completed modern), 2024 (active week 8)
      - 10 human managers with churn (departing manager, incoming rookie, co-managers)
      - 20 canonical NFL players
      - Complete regular season, playoffs, consolation, and bye matchups with Max PF
      - Weekly starter and bench lineups with actual & projected points
      - FAAB bidding wars with failed outbid bids linked via related_espn_transaction_id
      - Bilateral trades with post-trade starter points in weekly lineups
      - Reconciled financial earnings ledger ($10 wins, $5 ties, $600/$300/$100 podiums)
      - Raw ESPN JSON snapshots and sync run audit logs

Execution:
    python3 -m db.seed_dev
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import create_db_engine, init_db
from backend.jobs.payout_policy import load_season_payout_rules
from backend.models import (
    DraftPick,
    EarningsLedger,
    Manager,
    Matchup,
    Player,
    RawEspnSnapshot,
    Season,
    SyncRun,
    Team,
    Trade,
    Transaction,
    TransactionItem,
    WeeklyLineup,
)


def seed_database(target_engine: Engine | None = None) -> dict[str, int]:
    """Deterministically seed the database with a 3-season development dataset.

    Idempotent: Cleans existing development records and repopulates all 12 tables
    with identical rows and foreign key integrity.
    """
    engine = target_engine or create_db_engine()
    init_db(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        # 1. Clean existing records in reverse dependency order
        _clear_tables(session)

        # 2. Seed Master Managers (10 managers: 7 core, 1 legacy churned, 1 rookie, 1 co-manager)
        managers = _seed_managers(session)

        # 3. Seed Seasons (2022 completed legacy, 2023 completed modern, 2024 active)
        seasons = _seed_seasons(session)

        # 4. Seed Franchises / Teams (8 teams per season)
        teams = _seed_teams(session, managers, seasons)

        # 5. Seed Canonical NFL Players (20 marquee players across QB, RB, WR, TE)
        players = _seed_players(session)

        # 6. Seed Matchups (Regular season, ties, playoff winners bracket, consolation, byes)
        matchups = _seed_matchups(session, seasons, teams)

        # 7. Seed Weekly Lineups (Starters + bench with actual and projected points)
        _seed_lineups(session, seasons, teams, players)

        # 8. Seed Draft Board Picks
        _seed_draft_picks(session, seasons, teams, players)

        # 9. Seed Transactions, Bidding Wars & Trades
        _seed_transactions_and_trades(session, seasons, teams, players)

        # 10. Seed Financial Earnings Ledger ($10 wins, $5 ties, podium payouts)
        _seed_earnings_ledger(session, seasons, teams, matchups)

        # 11. Seed Raw ESPN Snapshots & Sync Runs
        _seed_raw_snapshots_and_sync_runs(session)

        session.commit()

        # Gather table counts for verification
        counts = {
            "seasons": session.query(Season).count(),
            "managers": session.query(Manager).count(),
            "teams": session.query(Team).count(),
            "players": session.query(Player).count(),
            "matchups": session.query(Matchup).count(),
            "weekly_lineups": session.query(WeeklyLineup).count(),
            "draft_picks": session.query(DraftPick).count(),
            "transactions": session.query(Transaction).count(),
            "transaction_items": session.query(TransactionItem).count(),
            "trades": session.query(Trade).count(),
            "earnings_ledger": session.query(EarningsLedger).count(),
            "raw_espn_snapshots": session.query(RawEspnSnapshot).count(),
            "sync_runs": session.query(SyncRun).count(),
        }

    return counts


def _clear_tables(session: Session) -> None:
    """Clear tables in reverse foreign-key dependency order."""
    session.query(SyncRun).delete()
    session.query(EarningsLedger).delete()
    session.query(TransactionItem).delete()
    session.query(Trade).delete()
    session.query(Transaction).delete()
    session.query(WeeklyLineup).delete()
    session.query(DraftPick).delete()
    session.query(Matchup).delete()
    session.query(Team).delete()
    session.query(Player).delete()
    session.query(Manager).delete()
    session.query(Season).delete()
    session.query(RawEspnSnapshot).delete()
    session.flush()


def _seed_managers(session: Session) -> dict[str, Manager]:
    """Seed 10 managers demonstrating continuity, churn, and co-management."""
    manager_specs = [
        ("mgr_01", "{AAAA-0001-ARCHER}", "Alice Archer", True),
        ("mgr_02", "{BBBB-0002-BAKER}", "Bob Baker", True),
        ("mgr_03", "{CCCC-0003-CLARK}", "Charlie Clark", True),
        ("mgr_04", "{DDDD-0004-DAVIS}", "Diana Davis", True),
        ("mgr_05", "{EEEE-0005-EVANS}", "Evan Evans", True),
        ("mgr_06", "{FFFF-0006-FORD}", "Frankie Ford", True),
        ("mgr_07", "{GGGG-0007-GREEN}", "Grace Green", True),
        ("mgr_08", "{HHHH-0008-HILL}", "Hank Hill", True),
        ("mgr_09", "{LLLL-0009-LOU}", "Legacy Lou", False),  # Churned out after 2022
        ("mgr_10", "{RRRR-0010-RACHEL}", "Rookie Rachel", True),  # Joined in 2023
    ]

    managers: dict[str, Manager] = {}
    for code, guid, name, active in manager_specs:
        mgr = Manager(
            espn_member_id=guid,
            display_name=name,
            avatar_url=f"https://fantasy.espn.com/avatars/{code}.png",
            is_active=active,
            created_at=datetime(2022, 8, 1, 12, 0, tzinfo=UTC),
        )
        session.add(mgr)
        managers[code] = mgr

    session.flush()
    return managers


def _seed_seasons(session: Session) -> dict[int, Season]:
    """Seed 3 seasons: 2022 (legacy), 2023 (modern completed), 2024 (active)."""
    default_scoring = {
        "pass_yd": 0.04,
        "pass_td": 4.0,
        "rush_yd": 0.1,
        "rush_td": 6.0,
        "rec": 1.0,
        "rec_yd": 0.1,
        "rec_td": 6.0,
    }
    default_slots = {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "FLEX": 1,
        "BE": 6,
        "IR": 1,
    }

    p2022 = load_season_payout_rules(2022)
    s2022 = Season(
        season_year=2022,
        league_id="12345678",
        league_name="The League of Extraordinary Gentlemen",
        is_active=False,
        is_completed=True,
        regular_season_weeks=14,
        current_week=17,
        playoff_team_count=6,
        playoff_matchup_length=1,
        scoring_type="PPR",
        scoring_settings=default_scoring,
        roster_slots=default_slots,
        faab_budget=100,
        weekly_win_payout=p2022["weekly_win_payout"],
        weekly_high_score_payout=p2022["weekly_high_score_payout"],
        weekly_high_score_loss_payout=p2022["weekly_high_score_loss_payout"],
        champion_payout=p2022["champion_payout"],
        runner_up_payout=p2022["runner_up_payout"],
        third_place_payout=p2022["third_place_payout"],
        fourth_place_payout=p2022["fourth_place_payout"],
        fifth_place_payout=p2022["fifth_place_payout"],
        regular_season_most_points_payout=p2022["regular_season_most_points_payout"],
        has_transaction_data=False,  # Legacy era without ESPN transaction history
        has_boxscore_data=True,
    )

    p2023 = load_season_payout_rules(2023)
    s2023 = Season(
        season_year=2023,
        league_id="12345678",
        league_name="The League of Extraordinary Gentlemen",
        is_active=False,
        is_completed=True,
        regular_season_weeks=14,
        current_week=17,
        playoff_team_count=6,
        playoff_matchup_length=1,
        scoring_type="PPR",
        scoring_settings=default_scoring,
        roster_slots=default_slots,
        faab_budget=100,
        weekly_win_payout=p2023["weekly_win_payout"],
        weekly_high_score_payout=p2023["weekly_high_score_payout"],
        weekly_high_score_loss_payout=p2023["weekly_high_score_loss_payout"],
        champion_payout=p2023["champion_payout"],
        runner_up_payout=p2023["runner_up_payout"],
        third_place_payout=p2023["third_place_payout"],
        fourth_place_payout=p2023["fourth_place_payout"],
        fifth_place_payout=p2023["fifth_place_payout"],
        regular_season_most_points_payout=p2023["regular_season_most_points_payout"],
        has_transaction_data=True,
        has_boxscore_data=True,
    )

    p2024 = load_season_payout_rules(2024)
    s2024 = Season(
        season_year=2024,
        league_id="12345678",
        league_name="The League of Extraordinary Gentlemen",
        is_active=True,
        is_completed=False,
        regular_season_weeks=14,
        current_week=8,
        playoff_team_count=6,
        playoff_matchup_length=1,
        scoring_type="PPR",
        scoring_settings=default_scoring,
        roster_slots=default_slots,
        faab_budget=100,
        weekly_win_payout=p2024["weekly_win_payout"],
        weekly_high_score_payout=p2024["weekly_high_score_payout"],
        weekly_high_score_loss_payout=p2024["weekly_high_score_loss_payout"],
        champion_payout=p2024["champion_payout"],
        runner_up_payout=p2024["runner_up_payout"],
        third_place_payout=p2024["third_place_payout"],
        fourth_place_payout=p2024["fourth_place_payout"],
        fifth_place_payout=p2024["fifth_place_payout"],
        regular_season_most_points_payout=p2024["regular_season_most_points_payout"],
        has_transaction_data=True,
        has_boxscore_data=True,
    )

    session.add_all([s2022, s2023, s2024])
    session.flush()
    return {2022: s2022, 2023: s2023, 2024: s2024}


def _seed_teams(
    session: Session, managers: dict[str, Manager], seasons: dict[int, Season]
) -> dict[tuple[int, int], Team]:
    """Seed 8 teams per season. In 2022 Mgr 9 plays; in 2023+ Mgr 10 replaces Mgr 9.

    Team 7 is co-managed by Mgr 7 and Mgr 8 across all seasons.
    """
    teams: dict[tuple[int, int], Team] = {}

    for year in [2022, 2023, 2024]:
        # Franchise 8 owner churns: Legacy Lou in 2022, Rookie Rachel in 2023-2024
        f8_mgr = managers["mgr_09"] if year == 2022 else managers["mgr_10"]
        f8_name = "Lou's Legends" if year == 2022 else "Rachel's Rookies"
        f8_abbrev = "LOU" if year == 2022 else "RCH"

        specs = [
            (1, managers["mgr_01"], None, "Archer Assassins", "ARC", 1, "East"),
            (2, managers["mgr_02"], None, "Baker's Dozen", "BAK", 1, "East"),
            (3, managers["mgr_03"], None, "Clark's Crusaders", "CLK", 1, "East"),
            (4, managers["mgr_04"], None, "Diana's Dynasty", "DYN", 1, "East"),
            (5, managers["mgr_05"], None, "Evans Elevation", "EVN", 2, "West"),
            (6, managers["mgr_06"], None, "Ford Tough", "FRD", 2, "West"),
            (7, managers["mgr_07"], managers["mgr_08"], "Green Hill Zone", "GHZ", 2, "West"),
            (8, f8_mgr, None, f8_name, f8_abbrev, 2, "West"),
        ]

        for espn_id, mgr, co_mgr, name, abbrev, div_id, div_name in specs:
            raw_guids = [mgr.espn_member_id]
            if co_mgr:
                raw_guids.append(co_mgr.espn_member_id)

            team = Team(
                season_year=year,
                espn_team_id=espn_id,
                team_name=name,
                team_abbrev=abbrev,
                logo_url=f"https://fantasy.espn.com/logos/{abbrev.lower()}.png",
                manager_id=mgr.id,
                co_manager_id=co_mgr.id if co_mgr else None,
                raw_owner_guids=raw_guids,
                division_id=div_id,
                division_name=div_name,
                wins=9 if espn_id <= 2 else (8 if espn_id <= 4 else (7 if espn_id <= 6 else 4)),
                losses=5 if espn_id <= 2 else (6 if espn_id <= 4 else (7 if espn_id <= 6 else 10)),
                ties=0,
                home_wins=5,
                home_losses=2,
                away_wins=4,
                away_losses=3,
                points_for=Decimal(f"{1650.00 + (espn_id * 20.50):.2f}"),
                points_against=Decimal(f"{1550.00 + (espn_id * 15.25):.2f}"),
                streak_type="WIN" if espn_id % 2 == 1 else "LOSS",
                streak_length=2,
                playoff_seed=espn_id,
                final_standing=espn_id if year < 2024 else None,
                faab_remaining=85 if year == 2024 else (15 if year == 2023 else 0),
                waiver_rank=espn_id,
                acquisitions=18 if year > 2022 else 0,
                drops=15 if year > 2022 else 0,
                trades=2 if year == 2023 else (1 if year == 2024 else 0),
                ir_moves=4,
            )
            session.add(team)
            teams[(year, espn_id)] = team

    session.flush()
    return teams


def _seed_players(session: Session) -> dict[int, Player]:
    """Seed 20 marquee NFL players."""
    player_data = [
        (101, "Christian McCaffrey", "RB", "SF"),
        (102, "Justin Jefferson", "WR", "MIN"),
        (103, "Josh Allen", "QB", "BUF"),
        (104, "CeeDee Lamb", "WR", "DAL"),
        (105, "Amon-Ra St. Brown", "WR", "DET"),
        (106, "Puka Nacua", "WR", "LAR"),
        (107, "Kyren Williams", "RB", "LAR"),
        (108, "Bijan Robinson", "RB", "ATL"),
        (109, "Travis Kelce", "TE", "KC"),
        (110, "Breece Hall", "RB", "NYJ"),
        (111, "Garrett Wilson", "WR", "NYJ"),
        (112, "Jahmyr Gibbs", "RB", "DET"),
        (113, "Patrick Mahomes", "QB", "KC"),
        (114, "Tyreek Hill", "WR", "MIA"),
        (115, "Lamar Jackson", "QB", "BAL"),
        (116, "A.J. Brown", "WR", "PHI"),
        (117, "Saquon Barkley", "RB", "PHI"),
        (118, "Sam LaPorta", "TE", "DET"),
        (119, "Derrick Henry", "RB", "BAL"),
        (120, "Ja'Marr Chase", "WR", "CIN"),
    ]

    players: dict[int, Player] = {}
    for pid, name, pos, team in player_data:
        p = Player(
            espn_player_id=pid,
            full_name=name,
            default_position=pos,
            pro_team=team,
            headshot_url=f"https://a.espncdn.com/i/headshots/nfl/players/full/{pid}.png",
        )
        session.add(p)
        players[pid] = p

    session.flush()
    return players


def _seed_matchups(
    session: Session,
    seasons: dict[int, Season],
    teams: dict[tuple[int, int], Team],
) -> list[Matchup]:
    """Seed regular season matchups, ties, playoffs (championship, consolation, byes)."""
    matchups: list[Matchup] = []
    matchup_pk_id = 1

    for year in [2022, 2023, 2024]:
        max_reg_weeks = 7 if year == 2024 else 14
        # 1. Regular season schedule (4 games per week across 8 teams)
        for week in range(1, max_reg_weeks + 1):
            pairings = [(1, 2), (3, 4), (5, 6), (7, 8)]
            # Rotate pairings slightly each week
            shift = (week - 1) % 3
            if shift == 1:
                pairings = [(1, 3), (2, 4), (5, 7), (6, 8)]
            elif shift == 2:
                pairings = [(1, 4), (2, 3), (5, 8), (6, 7)]

            for h_idx, a_idx in pairings:
                h_team = teams[(year, h_idx)]
                a_team = teams[(year, a_idx)]

                # Special: 2023 Week 3 has an exact tie between Team 1 and Team 2!
                is_tie = (year == 2023 and week == 3 and h_idx == 1 and a_idx == 3)
                if is_tie:
                    h_score = Decimal("114.50")
                    a_score = Decimal("114.50")
                    winner_id = None
                else:
                    h_score = Decimal(f"{100.00 + (h_idx * 5.0) + (week * 2.1):.2f}")
                    a_score = Decimal(f"{95.00 + (a_idx * 4.8) + (week * 1.9):.2f}")
                    winner_id = h_team.id if h_score > a_score else a_team.id

                m = Matchup(
                    season_year=year,
                    week=week,
                    espn_matchup_id=matchup_pk_id,
                    matchup_type="REGULAR",
                    home_team_id=h_team.id,
                    away_team_id=a_team.id,
                    home_score=h_score,
                    away_score=a_score,
                    home_projected=Decimal("110.00"),
                    away_projected=Decimal("108.50"),
                    home_optimal_score=h_score + Decimal("15.20"),
                    away_optimal_score=a_score + Decimal("12.40"),
                    home_bench_points=Decimal("38.50"),
                    away_bench_points=Decimal("32.10"),
                    winner_team_id=winner_id,
                    is_tie=is_tie,
                    is_completed=True,
                    points_by_scoring_period={"1": float(h_score)},
                )
                session.add(m)
                matchups.append(m)
                matchup_pk_id += 1

        # 2. Playoff rounds for completed seasons (2022, 2023)
        if year < 2024:
            # Week 15: Quarterfinals + 2 First-Round Byes (Seed 1 & 2) + Consolation (7 vs 8)
            t1 = teams[(year, 1)]
            t2 = teams[(year, 2)]
            t3 = teams[(year, 3)]
            t4 = teams[(year, 4)]
            t5 = teams[(year, 5)]
            t6 = teams[(year, 6)]
            t7 = teams[(year, 7)]
            t8 = teams[(year, 8)]

            # Seed 1 Bye
            m_bye1 = Matchup(
                season_year=year,
                week=15,
                espn_matchup_id=matchup_pk_id,
                matchup_type="BYE",
                home_team_id=t1.id,
                away_team_id=None,
                home_score=Decimal("120.00"),
                away_score=Decimal("0.00"),
                winner_team_id=t1.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            # Seed 2 Bye
            m_bye2 = Matchup(
                season_year=year,
                week=15,
                espn_matchup_id=matchup_pk_id,
                matchup_type="BYE",
                home_team_id=t2.id,
                away_team_id=None,
                home_score=Decimal("118.00"),
                away_score=Decimal("0.00"),
                winner_team_id=t2.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            # QF 1: Seed 3 vs Seed 6 (WINNERS_BRACKET)
            m_qf1 = Matchup(
                season_year=year,
                week=15,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t3.id,
                away_team_id=t6.id,
                home_score=Decimal("130.00"),
                away_score=Decimal("110.00"),
                winner_team_id=t3.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            # QF 2: Seed 4 vs Seed 5 (WINNERS_BRACKET)
            m_qf2 = Matchup(
                season_year=year,
                week=15,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t4.id,
                away_team_id=t5.id,
                home_score=Decimal("125.00"),
                away_score=Decimal("115.00"),
                winner_team_id=t4.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            # Consolation: Seed 7 vs Seed 8 (LOSERS_CONSOLATION_LADDER)
            m_cons15 = Matchup(
                season_year=year,
                week=15,
                espn_matchup_id=matchup_pk_id,
                matchup_type="LOSERS_CONSOLATION_LADDER",
                home_team_id=t7.id,
                away_team_id=t8.id,
                home_score=Decimal("105.00"),
                away_score=Decimal("98.00"),
                winner_team_id=t7.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            session.add_all([m_bye1, m_bye2, m_qf1, m_qf2, m_cons15])

            # Week 16: Semifinals (Seed 1 vs QF2 winner T4, Seed 2 vs QF1 winner T3)
            m_sf1 = Matchup(
                season_year=year,
                week=16,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t1.id,
                away_team_id=t4.id,
                home_score=Decimal("140.00"),
                away_score=Decimal("122.00"),
                winner_team_id=t1.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            m_sf2 = Matchup(
                season_year=year,
                week=16,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t2.id,
                away_team_id=t3.id,
                home_score=Decimal("135.00"),
                away_score=Decimal("120.00"),
                winner_team_id=t2.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            session.add_all([m_sf1, m_sf2])

            # Week 17: Championship Finals (T1 vs T2) and 3rd Place (T3 vs T4)
            m_champ = Matchup(
                season_year=year,
                week=17,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t1.id,
                away_team_id=t2.id,
                home_score=Decimal("145.50"),
                away_score=Decimal("138.20"),
                winner_team_id=t1.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            m_third = Matchup(
                season_year=year,
                week=17,
                espn_matchup_id=matchup_pk_id,
                matchup_type="WINNERS_BRACKET",
                home_team_id=t3.id,
                away_team_id=t4.id,
                home_score=Decimal("128.00"),
                away_score=Decimal("112.00"),
                winner_team_id=t3.id,
                is_completed=True,
            )
            matchup_pk_id += 1
            session.add_all([m_champ, m_third])

    session.flush()
    return matchups


def _seed_lineups(
    session: Session,
    seasons: dict[int, Season],
    teams: dict[tuple[int, int], Team],
    players: dict[int, Player],
) -> None:
    """Seed weekly lineups for starters (QB, RB, WR, TE, FLEX) and bench (BE, IR)."""
    # Map roster players per franchise
    # Team 1 has CMC (101), Justin Jefferson (102), Josh Allen (103), Kelce (109)
    # Team 2 has CeeDee (104), St. Brown (105), Kyren (107), Bijan (108)
    lineups: list[WeeklyLineup] = []

    for year in [2022, 2023, 2024]:
        max_weeks = 7 if year == 2024 else 17
        for week in range(1, max_weeks + 1):
            for espn_id in range(1, 9):
                team = teams[(year, espn_id)]

                # Assign 5 starters and 2 bench players per team
                starter_pids = [101, 102, 103, 104, 105] if espn_id % 2 == 1 else [107, 108, 109, 110, 112]
                bench_pids = [113, 114] if espn_id % 2 == 1 else [115, 116]

                # Special: In 2023, after week 6 trade, Kyren (107) starts on Team 2, Garrett Wilson (111) on Team 1!
                if year == 2023 and week > 6:
                    if espn_id == 1:
                        starter_pids = [101, 102, 103, 111, 105]  # Garrett Wilson (111) now starts for Team 1
                    elif espn_id == 2:
                        starter_pids = [107, 108, 109, 110, 112]  # Kyren (107) starts for Team 2

                slots = ["QB", "RB", "WR", "TE", "FLEX"]
                for slot, pid in zip(slots, starter_pids, strict=False):
                    pts = Decimal(f"{15.00 + ((pid % 7) * 2.5) + (week * 0.5):.2f}")
                    proj = Decimal(f"{14.00 + ((pid % 5) * 2.0):.2f}")
                    lineup = WeeklyLineup(
                        season_year=year,
                        week=week,
                        team_id=team.id,
                        player_id=pid,
                        slot_position=slot,
                        is_starter=True,
                        actual_points=pts,
                        projected_points=proj,
                        acquisition_type="DRAFT",
                        weekly_stats={
                            "passing_yards": 250,
                            "rushing_yards": 40,
                            "touchdowns": 2,
                            "injury_status": None,
                            "injured": False,
                        },
                    )
                    lineups.append(lineup)

                for b_slot, b_pid in zip(["BE", "IR"], bench_pids, strict=False):
                    b_pts = Decimal(f"{8.00 + ((b_pid % 4) * 1.5):.2f}")
                    if b_slot == "IR":
                        b_stats: dict[str, Any] = {
                            "injury_status": "INJURY_RESERVE",
                            "injured": True,
                        }
                    elif (week + b_pid) % 6 == 0:
                        b_stats = {
                            "injury_status": "QUESTIONABLE",
                            "injured": False,
                        }
                    elif (week + b_pid) % 9 == 0:
                        b_stats = {
                            "injury_status": "OUT",
                            "injured": True,
                        }
                    else:
                        b_stats = {
                            "injury_status": None,
                            "injured": False,
                        }

                    lineup_b = WeeklyLineup(
                        season_year=year,
                        week=week,
                        team_id=team.id,
                        player_id=b_pid,
                        slot_position=b_slot,
                        is_starter=False,
                        actual_points=b_pts,
                        projected_points=Decimal("10.00"),
                        acquisition_type="DRAFT",
                        weekly_stats=b_stats,
                    )
                    lineups.append(lineup_b)

    session.add_all(lineups)
    session.flush()


def _seed_draft_picks(
    session: Session,
    seasons: dict[int, Season],
    teams: dict[tuple[int, int], Team],
    players: dict[int, Player],
) -> None:
    """Seed annual draft board selections for modern and active seasons (2023, 2024)."""
    draft_picks: list[DraftPick] = []

    # Player IDs pool: 101 through 116
    player_pool = sorted(players.keys())[:16]

    for year in (2023, 2024):
        overall = 1
        for round_num in (1, 2):
            team_order = range(1, 9) if round_num == 1 else range(8, 0, -1)
            for round_pick, espn_id in enumerate(team_order, start=1):
                team = teams[(year, espn_id)]
                pid = player_pool[(overall - 1) % len(player_pool)]
                is_keeper = (round_num == 1 and espn_id == 1 and year == 2024)

                pick = DraftPick(
                    season_year=year,
                    round=round_num,
                    round_pick=round_pick,
                    overall_pick=overall,
                    team_id=team.id,
                    player_id=pid,
                    bid_amount=0,
                    is_keeper=is_keeper,
                    lineup_slot_id=4 if pid % 2 == 0 else 2,
                    auto_draft_type_id=0,
                )
                draft_picks.append(pick)
                overall += 1

    session.add_all(draft_picks)
    session.flush()


def _seed_transactions_and_trades(
    session: Session,
    seasons: dict[int, Season],
    teams: dict[tuple[int, int], Team],
    players: dict[int, Player],
) -> None:
    """Seed waivers, failed FAAB bidding wars, free agents, and bilateral trades."""
    # 1. 2023 Week 2 FAAB Bidding War for Puka Nacua (Player 106)
    # Team 1 wins with $35 bid; Team 2 and Team 3 are outbid; Team 4 has insufficient funds
    tx_win = Transaction(
        season_year=2023,
        week=2,
        scoring_period=2,
        espn_transaction_id="tx_2023_w02_puka_win",
        transaction_type="WAIVER",
        status="EXECUTED",
        team_id=teams[(2023, 1)].id,
        bid_amount=35,
        waiver_priority=3,
        proposed_at=datetime(2023, 9, 12, 10, 0, tzinfo=UTC),
        executed_at=datetime(2023, 9, 13, 8, 0, tzinfo=UTC),
        raw_summary={"note": "Winning FAAB claim for Puka Nacua"},
    )
    session.add(tx_win)
    session.flush()

    # Winning claim item
    item_win = TransactionItem(
        transaction_id=tx_win.id,
        player_id=106,
        from_team_id=None,
        to_team_id=teams[(2023, 1)].id,
        item_type="ADD",
    )
    session.add(item_win)

    # Losing bids linked via related_espn_transaction_id
    tx_loss_t2 = Transaction(
        season_year=2023,
        week=2,
        scoring_period=2,
        espn_transaction_id="tx_2023_w02_puka_loss_t2",
        transaction_type="WAIVER",
        status="FAILED",
        team_id=teams[(2023, 2)].id,
        bid_amount=27,
        waiver_priority=5,
        failure_reason="OUTBID",
        related_espn_transaction_id="tx_2023_w02_puka_win",
        proposed_at=datetime(2023, 9, 12, 14, 0, tzinfo=UTC),
        raw_summary={"note": "Outbid by $8"},
    )
    tx_loss_t3 = Transaction(
        season_year=2023,
        week=2,
        scoring_period=2,
        espn_transaction_id="tx_2023_w02_puka_loss_t3",
        transaction_type="WAIVER",
        status="FAILED",
        team_id=teams[(2023, 3)].id,
        bid_amount=19,
        waiver_priority=6,
        failure_reason="OUTBID",
        related_espn_transaction_id="tx_2023_w02_puka_win",
        proposed_at=datetime(2023, 9, 12, 16, 0, tzinfo=UTC),
    )
    tx_loss_t4 = Transaction(
        season_year=2023,
        week=2,
        scoring_period=2,
        espn_transaction_id="tx_2023_w02_puka_loss_t4",
        transaction_type="WAIVER",
        status="FAILED",
        team_id=teams[(2023, 4)].id,
        bid_amount=40,
        waiver_priority=1,
        failure_reason="INSUFFICIENT_FUNDS",
        related_espn_transaction_id="tx_2023_w02_puka_win",
        proposed_at=datetime(2023, 9, 12, 18, 0, tzinfo=UTC),
    )
    session.add_all([tx_loss_t2, tx_loss_t3, tx_loss_t4])

    # 2. Free Agent Add and Drop
    tx_fa = Transaction(
        season_year=2023,
        week=4,
        scoring_period=4,
        espn_transaction_id="tx_2023_w04_fa_laporta",
        transaction_type="FREE_AGENT",
        status="EXECUTED",
        team_id=teams[(2023, 3)].id,
        bid_amount=0,
        executed_at=datetime(2023, 9, 27, 15, 30, tzinfo=UTC),
    )
    session.add(tx_fa)
    session.flush()

    item_fa_add = TransactionItem(
        transaction_id=tx_fa.id,
        player_id=118,  # Sam LaPorta
        from_team_id=None,
        to_team_id=teams[(2023, 3)].id,
        item_type="ADD",
    )
    item_fa_drop = TransactionItem(
        transaction_id=tx_fa.id,
        player_id=120,  # Ja'Marr Chase bench drop
        from_team_id=teams[(2023, 3)].id,
        to_team_id=None,
        item_type="DROP",
    )
    session.add_all([item_fa_add, item_fa_drop])

    # 3. Bilateral Trade in 2023 Week 6
    # Team 1 gives Kyren Williams (107) to Team 2
    # Team 2 gives Garrett Wilson (111) + $10 FAAB to Team 1
    t1 = teams[(2023, 1)]
    t2 = teams[(2023, 2)]
    trade = Trade(
        season_year=2023,
        week=6,
        espn_transaction_id="trade_2023_w06_t1_t2",
        proposing_team_id=t1.id,
        accepting_team_id=t2.id,
        status="EXECUTED",
        proposed_at=datetime(2023, 10, 17, 12, 0, tzinfo=UTC),
        executed_at=datetime(2023, 10, 18, 9, 0, tzinfo=UTC),
        faab_from_proposer=0,
        faab_from_accepter=10,
        trade_summary={"notes": "Kyren Williams for Garrett Wilson + $10 FAAB"},
    )
    session.add(trade)

    tx_trade = Transaction(
        season_year=2023,
        week=6,
        scoring_period=6,
        espn_transaction_id="trade_2023_w06_t1_t2",
        transaction_type="TRADE",
        status="EXECUTED",
        team_id=t1.id,
        bid_amount=0,
        executed_at=datetime(2023, 10, 18, 9, 0, tzinfo=UTC),
    )
    session.add(tx_trade)
    session.flush()

    item_trade1 = TransactionItem(
        transaction_id=tx_trade.id,
        player_id=107,
        from_team_id=t1.id,
        to_team_id=t2.id,
        item_type="TRADE",
    )
    item_trade2 = TransactionItem(
        transaction_id=tx_trade.id,
        player_id=111,
        from_team_id=t2.id,
        to_team_id=t1.id,
        item_type="TRADE",
    )
    session.add_all([item_trade1, item_trade2])
    session.flush()


def _seed_earnings_ledger(
    session: Session,
    seasons: dict[int, Season],
    teams: dict[tuple[int, int], Team],
    matchups: list[Matchup],
) -> None:
    """Seed regular-season $10 wins, $5 ties, and championship podium awards ($600/$300/$100)."""
    ledger_entries: list[EarningsLedger] = []

    # 1. Weekly win and tie payouts derived from regular season matchups
    for m in matchups:
        if m.matchup_type != "REGULAR":
            continue

        if m.is_tie:
            # Both home and away team managers get $5.00
            h_team = session.get(Team, m.home_team_id)
            a_team = session.get(Team, m.away_team_id)
            if h_team and a_team:
                ledger_entries.append(
                    EarningsLedger(
                        manager_id=h_team.manager_id,
                        team_id=h_team.id,
                        season_year=m.season_year,
                        week=m.week,
                        entry_type="WEEKLY_TIE",
                        amount=Decimal("5.00"),
                        description=f"Week {m.week} Regular Season Tie Split",
                    )
                )
                ledger_entries.append(
                    EarningsLedger(
                        manager_id=a_team.manager_id,
                        team_id=a_team.id,
                        season_year=m.season_year,
                        week=m.week,
                        entry_type="WEEKLY_TIE",
                        amount=Decimal("5.00"),
                        description=f"Week {m.week} Regular Season Tie Split",
                    )
                )
        elif m.winner_team_id:
            w_team = session.get(Team, m.winner_team_id)
            if w_team:
                ledger_entries.append(
                    EarningsLedger(
                        manager_id=w_team.manager_id,
                        team_id=w_team.id,
                        season_year=m.season_year,
                        week=m.week,
                        entry_type="WEEKLY_WIN",
                        amount=Decimal("10.00"),
                        description=f"Week {m.week} Regular Season Win",
                    )
                )

    # 2. Weekly high score ($10.00) and weekly high score in a loss ($10.00)
    matchups_by_year_week: dict[tuple[int, int], list[Matchup]] = defaultdict(list)
    for m in matchups:
        if m.matchup_type == "REGULAR":
            matchups_by_year_week[(m.season_year, m.week)].append(m)

    for (year, week), wk_matchups in matchups_by_year_week.items():
        # High score of the week
        team_scores: list[tuple[int, Decimal, int]] = []
        for m in wk_matchups:
            h_team = session.get(Team, m.home_team_id)
            if h_team:
                team_scores.append((h_team.id, m.home_score, h_team.manager_id))
            if m.away_team_id:
                a_team = session.get(Team, m.away_team_id)
                if a_team:
                    team_scores.append((a_team.id, m.away_score, a_team.manager_id))

        if team_scores:
            max_score = max(score for _, score, _ in team_scores)
            if max_score > Decimal("0.00"):
                high_score_teams = [
                    (tid, mid) for tid, score, mid in team_scores if score == max_score
                ]
                split_count = len(high_score_teams)
                hs_amount = (Decimal("10.00") / Decimal(split_count)).quantize(Decimal("0.01"))
                for tid, mid in high_score_teams:
                    desc = (
                        f"Week {week} Regular Season High Score ({max_score:.2f} pts)"
                        if split_count == 1
                        else f"Week {week} Regular Season High Score Tie ({max_score:.2f} pts)"
                    )
                    ledger_entries.append(
                        EarningsLedger(
                            manager_id=mid,
                            team_id=tid,
                            season_year=year,
                            week=week,
                            entry_type="WEEKLY_HIGH_SCORE",
                            amount=hs_amount,
                            description=desc,
                        )
                    )

        # High score in a loss
        losing_scores: list[tuple[int, Decimal, int]] = []
        for m in wk_matchups:
            if not m.is_tie and m.winner_team_id:
                if m.winner_team_id == m.home_team_id and m.away_team_id:
                    l_team = session.get(Team, m.away_team_id)
                    if l_team:
                        losing_scores.append((l_team.id, m.away_score, l_team.manager_id))
                elif m.winner_team_id == m.away_team_id:
                    l_team = session.get(Team, m.home_team_id)
                    if l_team:
                        losing_scores.append((l_team.id, m.home_score, l_team.manager_id))

        if losing_scores:
            max_loss_score = max(score for _, score, _ in losing_scores)
            if max_loss_score > Decimal("0.00"):
                high_loss_teams = [
                    (tid, mid) for tid, score, mid in losing_scores if score == max_loss_score
                ]
                loss_split_count = len(high_loss_teams)
                hsl_amount = (Decimal("10.00") / Decimal(loss_split_count)).quantize(
                    Decimal("0.01")
                )
                for tid, mid in high_loss_teams:
                    desc = (
                        f"Week {week} Regular Season Most Points in a Loss ({max_loss_score:.2f} pts)"
                        if loss_split_count == 1
                        else f"Week {week} Regular Season Most Points in a Loss Tie ({max_loss_score:.2f} pts)"
                    )
                    ledger_entries.append(
                        EarningsLedger(
                            manager_id=mid,
                            team_id=tid,
                            season_year=year,
                            week=week,
                            entry_type="WEEKLY_HIGH_SCORE_LOSS",
                            amount=hsl_amount,
                            description=desc,
                        )
                    )

    # 2. Season podium payouts for completed seasons (2022 and 2023)
    # week=None for podium awards
    for year in [2022, 2023]:
        s = session.query(Season).filter_by(season_year=year).first()
        if not s:
            continue
        t1 = teams[(year, 1)]  # 1st place Champion
        t2 = teams[(year, 2)]  # 2nd place Runner Up
        t3 = teams[(year, 3)]  # 3rd place Third Place

        ledger_entries.extend([
            EarningsLedger(
                manager_id=t1.manager_id,
                team_id=t1.id,
                season_year=year,
                week=None,
                entry_type="CHAMPION",
                amount=s.champion_payout,
                description=f"{year} League Champion Payout",
            ),
            EarningsLedger(
                manager_id=t2.manager_id,
                team_id=t2.id,
                season_year=year,
                week=None,
                entry_type="RUNNER_UP",
                amount=s.runner_up_payout,
                description=f"{year} League Runner-Up Payout",
            ),
            EarningsLedger(
                manager_id=t3.manager_id,
                team_id=t3.id,
                season_year=year,
                week=None,
                entry_type="THIRD_PLACE",
                amount=s.third_place_payout,
                description=f"{year} 3rd Place Playoff Payout",
            ),
        ])

    session.add_all(ledger_entries)
    session.flush()


def _seed_raw_snapshots_and_sync_runs(session: Session) -> None:
    """Seed raw JSON payload snapshots and ingestion audit records."""
    views = ["mSettings", "mTeam", "mMatchupScore", "mTransactions2"]
    snapshots: list[RawEspnSnapshot] = []

    for year in [2022, 2023, 2024]:
        for view in views:
            snap = RawEspnSnapshot(
                season_year=year,
                view_name=view,
                scoring_period=0,
                payload={
                    "seasonId": year,
                    "view": view,
                    "status": "archived",
                    "data": {"leagueId": "12345678", "seasonYear": year},
                },
                fetched_at=datetime(year, 12, 31, 23, 59, tzinfo=UTC),
            )
            snapshots.append(snap)

    session.add_all(snapshots)

    # Sync run audit records
    runs = [
        SyncRun(
            run_type="BACKFILL",
            season_year=2022,
            week_range="1-17",
            status="SUCCESS",
            records_processed=340,
            started_at=datetime(2023, 1, 1, 0, 0, tzinfo=UTC),
            completed_at=datetime(2023, 1, 1, 0, 5, tzinfo=UTC),
        ),
        SyncRun(
            run_type="BACKFILL",
            season_year=2023,
            week_range="1-17",
            status="SUCCESS",
            records_processed=420,
            started_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 1, 0, 6, tzinfo=UTC),
        ),
        SyncRun(
            run_type="WEEKLY_CRON",
            season_year=2024,
            week_range="7-8",
            status="SUCCESS",
            records_processed=36,
            started_at=datetime(2024, 10, 22, 10, 0, tzinfo=UTC),
            completed_at=datetime(2024, 10, 22, 10, 1, tzinfo=UTC),
        ),
    ]
    session.add_all(runs)
    session.flush()


def main() -> None:
    """CLI Entrypoint for make seed."""
    print("🌱 Seeding development database (3 seasons: 2022, 2023, 2024)...")
    counts = seed_database()
    print("✅ Database successfully seeded with:")
    for table, count in sorted(counts.items()):
        print(f"   - {table:20s}: {count:4d} records")


if __name__ == "__main__":
    main()
    sys.exit(0)
