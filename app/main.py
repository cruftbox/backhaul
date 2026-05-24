import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
import espn
import notifier
import poller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    task = asyncio.create_task(poller.run_poller())
    logger.info("Backhaul started on port 8000")
    yield
    poller._running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan, title="Backhaul")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


async def _is_setup_complete() -> bool:
    return await database.get_setting("setup_complete") == "true"


# ── Home ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not await _is_setup_complete():
        return RedirectResponse("/setup/1", status_code=302)

    settings = await database.get_all_settings()
    live_games = await database.get_live_games()
    activity = await database.get_activity_log(50)

    # Build per-sport teams dict (only sports with teams configured)
    teams_by_sport = {
        sport: settings.get(f"teams_{sport}", "").strip()
        for sport in espn.SPORTS_CONFIG
        if settings.get(f"teams_{sport}", "").strip()
    }

    return templates.TemplateResponse("index.html", {
        "request": request,
        "teams_by_sport": teams_by_sport,
        "live_games": live_games,
        "activity": activity,
        "settings": settings,
        "sports_config": espn.SPORTS_CONFIG,
    })


# ── Setup wizard ──────────────────────────────────────────────────────────────

@app.get("/setup/1", response_class=HTMLResponse)
async def setup1_get(request: Request):
    settings = await database.get_all_settings()
    return templates.TemplateResponse("setup_1.html", {
        "request": request,
        "settings": settings,
        "step": 1,
    })


@app.post("/setup/1")
async def setup1_post(
    email_from: str = Form(""),
    email_password: str = Form(""),
    sms_to_number: str = Form(""),
    sms_carrier: str = Form("att"),
):
    await database.set_setting("email_from", email_from.strip())
    await database.set_setting("email_password", email_password.strip())
    await database.set_setting("sms_to_number", sms_to_number.strip())
    await database.set_setting("sms_carrier", sms_carrier.strip())
    return RedirectResponse("/setup/2", status_code=302)


@app.get("/setup/2", response_class=HTMLResponse)
async def setup2_get(request: Request):
    settings = await database.get_all_settings()
    return templates.TemplateResponse("setup_2.html", {
        "request": request,
        "settings": settings,
        "sports_config": espn.SPORTS_CONFIG,
        "step": 2,
    })


@app.post("/setup/2")
async def setup2_post(request: Request):
    form = await request.form()
    for sport in espn.SPORTS_CONFIG:
        await database.set_setting(f"teams_{sport}", form.get(f"teams_{sport}", "").strip())
        await database.set_setting(f"notify_start_{sport}", "true" if form.get(f"notify_start_{sport}") else "false")
        await database.set_setting(f"notify_score_{sport}", "true" if form.get(f"notify_score_{sport}") else "false")
        await database.set_setting(f"notify_final_{sport}", "true" if form.get(f"notify_final_{sport}") else "false")
    await database.set_setting("setup_complete", "true")
    return RedirectResponse("/", status_code=302)


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    if not await _is_setup_complete():
        return RedirectResponse("/setup/1", status_code=302)

    settings = await database.get_all_settings()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "sports_config": espn.SPORTS_CONFIG,
    })


@app.post("/settings")
async def settings_post(request: Request):
    form = await request.form()

    # SMS / email-to-SMS
    for key in ["email_from", "sms_to_number", "sms_carrier"]:
        val = form.get(key, "").strip()
        if val:
            await database.set_setting(key, val)
    # Only overwrite password if a new one was entered
    pw = form.get("email_password", "").strip()
    if pw:
        await database.set_setting("email_password", pw)

    # DND
    await database.set_setting("dnd_enabled", "true" if form.get("dnd_enabled") else "false")
    await database.set_setting("dnd_start", form.get("dnd_start", "23:00"))
    await database.set_setting("dnd_end", form.get("dnd_end", "08:00"))

    # Per-sport: teams, notification prefs, poll interval
    for sport in espn.SPORTS_CONFIG:
        await database.set_setting(f"teams_{sport}", form.get(f"teams_{sport}", "").strip())
        await database.set_setting(f"notify_start_{sport}", "true" if form.get(f"notify_start_{sport}") else "false")
        await database.set_setting(f"notify_score_{sport}", "true" if form.get(f"notify_score_{sport}") else "false")
        await database.set_setting(f"notify_final_{sport}", "true" if form.get(f"notify_final_{sport}") else "false")
        raw = form.get(f"poll_interval_{sport}", "5").strip()
        try:
            val = str(max(1, int(raw)))
        except ValueError:
            val = "5"
        await database.set_setting(f"poll_interval_{sport}", val)

    return RedirectResponse("/settings", status_code=302)


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/activity")
async def api_activity():
    return await database.get_activity_log(50)


@app.post("/api/test-notification")
async def api_test_notification():
    try:
        await notifier.send_notification("Backhaul: test notification — if you got this, it's working.", log_type="info")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
