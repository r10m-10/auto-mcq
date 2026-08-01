"""Public configuration router.

Serves the ad/sponsor toggles and ad copy that the extension and website
read to respect the admin's switches. This endpoint is deliberately public
and carries only safe display toggles — no user data, no balances, no PII.

Ad slots (overlay / card / offerwall) are stored as JSON blobs under one
config key each, so the whole suite for a slot is a single atomic value.
Credit economy values (click costs + ad reward) are read live from the
existing `reward_config` table; the sandbox ad length lives in the config
table as `ad_seconds`.

The `config` key/value table is created here (deterministic, at import
time) so it exists the moment the router is wired. The protected
`app/db.py` schema is never touched.
"""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()

SLOT_KEYS = ("overlay", "card", "offerwall")

DEFAULT_SLOT = {
    "enabled": True,
    "source": "house",
    "ad_name": "VEDPREP CRASH COURSE",
    "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
    "ad_url": "https://automcq.reyaanshsharma.com",
    "ad_cta": "LEARN MORE",
    "third_party_html": "",
    "frequency_every": 3,
    "min_view_seconds": 0,
    "auto_close_seconds": 0,
}

DEFAULT_CONFIG = {
    "overlay_config": json.dumps(DEFAULT_SLOT),
    "card_config": json.dumps(DEFAULT_SLOT),
    "offerwall_config": json.dumps(DEFAULT_SLOT),
    "ad_seconds": "25",
}

CONFIG_KEYS = frozenset(DEFAULT_CONFIG.keys())

DEFAULT_REWARDS = {"normal_click": 1, "premium_click": 4, "ad_reward": 3}


class AdSlotConfig(BaseModel):
    enabled: bool
    source: str
    ad_name: str
    ad_sub: str
    ad_url: str
    ad_cta: str
    third_party_html: str
    frequency_every: int
    min_view_seconds: int
    auto_close_seconds: int


class PublicConfigResponse(BaseModel):
    # Backward-compatible flat keys, derived from the slot configs so the
    # existing consumers (extension popup, claim-watch, claim page) keep
    # working unchanged.
    sponsor_overlay_enabled: bool
    sponsor_card_enabled: bool
    offerwall_enabled: bool
    ad_name: str
    ad_sub: str
    ad_url: str
    # Structured per-slot configs.
    overlay_config: AdSlotConfig
    card_config: AdSlotConfig
    offerwall_config: AdSlotConfig
    # Credit economy.
    normal_cost: int
    fast_cost: int
    ad_reward: int
    ad_seconds: int


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


def _parse_slot(raw: dict[str, str], key: str) -> dict:
    """Parse a slot JSON blob, merging missing fields with defaults.

    Values are coerced so corrupt/legacy rows can never break the public
    response: bad JSON falls back to defaults, unknown sources become
    "house", numeric fields clamp to sane ranges.
    """
    slot = dict(DEFAULT_SLOT)
    try:
        data = json.loads(raw.get(key, ""))
    except (ValueError, TypeError):
        data = {}
    if isinstance(data, dict):
        for field in slot:
            if field in data:
                slot[field] = data[field]

    slot["enabled"] = bool(slot["enabled"])
    if slot["source"] not in ("house", "third_party"):
        slot["source"] = "house"
    slot["frequency_every"] = max(1, _int(slot["frequency_every"], 3))
    slot["min_view_seconds"] = max(0, _int(slot["min_view_seconds"], 0))
    slot["auto_close_seconds"] = max(0, _int(slot["auto_close_seconds"], 0))
    return slot


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _reward_amounts() -> dict[str, int]:
    """Read credit amounts live from reward_config (grant-time source)."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT action_type, credits FROM reward_config"
            ).fetchall()
        return {r["action_type"]: r["credits"] for r in rows}
    except Exception:
        return dict(DEFAULT_REWARDS)


def build_public_config(raw: dict[str, str]) -> PublicConfigResponse:
    overlay = _parse_slot(raw, "overlay_config")
    card = _parse_slot(raw, "card_config")
    offerwall = _parse_slot(raw, "offerwall_config")
    rewards = _reward_amounts()

    return PublicConfigResponse(
        sponsor_overlay_enabled=bool(overlay["enabled"]),
        sponsor_card_enabled=bool(card["enabled"]),
        offerwall_enabled=bool(offerwall["enabled"]),
        ad_name=overlay["ad_name"],
        ad_sub=overlay["ad_sub"],
        ad_url=overlay["ad_url"],
        overlay_config=AdSlotConfig(**overlay),
        card_config=AdSlotConfig(**card),
        offerwall_config=AdSlotConfig(**offerwall),
        normal_cost=rewards.get("normal_click", DEFAULT_REWARDS["normal_click"]),
        fast_cost=rewards.get("premium_click", DEFAULT_REWARDS["premium_click"]),
        ad_reward=rewards.get("ad_reward", DEFAULT_REWARDS["ad_reward"]),
        ad_seconds=_int(raw.get("ad_seconds"), 25),
    )


@router.get("/config", response_model=PublicConfigResponse)
def read_config():
    return build_public_config(get_config())


ensure_config_table()
