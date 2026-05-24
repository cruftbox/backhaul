import httpx
import logging

logger = logging.getLogger(__name__)

SPORTS_CONFIG = {
    "epl": {
        "name": "EPL",
        "full_name": "English Premier League",
        "scoreboard_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
        "teams_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams",
        "score_label": "GOAL",
        "period_format": "soccer",
    },
    "nfl": {
        "name": "NFL",
        "full_name": "NFL",
        "scoreboard_url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "teams_url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams",
        "score_label": "SCORE",
        "period_format": "football",
    },
    "nba": {
        "name": "NBA",
        "full_name": "NBA",
        "scoreboard_url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "teams_url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams",
        "score_label": "SCORE",
        "period_format": "basketball",
    },
    "mlb": {
        "name": "MLB",
        "full_name": "MLB",
        "scoreboard_url": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
        "teams_url": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams",
        "score_label": "SCORE",
        "period_format": "baseball",
    },
    "nhl": {
        "name": "NHL",
        "full_name": "NHL",
        "scoreboard_url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
        "teams_url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams",
        "score_label": "GOAL",
        "period_format": "hockey",
    },
}


async def fetch_teams(sport: str) -> list[dict]:
    """Fetch all teams for a sport from the ESPN teams endpoint."""
    config = SPORTS_CONFIG.get(sport)
    if not config:
        return []

    all_teams = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            page = 1
            while True:
                resp = await client.get(config["teams_url"], params={"limit": 50, "page": page})
                resp.raise_for_status()
                data = resp.json()

                sports_data = data.get("sports", [{}])[0]
                leagues_data = sports_data.get("leagues", [{}])[0]
                teams_data = leagues_data.get("teams", [])

                if not teams_data:
                    break

                for entry in teams_data:
                    team = entry.get("team", entry)
                    espn_id = str(team.get("id", ""))
                    name = team.get("displayName") or team.get("name", "")
                    abbr = team.get("abbreviation", "")
                    if espn_id and name:
                        all_teams.append({
                            "espn_id": espn_id,
                            "name": name,
                            "abbreviation": abbr,
                        })

                page_count = data.get("pageCount", 1)
                if page >= page_count:
                    break
                page += 1

    except Exception as e:
        logger.error(f"Error fetching teams for {sport}: {e}")

    return sorted(all_teams, key=lambda t: t["name"])


async def fetch_scoreboard(sport: str) -> list[dict]:
    """Fetch current scoreboard for a sport. Returns parsed list of game dicts."""
    config = SPORTS_CONFIG.get(sport)
    if not config:
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(config["scoreboard_url"])
            resp.raise_for_status()
            data = resp.json()

        games = []
        for event in data.get("events", []):
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])

            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            status = event.get("status", {})
            status_type = status.get("type", {})
            status_name = status_type.get("name", "STATUS_SCHEDULED")
            display_clock = status.get("displayClock", "")
            short_detail = status_type.get("shortDetail", "")
            period = status.get("period", 0)

            if "FINAL" in status_name or "END_OF_GAME" in status_name:
                game_status = "final"
            elif "IN_PROGRESS" in status_name or "HALFTIME" in status_name:
                game_status = "in_progress"
            else:
                game_status = "pre"

            clock = display_clock or short_detail
            period_detail = _format_period(sport, period, clock, status_name)

            games.append({
                "game_id": str(event.get("id", "")),
                "name": event.get("name", ""),
                "status": game_status,
                "period_detail": period_detail,
                "home": {
                    "espn_id": str(home.get("team", {}).get("id", "")),
                    "name": home.get("team", {}).get("displayName", ""),
                    "abbreviation": home.get("team", {}).get("abbreviation", ""),
                    "score": _parse_score(home.get("score")),
                },
                "away": {
                    "espn_id": str(away.get("team", {}).get("id", "")),
                    "name": away.get("team", {}).get("displayName", ""),
                    "abbreviation": away.get("team", {}).get("abbreviation", ""),
                    "score": _parse_score(away.get("score")),
                },
            })

        return games

    except Exception as e:
        logger.error(f"Error fetching scoreboard for {sport}: {e}")
        return []


def _parse_score(raw) -> int:
    try:
        return int(raw or 0)
    except (ValueError, TypeError):
        return 0


def _format_period(sport: str, period: int, clock: str, status_name: str) -> str:
    if "HALFTIME" in status_name:
        return "HT"
    if not period and not clock:
        return ""

    fmt = SPORTS_CONFIG.get(sport, {}).get("period_format", "")

    if fmt == "soccer":
        # clock is something like "45" or "67'"
        c = clock.rstrip("'")
        return f"{c}'" if c.isdigit() else clock

    elif fmt in ("football", "basketball"):
        labels = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4", 5: "OT"}
        q = labels.get(period, f"OT{period - 4}" if period > 4 else f"Q{period}")
        return f"{q} {clock}".strip() if clock else q

    elif fmt == "baseball":
        return short_detail_or(clock, period)

    elif fmt == "hockey":
        labels = {1: "P1", 2: "P2", 3: "P3", 4: "OT", 5: "SO"}
        p = labels.get(period, f"OT{period - 3}" if period > 3 else f"P{period}")
        return f"{p} {clock}".strip() if clock else p

    return clock


def short_detail_or(clock: str, period: int) -> str:
    """For baseball, ESPN provides descriptive strings like 'Top 7th'."""
    return clock if clock else f"Inning {period}"


def get_score_label(sport: str) -> str:
    return SPORTS_CONFIG.get(sport, {}).get("score_label", "SCORE")
