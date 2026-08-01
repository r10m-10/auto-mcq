"""Ad metrics intake — public, fire-and-forget.

The extension and claim page POST lightweight impression / click / close
events for each ad slot so the admin panel can show real usage numbers.
The endpoint is deliberately public and carries only an event type, a slot
name, and an optional device id — no balances, no PII.

The `ad_events` table is created here (deterministic, at import time) so
it exists the moment the router is wired. The protected `app/db.py`
schema is never touched.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()

VALID_SLOTS = ("overlay", "card", "offerwall")
VALID_EVENTS = ("impression", "click", "close")


class AdEventRequest(BaseModel):
    slot: str
    event_type: str
    device_id: str | None = None


def ensure_ads_table():
    """Create the ad_events table. Idempotent; runs at import time."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot TEXT NOT NULL,
                event_type TEXT NOT NULL,
                device_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


@router.post("/ads/event", status_code=201)
def record_ad_event(body: AdEventRequest):
    if body.slot not in VALID_SLOTS:
        raise HTTPException(status_code=422, detail=f"Unknown slot: {body.slot}")
    if body.event_type not in VALID_EVENTS:
        raise HTTPException(status_code=422, detail=f"Unknown event_type: {body.event_type}")

    ensure_ads_table()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO ad_events (slot, event_type, device_id) VALUES (?, ?, ?)",
            (body.slot, body.event_type, body.device_id),
        )
    return {"ok": True}


ensure_ads_table()
