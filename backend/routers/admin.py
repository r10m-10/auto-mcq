"""Admin panel router — the ownly-accessible control room.

Two auth layers, both fail closed:

  Layer 1 (proxy): Caddy basic_auth in front of /admin* — configured on the
  VPS, outside this repo. The dashboard HTML is only reachable through that
  gate.

  Layer 2 (app): every /admin/api/* call must send
  `Authorization: Bearer <ADMIN_TOKEN>`. The token comes from the
  ADMIN_TOKEN env var, read at request time (so setting the env on the VPS
  needs no code change). When ADMIN_TOKEN is unset, ALL /admin* routes
  return 404 — the panel is completely invisible until configured.

  Tokens are compared in constant time to avoid timing leaks.

Endpoints (all JSON under /admin/api/* except the page itself):
  GET    /admin                                  dashboard HTML
  GET    /admin/api/stats                        overview numbers
  GET    /admin/api/devices                      all devices
  GET    /admin/api/devices/{id}                 one device + its ledger
  DELETE /admin/api/devices/{id}                 reuses device_delete logic
  POST   /admin/api/devices/{id}/credits         arbitrary +/- adjust
  GET    /admin/api/activity                     30-day series for the chart
  GET    /admin/api/config                       read ad toggles
  PUT    /admin/api/config                       write ad toggles
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from app.db import get_db
from app.models import CreditEventResponse
from routers.config import (
    CONFIG_KEYS,
    DEFAULT_CONFIG,
    build_public_config,
    ensure_config_table,
    get_config,
    PublicConfigResponse,
)
from routers.device_delete import delete_device as delete_device_impl
from routers.device_delete import DeleteDeviceResponse

router = APIRouter()

ADMIN_TOKEN_ENV = "ADMIN_TOKEN"


def _admin_token() -> str | None:
    return os.environ.get(ADMIN_TOKEN_ENV)


def require_admin(authorization: str | None = Header(default=None)):
    """Fail-closed gate for /admin/api/*.

    404 when ADMIN_TOKEN is unset (panel disabled), 401 on missing or
    wrong credentials. Constant-time comparison.
    """
    expected = _admin_token()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def _require_page_access():
    """404 when ADMIN_TOKEN is unset, so the panel is invisible until
    configured. The page itself is gated by Caddy basic_auth (layer 1)."""
    if not _admin_token():
        raise HTTPException(status_code=404, detail="Not found")
    return True


def _validate_uuid(device_id: str) -> str:
    try:
        uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{device_id}' is not a valid UUID")
    return device_id


def _get_user(conn, device_id: str):
    return conn.execute(
        "SELECT device_id, credits_balance, created_at FROM users WHERE device_id = ?",
        (device_id,),
    ).fetchone()


def _last_activity(conn, device_id: str):
    row = conn.execute(
        "SELECT MAX(timestamp) AS last_ts FROM credit_events WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    return row["last_ts"]


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------


class AdminStats(BaseModel):
    total_devices: int
    total_credits_issued: int
    total_credits_spent: int
    total_balance: int
    claim_count: int
    click_count: int
    active_devices_today: int


class AdminDeviceRow(BaseModel):
    device_id: str
    credits_balance: int
    created_at: str
    last_activity: str | None


class AdminDeviceDetail(BaseModel):
    device_id: str
    credits_balance: int
    created_at: str
    last_activity: str | None
    ledger: list[CreditEventResponse]


class CreditAdjustRequest(BaseModel):
    delta: int = Field(ge=-1000, le=1000)

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must be non-zero")
        return v


class CreditAdjustResponse(BaseModel):
    device_id: str
    credits_balance: int
    delta: int


class ActivityPoint(BaseModel):
    date: str
    claims: int
    clicks: int
    active_devices: int


class ConfigUpdateRequest(BaseModel):
    sponsor_overlay_enabled: bool | None = None
    sponsor_card_enabled: bool | None = None
    offerwall_enabled: bool | None = None
    ad_name: str | None = None
    ad_sub: str | None = None
    ad_url: str | None = None


# --------------------------------------------------------------------------
# Dashboard page
# --------------------------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(_require_page_access)])
def admin_page():
    return ADMIN_HTML


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


@router.get("/admin/api/stats", response_model=AdminStats, dependencies=[Depends(require_admin)])
def admin_stats():
    with get_db() as conn:
        total_devices = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_balance = conn.execute(
            "SELECT COALESCE(SUM(credits_balance), 0) FROM users"
        ).fetchone()[0]
        issued = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) FROM credit_events WHERE delta > 0"
        ).fetchone()[0]
        spent = conn.execute(
            "SELECT COALESCE(SUM(-delta), 0) FROM credit_events WHERE delta < 0"
        ).fetchone()[0]
        claims = conn.execute(
            "SELECT COUNT(*) FROM credit_events WHERE reason = 'ad_reward'"
        ).fetchone()[0]
        clicks = conn.execute(
            "SELECT COUNT(*) FROM credit_events WHERE reason IN ('normal_click', 'premium_click')"
        ).fetchone()[0]
        active_today = conn.execute(
            """
            SELECT COUNT(DISTINCT device_id) FROM credit_events
            WHERE date(timestamp) = date('now')
            """
        ).fetchone()[0]

    return AdminStats(
        total_devices=total_devices,
        total_credits_issued=issued,
        total_credits_spent=spent,
        total_balance=total_balance,
        claim_count=claims,
        click_count=clicks,
        active_devices_today=active_today,
    )


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------


@router.get("/admin/api/devices", response_model=list[AdminDeviceRow], dependencies=[Depends(require_admin)])
def admin_devices():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT u.device_id, u.credits_balance, u.created_at,
                   (SELECT MAX(ce.timestamp) FROM credit_events ce
                    WHERE ce.device_id = u.device_id) AS last_activity
            FROM users u
            ORDER BY u.created_at DESC
            """
        ).fetchall()
    return [
        AdminDeviceRow(
            device_id=r["device_id"],
            credits_balance=r["credits_balance"],
            created_at=r["created_at"],
            last_activity=r["last_activity"],
        )
        for r in rows
    ]


@router.get("/admin/api/devices/{device_id}", response_model=AdminDeviceDetail, dependencies=[Depends(require_admin)])
def admin_device_detail(device_id: str):
    _validate_uuid(device_id)
    with get_db() as conn:
        user = _get_user(conn, device_id)
        if not user:
            raise HTTPException(status_code=404, detail="Device not found")
        ledger_rows = conn.execute(
            """
            SELECT id, device_id, delta, reason, source, timestamp
            FROM credit_events
            WHERE device_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 100
            """,
            (device_id,),
        ).fetchall()
        last_activity = _last_activity(conn, device_id)

    return AdminDeviceDetail(
        device_id=user["device_id"],
        credits_balance=user["credits_balance"],
        created_at=user["created_at"],
        last_activity=last_activity,
        ledger=[CreditEventResponse(**dict(r)) for r in ledger_rows],
    )


@router.delete("/admin/api/devices/{device_id}", response_model=DeleteDeviceResponse, dependencies=[Depends(require_admin)])
def admin_delete_device(device_id: str):
    """Reuses the existing device_delete logic — no reimplementation."""
    return delete_device_impl(device_id=device_id)


@router.post("/admin/api/devices/{device_id}/credits", response_model=CreditAdjustResponse, dependencies=[Depends(require_admin)])
def admin_adjust_credits(device_id: str, body: CreditAdjustRequest):
    """Arbitrary credit adjustment (admin grant or penalty).

    Uses a dedicated ledger insert with source='admin_adjust' so the change
    is auditable and never confused with a sandbox/offerwall grant. The
    balance is clamped at zero — an adjust that would take a user below 0
    fails instead of going negative.
    """
    _validate_uuid(device_id)
    with get_db() as conn:
        user = _get_user(conn, device_id)
        if not user:
            raise HTTPException(status_code=404, detail="Device not found")

        new_balance = user["credits_balance"] + body.delta
        if new_balance < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Adjustment would take balance below zero (have {user['credits_balance']}, delta {body.delta})",
            )

        conn.execute(
            "UPDATE users SET credits_balance = ? WHERE device_id = ?",
            (new_balance, device_id),
        )
        conn.execute(
            "INSERT INTO credit_events (device_id, delta, reason, source) VALUES (?, ?, ?, ?)",
            (device_id, body.delta, "admin_adjust", "admin_adjust"),
        )

    return CreditAdjustResponse(device_id=device_id, credits_balance=new_balance, delta=body.delta)


# --------------------------------------------------------------------------
# Activity series
# --------------------------------------------------------------------------


@router.get("/admin/api/activity", response_model=list[ActivityPoint], dependencies=[Depends(require_admin)])
def admin_activity():
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    day_labels = [d.isoformat() for d in days]

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT date(timestamp) AS day,
                   SUM(CASE WHEN reason = 'ad_reward' THEN 1 ELSE 0 END) AS claims,
                   SUM(CASE WHEN reason IN ('normal_click', 'premium_click') THEN 1 ELSE 0 END) AS clicks,
                   COUNT(DISTINCT device_id) AS active_devices
            FROM credit_events
            WHERE date(timestamp) >= date('now', '-29 days')
            GROUP BY date(timestamp)
            """
        ).fetchall()

    by_day = {r["day"]: r for r in rows}
    points = []
    for label in day_labels:
        row = by_day.get(label)
        points.append(
            ActivityPoint(
                date=label,
                claims=row["claims"] if row else 0,
                clicks=row["clicks"] if row else 0,
                active_devices=row["active_devices"] if row else 0,
            )
        )
    return points


# --------------------------------------------------------------------------
# Config (ad toggles)
# --------------------------------------------------------------------------


@router.get("/admin/api/config", response_model=PublicConfigResponse, dependencies=[Depends(require_admin)])
def admin_get_config():
    return build_public_config(get_config())


@router.put("/admin/api/config", response_model=PublicConfigResponse, dependencies=[Depends(require_admin)])
def admin_update_config(body: ConfigUpdateRequest):
    ensure_config_table()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No config fields provided")

    bad = [k for k in updates if k not in CONFIG_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown config keys: {', '.join(bad)}")

    with get_db() as conn:
        for key, value in updates.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            conn.execute(
                """
                INSERT INTO config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )

    return build_public_config(get_config())


# --------------------------------------------------------------------------
# Dashboard HTML
# --------------------------------------------------------------------------

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoMCQ &middot; Admin</title>
<style>
  :root {
    --paper: #ECEFF4; --ink: #1E2128; --pencil: #6B7280;
    --pen-red: #C1440E; --correct-green: #2C8C5B;
    --line: rgba(30,33,40,0.14); --line-strong: rgba(30,33,40,0.28);
    --surface-card: rgba(255,255,255,0.6); --input-bg: #FFFFFF;
    --table-head-bg: rgba(30,33,40,0.05);
    --grid-line: rgba(30,33,40,0.025); --grid-line-weak: rgba(30,33,40,0.03);
    --shadow-color: rgba(30,33,40,0.85); --shadow-soft: rgba(30,33,40,0.25);
    --font-mono: "Space Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #15171C; --ink: #ECEFF4; --pencil: #9AA3B2;
      --pen-red: #E4703A; --correct-green: #3FA96F;
      --line: rgba(236,239,244,0.14); --line-strong: rgba(236,239,244,0.28);
      --surface-card: rgba(255,255,255,0.06); --input-bg: #23262E;
      --table-head-bg: rgba(236,239,244,0.06);
      --grid-line: rgba(236,239,244,0.03); --grid-line-weak: rgba(236,239,244,0.04);
      --shadow-color: rgba(236,239,244,0.5); --shadow-soft: rgba(236,239,244,0.25);
    }
  }
  :root[data-theme="dark"] {
    --paper: #15171C; --ink: #ECEFF4; --pencil: #9AA3B2;
    --pen-red: #E4703A; --correct-green: #3FA96F;
    --line: rgba(236,239,244,0.14); --line-strong: rgba(236,239,244,0.28);
    --surface-card: rgba(255,255,255,0.06); --input-bg: #23262E;
    --table-head-bg: rgba(236,239,244,0.06);
    --grid-line: rgba(236,239,244,0.03); --grid-line-weak: rgba(236,239,244,0.04);
    --shadow-color: rgba(236,239,244,0.5); --shadow-soft: rgba(236,239,244,0.25);
  }
  *, *::before, *::after { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: var(--font-sans); font-size: 1rem; line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  body::before {
    content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background-image:
      linear-gradient(to right, transparent 95%, var(--grid-line) 95%),
      repeating-linear-gradient(0deg, transparent, transparent 31px, var(--grid-line-weak) 31px, var(--grid-line-weak) 32px);
  }
  :focus-visible { outline: 3px solid var(--pen-red); outline-offset: 2px; }
  .container { width: min(1120px, 100% - 2.5rem); margin-inline: auto; }

  .site-header {
    border-bottom: 1px solid var(--line-strong); padding: 0.75rem 0;
    position: sticky; top: 0; z-index: 50;
    background: color-mix(in srgb, var(--paper) 92%, transparent);
    backdrop-filter: blur(6px);
  }
  .site-header .container { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
  .wordmark { font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.08em; font-size: 1.05rem; color: var(--ink); white-space: nowrap; }
  .wordmark .pen { color: var(--pen-red); }
  .header-actions { display: flex; align-items: center; gap: 0.75rem; }

  .tabs { display: flex; gap: 0.25rem; margin: 1.5rem 0; border-bottom: 2px solid var(--ink); flex-wrap: wrap; }
  .tab-btn {
    font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.08em;
    font-size: 0.85rem; padding: 0.6rem 1.1rem; border: none; cursor: pointer;
    background: transparent; color: var(--pencil); border-bottom: 3px solid transparent;
    margin-bottom: -2px;
  }
  .tab-btn:hover { color: var(--ink); }
  .tab-btn.active { color: var(--ink); border-bottom-color: var(--pen-red); }

  .card {
    background: var(--surface-card); border: 2px solid var(--ink);
    padding: 1.25rem; margin-bottom: 1.25rem;
  }
  .card-title { font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.1em; font-size: 0.85rem; margin: 0 0 1rem; }

  .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; }
  .stat {
    border: 2px solid var(--ink); background: var(--surface-card);
    padding: 1rem 1.1rem; box-shadow: 5px 5px 0 var(--shadow-soft);
  }
  .stat .num { font-family: var(--font-mono); font-weight: 700; font-size: 1.9rem; line-height: 1.1; }
  .stat .lbl { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.12em; color: var(--pencil); text-transform: uppercase; margin-top: 0.3rem; }

  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  thead th {
    text-align: left; font-family: var(--font-mono); font-size: 0.72rem;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--pencil);
    background: var(--table-head-bg); padding: 0.55rem 0.75rem; border-bottom: 2px solid var(--ink);
  }
  tbody td { padding: 0.55rem 0.75rem; border-bottom: 1px solid var(--line); vertical-align: top; }
  tbody tr:hover { background: var(--surface-card); }
  .mono { font-family: var(--font-mono); }
  .dim { color: var(--pencil); }
  .pos { color: var(--correct-green); font-weight: 700; }
  .neg { color: var(--pen-red); font-weight: 700; }
  .uuid-cell { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.78rem; }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem;
    font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.06em;
    font-size: 0.8rem; padding: 0.45rem 0.85rem; border: 2px solid var(--ink);
    border-radius: 0; cursor: pointer; color: var(--ink); background: transparent;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
  }
  .btn:hover { transform: translate(-2px,-2px); box-shadow: 3px 3px 0 var(--shadow-color); }
  .btn:active { transform: translate(0,0); box-shadow: none; }
  .btn-primary { background: var(--pen-red); border-color: var(--pen-red); color: #FFFFFF; }
  .btn-ghost { border-color: var(--line-strong); color: var(--pencil); }
  .btn-danger { border-color: var(--pen-red); color: var(--pen-red); }
  .btn-small { padding: 0.3rem 0.6rem; font-size: 0.72rem; }

  .toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem 0; border-bottom: 1px solid var(--line); }
  .toggle-row:last-child { border-bottom: none; }
  .toggle-row .tgl-name { font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.06em; font-size: 0.85rem; }
  .toggle-row .tgl-desc { color: var(--pencil); font-size: 0.82rem; }
  .switch { position: relative; width: 52px; height: 28px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; inset: 0; cursor: pointer; background: var(--line-strong);
    transition: background 0.12s ease;
  }
  .slider::before {
    content: ""; position: absolute; height: 20px; width: 20px; left: 4px; top: 4px;
    background: var(--paper); transition: transform 0.12s ease;
  }
  .switch input:checked + .slider { background: var(--correct-green); }
  .switch input:checked + .slider::before { transform: translateX(24px); }

  .field { margin-bottom: 1rem; }
  .field label { display: block; font-family: var(--font-mono); font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--pencil); margin-bottom: 0.35rem; }
  .field input, .field textarea {
    width: 100%; padding: 0.6rem 0.8rem; font-family: var(--font-mono); font-size: 0.88rem;
    border: 2px solid var(--line-strong); border-radius: 0; background: var(--input-bg); color: var(--ink);
  }
  .field input:focus, .field textarea:focus { outline: 3px solid var(--pen-red); outline-offset: 2px; }

  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(30,33,40,0.6); display: none;
    align-items: center; justify-content: center; padding: 1rem; z-index: 100;
  }
  .modal-backdrop.is-open { display: flex; }
  .modal {
    background: var(--paper); border: 2px solid var(--ink); width: min(600px, 100%);
    max-height: 85vh; overflow-y: auto; box-shadow: 8px 8px 0 var(--shadow-soft);
  }
  .modal-head { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line-strong); padding: 0.9rem 1.25rem; font-family: var(--font-mono); font-weight: 700; letter-spacing: 0.1em; font-size: 0.85rem; }
  .modal-close { background: none; border: none; cursor: pointer; font-family: var(--font-mono); font-size: 1.4rem; line-height: 1; color: var(--ink); }
  .modal-close:hover { color: var(--pen-red); }
  .modal-body { padding: 1.25rem; }
  .modal-actions { display: flex; gap: 0.75rem; justify-content: flex-end; padding: 0 1.25rem 1.25rem; }

  .banner {
    display: none; padding: 0.75rem 1rem; margin-bottom: 1.25rem; font-family: var(--font-mono);
    font-weight: 700; font-size: 0.85rem; letter-spacing: 0.06em; border: 2px solid;
  }
  .banner.ok { display: block; border-color: var(--correct-green); color: var(--correct-green); }
  .banner.err { display: block; border-color: var(--pen-red); color: var(--pen-red); }

  .login-card { max-width: 420px; margin: 12vh auto 0; }
  .login-card .field { margin-top: 1rem; }
  .empty { color: var(--pencil); font-family: var(--font-mono); font-size: 0.85rem; padding: 1rem 0; }

  .spark { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.12em; color: var(--pencil); text-transform: uppercase; }
  .action-cell { white-space: nowrap; }
</style>
</head>
<body>
  <header class="site-header">
    <div class="container">
      <span class="wordmark">AUTOMCQ <span class="pen">ADMIN</span></span>
      <div class="header-actions">
        <button class="btn btn-ghost btn-small" id="themeBtn" title="Toggle theme">THEME</button>
        <button class="btn btn-small" id="logoutBtn" title="Forget token">LOCK</button>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="banner" id="banner"></div>

    <div class="tabs" id="tabs" style="display:none">
      <button class="tab-btn active" data-tab="overview">OVERVIEW</button>
      <button class="tab-btn" data-tab="devices">DEVICES</button>
      <button class="tab-btn" data-tab="activity">ACTIVITY</button>
      <button class="tab-btn" data-tab="ads">ADS</button>
    </div>

    <section id="tab-overview">
      <div class="stat-grid" id="statGrid"></div>
      <div class="card" style="margin-top:1.25rem">
        <h3 class="card-title">RECENT ACTIVITY (30D)</h3>
        <div id="miniChart"></div>
      </div>
    </section>

    <section id="tab-devices" style="display:none">
      <div class="card">
        <h3 class="card-title">ALL DEVICES</h3>
        <div style="overflow-x:auto"><table id="devicesTable"></table></div>
      </div>
    </section>

    <section id="tab-activity" style="display:none">
      <div class="card">
        <h3 class="card-title">DAILY ACTIVITY &middot; CLAIMS &amp; CLICKS</h3>
        <div id="activityChart"></div>
      </div>
    </section>

    <section id="tab-ads" style="display:none">
      <div class="card">
        <h3 class="card-title">AD &amp; SPONSOR SWITCHES</h3>
        <div id="toggles"></div>
      </div>
      <div class="card">
        <h3 class="card-title">AD COPY</h3>
        <div class="field"><label>Ad name</label><input id="ad_name" autocomplete="off"></div>
        <div class="field"><label>Ad subtitle</label><textarea id="ad_sub" rows="2"></textarea></div>
        <div class="field"><label>Ad URL</label><input id="ad_url" autocomplete="off"></div>
        <div class="modal-actions" style="padding:0"><button class="btn btn-primary" id="saveConfigBtn">SAVE ADS</button></div>
      </div>
    </section>
  </main>

  <div class="modal-backdrop" id="loginModal">
    <div class="modal login-card">
      <div class="modal-head"><span>ADMIN TOKEN</span></div>
      <div class="modal-body">
        <p class="dim" style="margin-top:0">Paste the admin API token to unlock the panel. It stays in this tab&rsquo;s session memory.</p>
        <div class="field"><label>Bearer token</label><input id="tokenInput" type="password" autocomplete="off"></div>
      </div>
      <div class="modal-actions"><button class="btn btn-primary" id="unlockBtn">UNLOCK</button></div>
    </div>
  </div>

  <div class="modal-backdrop" id="detailModal">
    <div class="modal">
      <div class="modal-head"><span>DEVICE LEDGER</span><button class="modal-close" id="detailClose">&times;</button></div>
      <div class="modal-body" id="detailBody"></div>
    </div>
  </div>

<script>
(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const API = "/admin/api";
  let token = sessionStorage.getItem("automcq_admin_token") || "";

  function banner(msg, kind) {
    const el = $("#banner");
    el.textContent = msg;
    el.className = "banner " + (kind || "ok");
    clearTimeout(banner._t);
    banner._t = setTimeout(() => { el.className = "banner"; }, 4000);
  }

  async function api(path, opts) {
    const res = await fetch(API + path, Object.assign({}, opts, {
      headers: Object.assign({}, opts && opts.headers, {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
      }),
    }));
    if (res.status === 401) { token = ""; sessionStorage.removeItem("automcq_admin_token"); showLogin(); throw new Error("Unauthorized"); }
    if (res.status === 404) { banner("Panel is disabled (ADMIN_TOKEN not set on server).", "err"); throw new Error("Not found"); }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || ("HTTP " + res.status));
    }
    return res.json();
  }

  /* ---- theme ---- */
  function initTheme() {
    const saved = localStorage.getItem("automcq_theme");
    if (saved) document.documentElement.dataset.theme = saved;
  }
  $("#themeBtn").addEventListener("click", () => {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("automcq_theme", root.dataset.theme);
  });

  /* ---- login / lock ---- */
  function showLogin() {
    $("#tabs").style.display = "none";
    $$("main > section").forEach(s => s.style.display = "none");
    $("#loginModal").classList.add("is-open");
    $("#tokenInput").focus();
  }
  async function unlock() {
    token = $("#tokenInput").value.trim();
    if (!token) return;
    sessionStorage.setItem("automcq_admin_token", token);
    $("#loginModal").classList.remove("is-open");
    try { await loadAll(); } catch (e) { banner(e.message, "err"); }
  }
  $("#unlockBtn").addEventListener("click", unlock);
  $("#tokenInput").addEventListener("keydown", (e) => { if (e.key === "Enter") unlock(); });
  $("#logoutBtn").addEventListener("click", () => {
    token = ""; sessionStorage.removeItem("automcq_admin_token"); showLogin();
  });

  /* ---- tabs ---- */
  $("#tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab-btn"); if (!btn) return;
    $$(".tab-btn").forEach(b => b.classList.toggle("active", b === btn));
    $$("main > section").forEach(s => s.style.display = "none");
    $("#tab-" + btn.dataset.tab).style.display = "block";
    const loaders = {
      overview: loadOverview, devices: loadDevices,
      activity: loadActivity, ads: loadAds,
    };
    (loaders[btn.dataset.tab] || loadOverview)();
  });

  /* ---- overview ---- */
  async function loadOverview() {
    const s = await api("/stats");
    const cards = [
      ["TOTAL DEVICES", s.total_devices],
      ["CREDITS ISSUED", s.total_credits_issued],
      ["CREDITS SPENT", s.total_credits_spent],
      ["TOTAL BALANCE", s.total_balance],
      ["AD CLAIMS", s.claim_count],
      ["CLICK SPENDS", s.click_count],
      ["ACTIVE TODAY", s.active_devices_today],
    ];
    $("#statGrid").innerHTML = cards.map(([l, n]) =>
      `<div class="stat"><div class="num">${n}</div><div class="lbl">${l}</div></div>`
    ).join("");
    const act = await api("/activity");
    renderMiniChart(act);
  }

  /* ---- devices ---- */
  async function loadDevices() {
    const rows = await api("/devices");
    const table = $("#devicesTable");
    if (!rows.length) {
      table.innerHTML = '<div class="empty">NO DEVICES YET</div>';
      return;
    }
    table.innerHTML =
      "<thead><tr><th>DEVICE</th><th>BALANCE</th><th>CREATED</th><th>LAST ACTIVITY</th><th></th></tr></thead><tbody>" +
      rows.map(r => {
        const created = (r.created_at || "").slice(0, 10);
        const last = r.last_activity ? r.last_activity.slice(0, 16) : "&mdash;";
        return `<tr>
          <td class="uuid-cell mono" title="${r.device_id}">${r.device_id}</td>
          <td class="mono">${r.credits_balance}</td>
          <td class="mono dim">${created}</td>
          <td class="mono dim">${last}</td>
          <td class="action-cell">
            <button class="btn btn-small" data-act="view" data-id="${r.device_id}">LEDGER</button>
            <button class="btn btn-small" data-act="adjust" data-id="${r.device_id}">&plusmn;</button>
            <button class="btn btn-small btn-danger" data-act="delete" data-id="${r.device_id}">DELETE</button>
          </td>
        </tr>`;
      }).join("") + "</tbody>";

    table.querySelectorAll("[data-act]").forEach(btn => {
      btn.addEventListener("click", () => deviceAction(btn.dataset.act, btn.dataset.id));
    });
  }

  async function deviceAction(act, id) {
    try {
      if (act === "view") {
        const d = await api("/devices/" + id);
        const rows = d.ledger.map(e =>
          `<tr><td class="mono dim">${e.timestamp}</td><td class="mono ${e.delta >= 0 ? "pos" : "neg"}">${e.delta >= 0 ? "+" : ""}${e.delta}</td><td class="mono">${e.reason}</td><td class="mono dim">${e.source || ""}</td></tr>`
        ).join("");
        $("#detailBody").innerHTML =
          `<p class="mono" style="word-break:break-all;margin-top:0">${d.device_id}</p>
           <p>Balance: <span class="mono">${d.credits_balance}</span> &middot; Created: <span class="mono dim">${d.created_at.slice(0,10)}</span></p>
           <table><thead><tr><th>TIME</th><th>DELTA</th><th>REASON</th><th>SOURCE</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="empty">NO LEDGER</td></tr>'}</tbody></table>`;
        $("#detailModal").classList.add("is-open");
      } else if (act === "adjust") {
        const input = prompt("Credits adjust for " + id.slice(0, 8) + "…\nUse +N to grant, -N to deduct.");
        if (input === null) return;
        const delta = parseInt(input, 10);
        if (!delta || Math.abs(delta) > 1000) { banner("Enter a non-zero integer between -1000 and 1000.", "err"); return; }
        const r = await api("/devices/" + id + "/credits", { method: "POST", body: JSON.stringify({ delta }) });
        banner("Adjusted " + (delta > 0 ? "+" : "") + delta + " → balance " + r.credits_balance);
        loadDevices(); loadOverview();
      } else if (act === "delete") {
        if (!confirm("Permanently delete " + id.slice(0, 8) + "… and ALL its credits? This is irreversible.")) return;
        const r = await api("/devices/" + id, { method: "DELETE" });
        banner("Deleted device — " + r.credits_removed + " credits removed.");
        loadDevices(); loadOverview();
      }
    } catch (e) { banner(e.message, "err"); }
  }

  /* ---- charts ---- */
  function chartSvg(act, metric) {
    const H = 220, W = 760, P = 8;
    const pts = act.map(p => p[metric]);
    const max = Math.max(1, ...pts);
    const bw = (W - P * 2) / act.length;
    const bars = act.map((p, i) => {
      const h = (p[metric] / max) * (H - 40);
      const x = P + i * bw;
      return `<rect x="${x.toFixed(1)}" y="${(H - 12 - h).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${h.toFixed(1)}" fill="var(--pen-red)" opacity="0.9"><title>${p.date}: ${p[metric]} ${metric.replace(/_/g, " ")}</title></rect>`;
    }).join("");
    const labels = act.map((p, i) => {
      const x = P + i * bw;
      const show = i % Math.ceil(act.length / 8) === 0;
      return show ? `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 2}" text-anchor="middle" font-family="var(--font-mono)" font-size="9" fill="var(--pencil)">${p.date.slice(5)}</text>` : "";
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;background:var(--surface-card)" role="img">
      <line x1="${P}" y1="${H - 12}" x2="${W - P}" y2="${H - 12}" stroke="var(--line-strong)"/>
      ${bars}${labels}
    </svg>`;
  }

  async function loadActivity() {
    const act = await api("/activity");
    $("#activityChart").innerHTML =
      `<p class="spark">Claims per day</p>${chartSvg(act, "claims")}`;
  }
  function renderMiniChart(act) {
    $("#miniChart").innerHTML = chartSvg(act, "active_devices");
  }

  /* ---- ads / config ---- */
  const TOGGLE_KEYS = [
    ["sponsor_overlay_enabled", "Sponsor overlay", "Show the sponsor card overlay on the claim page after a claim."],
    ["sponsor_card_enabled", "Sponsor card", "Show the sponsor card in the extension popup."],
    ["offerwall_enabled", "Offerwall", "Allow the rewarded-ad (offerwall) claim flow."],
  ];
  async function loadAds() {
    const cfg = await api("/config");
    $("#toggles").innerHTML = TOGGLE_KEYS.map(([key, name, desc]) => {
      const on = cfg[key] === true;
      return `<div class="toggle-row">
        <div><div class="tgl-name">${name}</div><div class="tgl-desc">${desc}</div></div>
        <label class="switch"><input type="checkbox" data-key="${key}" ${on ? "checked" : ""}><span class="slider"></span></label>
      </div>`;
    }).join("");
    $("#ad_name").value = cfg.ad_name || "";
    $("#ad_sub").value = cfg.ad_sub || "";
    $("#ad_url").value = cfg.ad_url || "";
  }

  $("#saveConfigBtn").addEventListener("click", async () => {
    try {
      const body = {
        ad_name: $("#ad_name").value.trim(),
        ad_sub: $("#ad_sub").value.trim(),
        ad_url: $("#ad_url").value.trim(),
      };
      $$("#toggles input[type=checkbox]").forEach(c => body[c.dataset.key] = c.checked);
      const cfg = await api("/config", { method: "PUT", body: JSON.stringify(body) });
      banner("Ad settings saved.");
      loadAds();
    } catch (e) { banner(e.message, "err"); }
  });

  $("#detailClose").addEventListener("click", () => $("#detailModal").classList.remove("is-open"));

  /* ---- boot ---- */
  async function loadAll() {
    $("#tabs").style.display = "flex";
    await loadOverview();
  }
  initTheme();
  if (token) {
    loadAll().catch(e => banner(e.message, "err"));
  } else {
    showLogin();
  }
})();
</script>
</body>
</html>
"""
