import asyncio
import logging

import database
import espn
import notifier

logger = logging.getLogger(__name__)

_running = False


def _team_matches(filters: list, home: dict, away: dict) -> bool:
    """Return True if any filter string matches a team in this game (Firstlight-style)."""
    abbrevs = {
        home.get("abbreviation", "").upper(),
        away.get("abbreviation", "").upper(),
    }
    names = {
        home.get("name", "").lower(),
        away.get("name", "").lower(),
    }
    return any(t.upper() in abbrevs or t.lower() in names for t in filters)


async def _process_games(sport: str, games: list, filters: list, settings: dict):
    """Check each game for state changes and fire notifications."""
    notify_start = settings.get(f"notify_start_{sport}") == "true"
    notify_score = settings.get(f"notify_score_{sport}") == "true"
    notify_final = settings.get(f"notify_final_{sport}") == "true"

    for game in games:
        home = game["home"]
        away = game["away"]

        if not _team_matches(filters, home, away):
            continue

        game_id = game["game_id"]
        cur_status = game["status"]
        cur_home_score = home["score"]
        cur_away_score = away["score"]
        period_detail = game["period_detail"]

        prev = await database.get_game_state(sport, game_id)

        # Game started (pre → in_progress). Only notify if we've seen it as 'pre'
        # so a poller restart mid-game doesn't re-fire the start notification.
        if (cur_status == "in_progress"
                and prev is not None
                and prev["status"] == "pre"
                and notify_start):
            await notifier.notify_game_start(sport, home["name"], away["name"])

        # Score changed during a live game
        if (cur_status == "in_progress"
                and prev is not None
                and prev["status"] == "in_progress"
                and (cur_home_score != prev["home_score"] or cur_away_score != prev["away_score"])
                and notify_score):
            await notifier.notify_score_change(
                sport, home["name"], away["name"],
                cur_home_score, cur_away_score, period_detail
            )

        # Game just ended
        if (cur_status == "final"
                and prev is not None
                and prev["status"] != "final"
                and notify_final):
            await notifier.notify_final(
                sport, home["name"], away["name"],
                cur_home_score, cur_away_score
            )

        # Persist current state
        await database.upsert_game_state(
            sport, game_id,
            home["espn_id"], away["espn_id"],
            home["name"], away["name"],
            cur_home_score, cur_away_score,
            cur_status, period_detail
        )


async def _get_poll_interval_seconds(sport: str, settings: dict) -> int:
    raw = settings.get(f"poll_interval_{sport}", "5")
    try:
        return max(1, int(raw)) * 60
    except (ValueError, TypeError):
        return 300


async def run_poller():
    global _running
    _running = True
    logger.info("Poller started")
    await database.add_activity_log("Poller started", "info")

    # next_poll[sport] = monotonic time when we should next poll that sport
    next_poll: dict = {}

    while _running:
        settings = await database.get_all_settings()

        if settings.get("setup_complete") != "true":
            await asyncio.sleep(30)
            continue

        now = asyncio.get_event_loop().time()

        for sport in espn.SPORTS_CONFIG:
            if now < next_poll.get(sport, 0):
                continue

            teams_str = settings.get(f"teams_{sport}", "").strip()
            if not teams_str:
                # No teams configured for this sport — check again in an hour
                next_poll[sport] = now + 3600
                continue

            filters = [t.strip() for t in teams_str.split(",") if t.strip()]
            if not filters:
                next_poll[sport] = now + 3600
                continue

            try:
                games = await espn.fetch_scoreboard(sport)

                relevant = [g for g in games if _team_matches(filters, g["home"], g["away"])]

                if relevant:
                    await _process_games(sport, games, filters, settings)
                    interval = await _get_poll_interval_seconds(sport, settings)
                    logger.debug(f"Polled {sport}: {len(relevant)} relevant game(s), next in {interval}s")
                else:
                    interval = 3600  # back off — no matching games today
                    logger.debug(f"No matching games for {sport} today, backing off 1h")

                next_poll[sport] = now + interval

            except Exception as e:
                logger.error(f"Poller error [{sport}]: {e}")
                await database.add_activity_log(f"Poll error ({sport}): {e}", "error")
                next_poll[sport] = now + 300  # retry in 5 min

        await asyncio.sleep(15)
