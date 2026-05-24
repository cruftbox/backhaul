# Backhaul — Claude Code Build Prompt

Build a Dockerized sports notification web application called **Backhaul** that runs on a QNAP NAS.

## Core Functionality

- Web UI for selecting teams to follow across multiple sports leagues
- Background polling of the ESPN public API for live score updates
- Score change detection that triggers SMS notifications via Twilio
- Notifications for: game start, goals/scores, and final whistle

## ESPN API Endpoints to Support

- EPL: `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard`
- NFL: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`
- NBA: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard`
- MLB: `https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard`
- NHL: `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard`

## Tech Stack

- Python with FastAPI for the backend
- Polling interval configurable per sport, defaulting to 5 minutes for live games
- SQLite for persisting team subscriptions and last known scores
- Twilio API for SMS notifications
- Simple clean HTML/CSS/JS frontend with no heavy frameworks
- Docker with a single `docker-compose.yml` suitable for QNAP Container Station, exposing the app on host port **8091**

## Web UI Requirements

The app has a single home page for day-to-day use, plus a paged setup/config flow (following the same pattern as Firstlight's setup wizard).

**Home page (`/`):**
- Currently live games for subscribed teams with current score
- Full list of subscribed teams with per-team notification toggles (match start, score, final) inline
- Activity log showing recent notifications sent
- Link to settings

**First-run setup wizard (`/setup/1`, `/setup/2`, …):**
- Redirects here automatically if Twilio credentials are not yet configured
- Step 1: Twilio credentials (Account SID, Auth Token, from-number)
- Step 2: Destination phone number
- Step 3: Sport selection — which leagues to follow (enables team browsing for those sports)
- Each step saves to SQLite on POST and redirects to the next step; survives page refresh

**Settings (`/settings`):**
- All setup fields editable after initial setup
- Do Not Disturb window (start/end time, enable/disable)
- Per-sport poll intervals
- Team browser: browse and search teams by sport/league in an alphabetical list, toggle subscriptions on/off

## Notification Preferences

Per-team notification settings, not global — each subscribed team should have independent toggles for:

- Match start
- Scoring event (goal, touchdown, basket, etc.)
- Final score

Defaults to all three enabled when a team is first subscribed. Toggles should be accessible directly in the team subscription list without navigating to a separate settings page. Notification preference changes should persist immediately to SQLite without requiring a save button.

### Do Not Disturb

A global do-not-disturb window suppresses all SMS notifications during quiet hours in the host system's local timezone. Default: **11:00 PM – 8:00 AM**. Configurable (start time, end time) via the settings page. Can be disabled entirely. Notifications that fire during DND are silently dropped (not queued for later delivery).

## Polling Behavior

- Only poll actively during reasonable game hours
- Poll at full rate only when a subscribed team has a game scheduled that day
- Back off to once per hour when no games are scheduled
- Detect and notify on: game starting, score change (with new score in message), game final
- Default live-game poll interval: 5 minutes, configurable per sport via the Web UI

## Notification Message Format Examples

```
Backhaul: Tottenham vs Everton has kicked off
Backhaul: GOAL — Tottenham 2-0 Everton (67')
Backhaul: FINAL — Tottenham 2-0 Everton
```

## Project Structure

```
backhaul/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py
│   ├── poller.py
│   ├── notifier.py
│   ├── espn.py
│   ├── database.py
│   ├── templates/
│   │   ├── base.html        # shared layout, nav
│   │   ├── index.html       # home page
│   │   ├── setup_1.html     # Twilio credentials
│   │   ├── setup_2.html     # destination phone number
│   │   ├── setup_3.html     # sport/league selection
│   │   └── settings.html    # all settings + team browser
│   └── static/
│       ├── style.css
│       └── app.js
```

## Reference

The team selection UI should follow a similar pattern to the Firstlight project — browsing leagues, searching for teams by name, and toggling subscriptions. Reuse any patterns from that codebase where applicable.

- Local path: `C:\Users\micha\OneDrive\Code\firstlight`
- GitHub: https://github.com/cruftbox/firstlight

Notable Firstlight patterns to reuse:
- Multi-step setup wizard (one route per step, saves incrementally, redirects forward)
- Settings page with pre-filled form values rendered server-side; no save button needed for toggles (auto-persist via API call on change)
- Show/hide dependent UI sections via lightweight JS on checkbox/toggle change, no heavy framework

## Constraints

- All configuration (Twilio credentials, phone number, polling intervals, DND window) must be editable through the Web UI and persisted to SQLite — not hardcoded or stored in environment variables
- The app should survive container restarts with all subscriptions and settings intact
- Logging should be visible in Docker logs as well as the Web UI activity feed
- No authentication required — the app is hosted on a local network only
- Team lists are populated from ESPN API responses (teams that appear in league scoreboards); seed the list on first load per sport, refresh periodically
