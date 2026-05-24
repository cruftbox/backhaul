import asyncio
import logging
import smtplib
from datetime import datetime, time as dtime
from email.mime.text import MIMEText

import database
from espn import get_score_label

logger = logging.getLogger(__name__)

CARRIER_GATEWAYS = {
    "att":      "txt.att.net",
    "verizon":  "vtext.com",
    "tmobile":  "tmomail.net",
    "sprint":   "messaging.sprintpcs.com",
    "boost":    "sms.myboostmobile.com",
    "cricket":  "sms.cricketwireless.net",
}


def _in_dnd_window(start_str: str, end_str: str) -> bool:
    """Return True if current local time falls within the DND window."""
    try:
        now = datetime.now().time()
        h, m = map(int, start_str.split(":"))
        start = dtime(h, m)
        h, m = map(int, end_str.split(":"))
        end = dtime(h, m)
        if start > end:  # spans midnight
            return now >= start or now < end
        return start <= now < end
    except Exception:
        return False


def _send_email_sync(from_addr: str, password: str, to_addr: str, message: str):
    """Blocking SMTP send — run in executor to avoid blocking the event loop."""
    msg = MIMEText(message)
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = ""  # empty subject keeps it clean as SMS

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(from_addr, password)
        server.send_message(msg)


async def send_notification(message: str, log_type: str = "notification"):
    """Send an SMS via email-to-SMS gateway, honouring DND."""
    settings = await database.get_all_settings()

    if settings.get("dnd_enabled", "true") == "true":
        dnd_start = settings.get("dnd_start", "23:00")
        dnd_end = settings.get("dnd_end", "08:00")
        if _in_dnd_window(dnd_start, dnd_end):
            logger.info(f"DND suppressed: {message}")
            await database.add_activity_log(f"[DND suppressed] {message}", "suppressed")
            return

    from_addr = settings.get("email_from", "").strip()
    password = settings.get("email_password", "").strip()
    to_number = settings.get("sms_to_number", "").strip().replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    carrier = settings.get("sms_carrier", "att").strip()

    if not all([from_addr, password, to_number]):
        logger.warning("Email/SMS not configured — notification not sent")
        return

    gateway = CARRIER_GATEWAYS.get(carrier, "txt.att.net")
    to_addr = f"{to_number}@{gateway}"

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_email_sync, from_addr, password, to_addr, message)
        logger.info(f"SMS sent to {to_addr}: {message}")
        await database.add_activity_log(message, log_type)
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        await database.add_activity_log(f"SMS failed: {e}", "error")


async def notify_game_start(sport: str, home_name: str, away_name: str):
    msg = f"{away_name} vs {home_name} has kicked off"
    await send_notification(msg)


async def notify_score_change(sport: str, home_name: str, away_name: str,
                               home_score: int, away_score: int, period_detail: str):
    label = get_score_label(sport)
    score = f"{away_name} {away_score}-{home_score} {home_name}"
    period = f" ({period_detail})" if period_detail else ""
    msg = f"{label} — {score}{period}"
    await send_notification(msg)


async def notify_final(sport: str, home_name: str, away_name: str,
                        home_score: int, away_score: int):
    score = f"{away_name} {away_score}-{home_score} {home_name}"
    msg = f"FINAL — {score}"
    await send_notification(msg)
