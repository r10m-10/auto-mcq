"""Public configuration router.

Serves the ad/sponsor toggles and ad copy that the extension reads to
respect the admin's switches. This endpoint is deliberately public and
carries only safe display toggles — no user data, no balances, no PII.

The `config` key/value table is created here (deterministic, at import
time) so it exists the moment the router is wired. The protected
`app/db.py` schema is never touched.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()

DEFAULT_CONFIG = {
    "sponsor_overlay_enabled": "true",
    "sponsor_card_enabled": "true",
    "offerwall_enabled": "true",
    "ad_name": "VEDPREP CRASH COURSE",
    "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
    "ad_url": "https://automcq.reyaanshsharma.com",
}

CONFIG_KEYS = frozenset(DEFAULT_CONFIG.keys())


class PublicConfigResponse(BaseModel):
    sponsor_overlay_enabled: bool
    sponsor_card_enabled: bool
    offerwall_enabled: bool
    ad_name: str
    ad_sub: str
    ad_url: str


def ensure_config_table():
    """Create the config table and seed defaults. Idempotent.

    Runs at import time (module bottom) so the table is guaranteed present
    before any request, and called again by any router that reads config
    in case imports are reordered. INSERT OR IGNORE keeps admin edits.
    """
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
            [(k, v) for k, v in DEFAULT_CONFIG.items()],
        )


def get_config() -> dict[str, str]:
    """Return the full config as a {key: value} dict."""
    ensure_config_table()
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM config").fetchall()
    return {row["key"]: row["value"] for row in rows}


def _bool(key: str, raw: dict[str, str]) -> bool:
    return raw.get(key, "true").lower() == "true"


def build_public_config(raw: dict[str, str]) -> PublicConfigResponse:
    return PublicConfigResponse(
        sponsor_overlay_enabled=_bool("sponsor_overlay_enabled", raw),
        sponsor_card_enabled=_bool("sponsor_card_enabled", raw),
        offerwall_enabled=_bool("offerwall_enabled", raw),
        ad_name=raw.get("ad_name", DEFAULT_CONFIG["ad_name"]),
        ad_sub=raw.get("ad_sub", DEFAULT_CONFIG["ad_sub"]),
        ad_url=raw.get("ad_url", DEFAULT_CONFIG["ad_url"]),
    )


@router.get("/config", response_model=PublicConfigResponse)
def read_config():
    return build_public_config(get_config())


ensure_config_table()
