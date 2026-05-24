import aiosqlite
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/app/data/backhaul.db")

DEFAULT_SETTINGS = {
    "setup_complete": "false",
    "email_from": "",
    "email_password": "",
    "sms_to_number": "",
    "sms_carrier": "att",
    "dnd_enabled": "true",
    "dnd_start": "23:00",
    "dnd_end": "08:00",
    # Per-sport team strings (comma-separated abbreviations/names)
    "teams_epl": "",
    "teams_nfl": "",
    "teams_nba": "",
    "teams_mlb": "",
    "teams_nhl": "",
    # Per-sport notification prefs
    "notify_start_epl": "true",  "notify_score_epl": "true",  "notify_final_epl": "true",
    "notify_start_nfl": "true",  "notify_score_nfl": "true",  "notify_final_nfl": "true",
    "notify_start_nba": "true",  "notify_score_nba": "true",  "notify_final_nba": "true",
    "notify_start_mlb": "true",  "notify_score_mlb": "true",  "notify_final_mlb": "true",
    "notify_start_nhl": "true",  "notify_score_nhl": "true",  "notify_final_nhl": "true",
    # Per-sport poll intervals
    "poll_interval_epl": "5",
    "poll_interval_nfl": "5",
    "poll_interval_nba": "5",
    "poll_interval_mlb": "5",
    "poll_interval_nhl": "5",
}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport TEXT NOT NULL,
                espn_id TEXT NOT NULL,
                name TEXT NOT NULL,
                abbreviation TEXT NOT NULL,
                UNIQUE(sport, espn_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                notify_start INTEGER NOT NULL DEFAULT 1,
                notify_score INTEGER NOT NULL DEFAULT 1,
                notify_final INTEGER NOT NULL DEFAULT 1,
                UNIQUE(team_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport TEXT NOT NULL,
                game_id TEXT NOT NULL,
                home_espn_id TEXT NOT NULL,
                away_espn_id TEXT NOT NULL,
                home_name TEXT NOT NULL DEFAULT '',
                away_name TEXT NOT NULL DEFAULT '',
                home_score INTEGER NOT NULL DEFAULT 0,
                away_score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pre',
                period_detail TEXT NOT NULL DEFAULT '',
                last_updated TEXT NOT NULL,
                UNIQUE(sport, game_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                message TEXT NOT NULL,
                log_type TEXT NOT NULL DEFAULT 'info'
            )
        """)
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        await db.commit()


async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else DEFAULT_SETTINGS.get(key, "")


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


async def upsert_team(sport: str, espn_id: str, name: str, abbreviation: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO teams (sport, espn_id, name, abbreviation) VALUES (?, ?, ?, ?)",
            (sport, espn_id, name, abbreviation)
        )
        await db.commit()
        async with db.execute(
            "SELECT id FROM teams WHERE sport = ? AND espn_id = ?", (sport, espn_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_teams(sport: str = None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if sport:
            async with db.execute(
                "SELECT * FROM teams WHERE sport = ? ORDER BY name", (sport,)
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT * FROM teams ORDER BY sport, name") as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_subscriptions() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.id, s.team_id, s.notify_start, s.notify_score, s.notify_final,
                   t.name, t.sport, t.abbreviation, t.espn_id
            FROM subscriptions s
            JOIN teams t ON s.team_id = t.id
            ORDER BY t.sport, t.name
        """) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_subscribed_espn_ids(sport: str) -> set:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT t.espn_id FROM subscriptions s
            JOIN teams t ON s.team_id = t.id
            WHERE t.sport = ?
        """, (sport,)) as cursor:
            return {row[0] for row in await cursor.fetchall()}


async def subscribe_team(team_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (team_id) VALUES (?)", (team_id,)
        )
        await db.commit()


async def unsubscribe_team(team_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscriptions WHERE team_id = ?", (team_id,))
        await db.commit()


async def update_subscription_prefs(team_id: int, notify_start: int, notify_score: int, notify_final: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET notify_start=?, notify_score=?, notify_final=? WHERE team_id=?",
            (notify_start, notify_score, notify_final, team_id)
        )
        await db.commit()


async def get_subscription_for_team(team_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE team_id=?", (team_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_game_state(sport: str, game_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM game_state WHERE sport=? AND game_id=?", (sport, game_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def upsert_game_state(sport: str, game_id: str, home_espn_id: str, away_espn_id: str,
                             home_name: str, away_name: str, home_score: int, away_score: int,
                             status: str, period_detail: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO game_state
                (sport, game_id, home_espn_id, away_espn_id, home_name, away_name,
                 home_score, away_score, status, period_detail, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sport, game_id) DO UPDATE SET
                home_name=excluded.home_name,
                away_name=excluded.away_name,
                home_score=excluded.home_score,
                away_score=excluded.away_score,
                status=excluded.status,
                period_detail=excluded.period_detail,
                last_updated=excluded.last_updated
        """, (sport, game_id, home_espn_id, away_espn_id, home_name, away_name,
              home_score, away_score, status, period_detail, datetime.now().isoformat()))
        await db.commit()


async def get_live_games() -> list:
    """Return all in-progress games stored in game_state."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM game_state
            WHERE status = 'in_progress'
            ORDER BY sport, last_updated DESC
        """) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def add_activity_log(message: str, log_type: str = "info"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO activity_log (timestamp, message, log_type) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), message, log_type)
        )
        await db.execute("""
            DELETE FROM activity_log WHERE id NOT IN (
                SELECT id FROM activity_log ORDER BY id DESC LIMIT 100
            )
        """)
        await db.commit()


async def get_activity_log(limit: int = 50) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
